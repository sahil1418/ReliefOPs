"""Live GPS tracking — RTDB write per ping + throttled Firestore aggregation.

Architecture (BLUEPRINT Phase 6 Module 6):
  Volunteer Flutter app emits a location every 15s. Each ping:
    1. Writes to Realtime Database `/locations/{volunteerId}` for the live admin map
       (cheap, designed for high-frequency presence-style data).
    2. Conditionally appends to Firestore `tracking_events` — but only if the
       most recent event for that shipment is older than `MIN_AGGREGATION_SECONDS`
       (default 50). This is the "1 doc per minute" aggregation the blueprint
       describes; the real Cloud Function path (COMMIT 10 deploy) is identical
       behavior, just running on RTDB onWrite instead of inline.
    3. Publishes Pub/Sub `location.updated` for downstream analytics fan-out.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import firebase_admin
from fastapi import status as http_status
from firebase_admin import db as fb_rtdb
from firebase_admin import firestore as fb_firestore
from google.cloud import firestore as gc_firestore

from src.core.errors import ApiError
from src.core.firebase import get_firestore, init_firebase
from src.core.logging import get_logger
from src.modules.disasters.models import GeoPoint
from src.modules.events import publisher
from src.modules.tracking.models import TrackingEvent, TrackingEventCreate

log = get_logger("relief.tracking")

TRACKING_EVENTS = "tracking_events"
MIN_AGGREGATION_SECONDS = 50


def _coerce_geopoint(v: Any) -> GeoPoint | None:
    if v is None:
        return None
    if hasattr(v, "latitude") and hasattr(v, "longitude"):
        return GeoPoint(lat=v.latitude, lng=v.longitude)
    if isinstance(v, dict) and "lat" in v and "lng" in v:
        return GeoPoint(lat=float(v["lat"]), lng=float(v["lng"]))
    return None


def _doc_to_event(snap: gc_firestore.DocumentSnapshot) -> TrackingEvent:
    data = snap.to_dict() or {}
    data["id"] = snap.id
    if "location" in data:
        loc = _coerce_geopoint(data["location"])
        if loc:
            data["location"] = loc.model_dump()
    return TrackingEvent.model_validate(data)


def _rtdb_url() -> str | None:
    """Best-effort lookup of the Realtime Database emulator/prod URL."""
    import os
    if os.environ.get("FIREBASE_DATABASE_EMULATOR_HOST"):
        return f"http://{os.environ['FIREBASE_DATABASE_EMULATOR_HOST']}/?ns=relief-logistics"
    return os.environ.get("FIREBASE_DATABASE_URL")


def _write_rtdb(volunteer_uid: str, shipment_id: str | None, payload: dict[str, Any]) -> None:
    """Push to /locations/{uid}. The admin map subscribes to this path for live pins."""
    try:
        init_firebase()
        url = _rtdb_url()
        if url:
            ref = fb_rtdb.reference(f"locations/{volunteer_uid}", url=url)
        else:
            ref = fb_rtdb.reference(f"locations/{volunteer_uid}")
        ref.set(payload)
        if shipment_id:
            sref = (
                fb_rtdb.reference(f"shipments/{shipment_id}/lastPing", url=url)
                if url
                else fb_rtdb.reference(f"shipments/{shipment_id}/lastPing")
            )
            sref.set(payload)
    except Exception as exc:  # noqa: BLE001
        log.warning("tracking.rtdb_write_failed", error=str(exc))


def record_event(
    payload: TrackingEventCreate, *, volunteer_uid: str, actor_role: str | None
) -> dict[str, Any]:
    """Volunteer ping handler. Returns ``{ok, aggregated, lastEventTs}``.

    `aggregated=True` means a Firestore tracking_events doc was written this call;
    otherwise the call only updated RTDB (throttled).
    """
    if actor_role not in {"volunteer", "coordinator", "ngo_admin", "super_admin"}:
        # Beneficiaries shouldn't be able to push fake locations.
        raise ApiError(
            "FORBIDDEN",
            "Only volunteers + staff may post tracking events.",
            http_status.HTTP_403_FORBIDDEN,
        )

    now = datetime.now(timezone.utc)

    rtdb_payload = {
        "lat": payload.location.lat,
        "lng": payload.location.lng,
        "ts": now.isoformat(),
        "speedKmh": payload.speedKmh,
        "accuracy": payload.accuracy,
        "heading": payload.heading,
        "shipmentId": payload.shipmentId,
        "volunteerId": volunteer_uid,
    }
    _write_rtdb(volunteer_uid, payload.shipmentId, rtdb_payload)

    # Throttle Firestore aggregation: only persist if the last event for this
    # shipment (or volunteer when no shipment) is older than MIN_AGGREGATION_SECONDS.
    db = get_firestore()
    q: gc_firestore.Query = db.collection(TRACKING_EVENTS)
    if payload.shipmentId:
        q = q.where(filter=gc_firestore.FieldFilter("shipmentId", "==", payload.shipmentId))
    else:
        q = q.where(filter=gc_firestore.FieldFilter("volunteerId", "==", volunteer_uid))
    q = q.order_by("ts", direction=gc_firestore.Query.DESCENDING).limit(1)

    most_recent = next(iter(q.stream()), None)
    last_ts: datetime | None = None
    if most_recent:
        ts = (most_recent.to_dict() or {}).get("ts")
        if isinstance(ts, datetime):
            last_ts = ts

    aggregated = False
    if last_ts is None or (now - last_ts) >= timedelta(seconds=MIN_AGGREGATION_SECONDS):
        ref = db.collection(TRACKING_EVENTS).document()
        ref.set({
            "shipmentId": payload.shipmentId,
            "volunteerId": volunteer_uid,
            "location": fb_firestore.GeoPoint(payload.location.lat, payload.location.lng),
            "ts": now,
            "speedKmh": payload.speedKmh,
            "accuracy": payload.accuracy,
            "heading": payload.heading,
        })
        aggregated = True
        log.info(
            "tracking.aggregated",
            volunteer_uid=volunteer_uid,
            shipment_id=payload.shipmentId,
            doc_id=ref.id,
        )

        publisher.publish(
            "location.updated",
            {
                "volunteerId": volunteer_uid,
                "shipmentId": payload.shipmentId,
                "lat": payload.location.lat,
                "lng": payload.location.lng,
            },
        )

    # ── ML Anomaly Detection (Pillar 2) ─────────────────────────────────
    anomaly_result = None
    try:
        from src.modules.ml.anomaly_detector import detect as ml_detect

        current_ping = {
            "lat": payload.location.lat,
            "lng": payload.location.lng,
            "speedKmh": payload.speedKmh,
            "heading": payload.heading,
            "ts": now.isoformat(),
        }
        # TODO: retrieve previous ping from RTDB for better feature extraction.
        anomaly_result = ml_detect(current_ping, previous_ping=None)

        if anomaly_result.is_anomaly:
            _persist_anomaly(
                anomaly_result, payload, volunteer_uid, now
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("tracking.anomaly_detection_failed", error=str(exc)[:200])

    return {
        "ok": True,
        "aggregated": aggregated,
        "lastEventTs": (last_ts or now).isoformat(),
        "anomaly": {
            "detected": anomaly_result.is_anomaly if anomaly_result else False,
            "score": anomaly_result.score if anomaly_result else 0,
            "type": anomaly_result.anomaly_type.value if anomaly_result else "none",
        } if anomaly_result else None,
    }


def _persist_anomaly(
    result: Any, payload: TrackingEventCreate, volunteer_uid: str, ts: datetime
) -> None:
    """Write anomaly event to Firestore + publish Pub/Sub."""
    from firebase_admin import firestore as fb_fs

    db = get_firestore()
    ref = db.collection("anomaly_events").document()
    ref.set({
        "anomaly_type": result.anomaly_type.value,
        "score": result.score,
        "confidence": result.confidence,
        "recommended_action": result.recommended_action,
        "features": result.features_used,
        "lat": payload.location.lat,
        "lng": payload.location.lng,
        "volunteerId": volunteer_uid,
        "shipmentId": payload.shipmentId,
        "detectedAt": ts,
    })

    publisher.publish(
        "tracking.anomaly",
        {
            "anomalyId": ref.id,
            "anomalyType": result.anomaly_type.value,
            "score": result.score,
            "volunteerId": volunteer_uid,
            "shipmentId": payload.shipmentId,
            "lat": payload.location.lat,
            "lng": payload.location.lng,
        },
    )

    log.info(
        "tracking.anomaly_detected",
        anomaly_id=ref.id,
        anomaly_type=result.anomaly_type.value,
        score=result.score,
        volunteer_uid=volunteer_uid,
    )


def list_events(
    *,
    shipment_id: str,
    limit: int = 100,
    requester_uid: str,
    requester_role: str | None,
) -> list[TrackingEvent]:
    db = get_firestore()
    # Permission: volunteers see only their own assignments' tracks.
    if requester_role == "volunteer":
        sshot = db.collection("shipments").document(shipment_id).get()
        if sshot.exists:
            assigned = (sshot.to_dict() or {}).get("assignedVolunteerId")
            if assigned and assigned != requester_uid:
                raise ApiError(
                    "FORBIDDEN",
                    "You can only read tracking for shipments assigned to you.",
                    http_status.HTTP_403_FORBIDDEN,
                )

    q = (
        db.collection(TRACKING_EVENTS)
        .where(filter=gc_firestore.FieldFilter("shipmentId", "==", shipment_id))
        .order_by("ts", direction=gc_firestore.Query.DESCENDING)
        .limit(limit)
    )
    return [_doc_to_event(d) for d in q.stream()]
