"""Disruption monitor — Cloud Scheduler-driven cron worker.

Pipeline (BLUEPRINT Phase 6 Module 8):
  1. Pull recent alerts from ReliefWeb + OpenWeatherMap (both have free tiers).
  2. Optional: Gemini Flash classifies severity (1-5) + headline + affected GeoJSON.
  3. Write each as `alerts/{id}` (Firestore).
  4. For each active disaster, find shipments whose dropoff lies within an
     active alert area; for severity >= 3 trigger a reroute via the routing
     service.
  5. FCM push to volunteers + coordinators for affected shipments.

For COMMIT 10 we expose the worker via:
  POST /api/admin/disruption/run        — manual trigger (admin-only)
  POST /api/admin/disruption/inject     — drop a synthetic alert (demo)

Cloud Scheduler hits the manual endpoint daily once Cloud Run is wired.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from firebase_admin import firestore as fb_firestore
from google.cloud import firestore as gc_firestore

from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.audit.log import write_audit_log
from src.modules.events import publisher
from src.modules.notifications import fcm
from src.modules.routing import service as routing_service
from src.modules.routing.models import OptimizeRequest

log = get_logger("relief.disruption")


# ── External feed adapters ──────────────────────────────────────────────────


async def _fetch_reliefweb(country_iso: str = "BGD", limit: int = 5) -> list[dict[str, Any]]:
    """Pull recent disaster reports for a country code from ReliefWeb's open API.

    Docs: https://reliefweb.int/help/api  — no key required for read-only.
    """
    params = {
        "appname": "reliefops-demo",
        "limit": str(limit),
        "filter[field]": "country.iso3",
        "filter[value]": country_iso,
        "fields[include][]": "title",
        "sort[]": "date.created:desc",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as cx:
            res = await cx.get("https://api.reliefweb.int/v1/reports", params=params)
            res.raise_for_status()
            data = res.json()
        return [
            {
                "source": "reliefweb",
                "headline": (item.get("fields") or {}).get("title", "")[:200],
                "url": item.get("href"),
            }
            for item in (data.get("data") or [])
        ]
    except Exception as exc:  # noqa: BLE001
        log.warning("disruption.reliefweb_failed", error=str(exc))
        return []


async def _fetch_openweather(
    *, lat: float, lng: float, api_key: str | None
) -> list[dict[str, Any]]:
    """One-Call API alerts at a point. No-op when no key configured."""
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=10) as cx:
            res = await cx.get(
                "https://api.openweathermap.org/data/3.0/onecall",
                params={
                    "lat": lat,
                    "lon": lng,
                    "exclude": "current,minutely,hourly,daily",
                    "appid": api_key,
                },
            )
            res.raise_for_status()
            data = res.json()
        out: list[dict[str, Any]] = []
        for a in data.get("alerts") or []:
            out.append({
                "source": "openweather",
                "headline": (a.get("event") or "")[:200],
                "description": (a.get("description") or "")[:500],
                "lat": lat,
                "lng": lng,
            })
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("disruption.openweather_failed", error=str(exc))
        return []


# ── Persistence ─────────────────────────────────────────────────────────────


def _seeded_alert(
    *,
    headline: str,
    severity: int,
    lat: float,
    lng: float,
    source: str,
    org_id: str | None = None,
    bbox_radius_deg: float = 0.02,
) -> dict[str, Any]:
    """Build an `alerts` doc for a point-source disruption."""
    polygon = {
        "type": "Polygon",
        "rings": [{
            "points": [
                {"lat": lat - bbox_radius_deg, "lng": lng - bbox_radius_deg},
                {"lat": lat - bbox_radius_deg, "lng": lng + bbox_radius_deg},
                {"lat": lat + bbox_radius_deg, "lng": lng + bbox_radius_deg},
                {"lat": lat + bbox_radius_deg, "lng": lng - bbox_radius_deg},
                {"lat": lat - bbox_radius_deg, "lng": lng - bbox_radius_deg},
            ],
        }],
    }
    return {
        "type": "weather",
        "subtype": "disruption_monitor",
        "severity": severity,
        "headline": headline[:200],
        "source": source,
        "classifiedBy": "human",
        "detectedAt": fb_firestore.SERVER_TIMESTAMP,
        "location": fb_firestore.GeoPoint(lat, lng),
        "area": polygon,
        "resolved": False,
        "rerouteRecommended": severity >= 3,
        "orgId": org_id,
    }


def _bbox_contains(bbox: dict[str, Any], lat: float, lng: float) -> bool:
    if not bbox:
        return False
    if isinstance(bbox, dict) and {"west", "south", "east", "north"}.issubset(bbox.keys()):
        return bbox["west"] <= lng <= bbox["east"] and bbox["south"] <= lat <= bbox["north"]
    return False


# ── Reroute fan-out ─────────────────────────────────────────────────────────


async def _reroute_affected_shipments(
    alert_id: str, alert_doc: dict[str, Any], *, actor_uid: str
) -> list[str]:
    db = get_firestore()
    affected: list[str] = []

    # Pull all in-flight shipments for the org (or all if no orgId on alert).
    q: gc_firestore.Query = db.collection("shipments").where(
        filter=gc_firestore.FieldFilter("status", "in", ["assigned", "in_transit"])
    )
    if alert_doc.get("orgId"):
        q = q.where(filter=gc_firestore.FieldFilter("orgId", "==", alert_doc["orgId"]))

    shipments = list(q.stream())

    alert_loc = alert_doc.get("location")
    alert_lat = getattr(alert_loc, "latitude", None) if alert_loc else None
    alert_lng = getattr(alert_loc, "longitude", None) if alert_loc else None

    for s in shipments:
        sd = s.to_dict() or {}
        loc = sd.get("dropoffLocation")
        s_lat = getattr(loc, "latitude", None)
        s_lng = getattr(loc, "longitude", None)
        if s_lat is None or alert_lat is None:
            continue
        # Cheap proximity check: 5 km haversine buffer.
        if _proximity_km(alert_lat, alert_lng, s_lat, s_lng) > 5:
            continue
        affected.append(s.id)

        # Trigger a reroute that excludes the alert area.
        try:
            await routing_service.optimize_routes(
                OptimizeRequest(
                    shipmentIds=[s.id],
                    vehicleIds=[sd.get("vehicleId") or "veh-van-01"],
                    blockedAreas=[alert_doc.get("area") or {}],
                    timeLimitSeconds=4,
                ),
                actor_uid=actor_uid,
                org_id=sd.get("orgId") or "org-relief-bd",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("disruption.reroute_failed", shipment_id=s.id, error=str(exc))

        # Notify the assigned volunteer.
        if sd.get("assignedVolunteerId"):
            fcm.send_to_topic(
                f"volunteer-{sd['assignedVolunteerId']}",
                title="Route updated",
                body=f"{alert_doc['headline']} — your route has been re-optimised.",
                data={"shipmentId": s.id, "alertId": alert_id},
            )

    if affected and alert_doc.get("orgId"):
        # Broadcast to the org's coordinators too.
        fcm.send_to_topic(
            f"org-{alert_doc['orgId']}-alerts",
            title=f"Disruption detected (sev {alert_doc['severity']})",
            body=alert_doc["headline"],
            data={"alertId": alert_id, "affected": str(len(affected))},
        )

    return affected


def _proximity_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    """Crude haversine for the proximity filter."""
    import math
    R = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlmb = math.radians(b_lng - a_lng)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ── Public entry points ─────────────────────────────────────────────────────


async def run_once(*, actor_uid: str, country_iso: str = "BGD") -> dict[str, Any]:
    """Cron entry point. Pulls feeds, writes alerts, triggers reroutes."""
    db = get_firestore()
    from src.core.config import get_settings

    settings = get_settings()
    alerts_written: list[str] = []
    rerouted_shipments: list[str] = []

    # Iterate over each active disaster — alerts are scoped to its bbox.
    disasters = list(
        db.collection("disasters")
        .where(filter=gc_firestore.FieldFilter("status", "==", "active"))
        .stream()
    )

    for d in disasters:
        dd = d.to_dict() or {}
        bbox = dd.get("bbox") or {}
        if not bbox:
            continue
        center_lat = (bbox.get("north", 0) + bbox.get("south", 0)) / 2
        center_lng = (bbox.get("east", 0) + bbox.get("west", 0)) / 2
        org_id = dd.get("orgId")

        # 1. ReliefWeb (open) — country-wide context.
        rw = await _fetch_reliefweb(country_iso=country_iso, limit=3)
        # 2. OpenWeather alerts at the disaster center.
        ow = await _fetch_openweather(
            lat=center_lat,
            lng=center_lng,
            api_key=settings.openweather_api_key or None,
        )

        for raw in rw + ow:
            severity = 4 if raw["source"] == "openweather" else 2
            alert_doc = _seeded_alert(
                headline=f"[{raw['source']}] {raw['headline']}",
                severity=severity,
                lat=center_lat,
                lng=center_lng,
                source=raw["source"],
                org_id=org_id,
            )
            ref = db.collection("alerts").document()
            ref.set(alert_doc)
            alerts_written.append(ref.id)

            publisher.publish(
                "disruption.detected",
                {"alertId": ref.id, "severity": severity, "source": raw["source"]},
                org_id=org_id or "",
            )

            if severity >= 3:
                affected = await _reroute_affected_shipments(
                    ref.id, alert_doc, actor_uid=actor_uid
                )
                rerouted_shipments.extend(affected)

    write_audit_log(
        actor_uid=actor_uid,
        action="disruption.monitor_run",
        resource="alerts",
        resource_id=",".join(alerts_written) or "(none)",
        after={
            "alertsWritten": len(alerts_written),
            "shipmentsRerouted": len(set(rerouted_shipments)),
        },
        org_id=None,
    )

    return {
        "ok": True,
        "alertsWritten": len(alerts_written),
        "shipmentsRerouted": len(set(rerouted_shipments)),
        "alertIds": alerts_written,
    }


async def inject_demo_alert(
    *,
    headline: str,
    severity: int,
    lat: float,
    lng: float,
    org_id: str | None,
    actor_uid: str,
) -> dict[str, Any]:
    """Stage-controllable disruption — used in the demo. Writes one alert and
    triggers reroutes immediately."""
    db = get_firestore()
    alert_doc = _seeded_alert(
        headline=headline, severity=severity, lat=lat, lng=lng, source="demo_inject", org_id=org_id
    )
    ref = db.collection("alerts").document()
    ref.set(alert_doc)
    publisher.publish(
        "disruption.detected",
        {"alertId": ref.id, "severity": severity, "source": "demo_inject"},
        org_id=org_id or "",
    )
    affected = await _reroute_affected_shipments(ref.id, alert_doc, actor_uid=actor_uid)
    write_audit_log(
        actor_uid=actor_uid,
        action="disruption.demo_inject",
        resource="alerts",
        resource_id=ref.id,
        after={"headline": headline, "severity": severity, "shipmentsRerouted": len(affected)},
        org_id=org_id,
    )
    return {
        "ok": True,
        "alertId": ref.id,
        "shipmentsRerouted": len(affected),
        "affectedShipmentIds": affected,
    }
