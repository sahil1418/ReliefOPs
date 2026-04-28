"""Routes module orchestration: load shipments + vehicles, optimize, persist."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import status as http_status
from firebase_admin import firestore as fb_firestore
from google.cloud import firestore as gc_firestore

from src.core.errors import ApiError
from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.audit.log import write_audit_log
from src.modules.disasters.models import GeoPoint
from src.modules.routing import optimizer
from src.modules.routing.models import (
    OptimizeRequest,
    OptimizeStop,
    OptimizeVehicle,
    Route,
    RouteStop,
)
from src.modules.routing.ortools_fallback import absolute_time

log = get_logger("relief.routing")
SHIPMENTS = "shipments"
VEHICLES = "vehicles"
VOLUNTEERS = "volunteers"
WAREHOUSES = "warehouses"
ROUTES = "routes"


async def optimize_routes(
    payload: OptimizeRequest, *, actor_uid: str, org_id: str
) -> list[Route]:
    db = get_firestore()
    ff = gc_firestore.FieldFilter

    # 1. Load shipments.
    shipments_data: dict[str, dict[str, Any]] = {}
    for sid in payload.shipmentIds:
        snap = db.collection(SHIPMENTS).document(sid).get()
        if not snap.exists:
            raise ApiError(
                code="SHIPMENT_NOT_FOUND",
                message=f"shipment {sid} not found",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        shipments_data[sid] = snap.to_dict() or {}

    # 2. Load vehicles + their volunteer assignments.
    vehicles_data: dict[str, dict[str, Any]] = {}
    for vid in payload.vehicleIds:
        snap = db.collection(VEHICLES).document(vid).get()
        if not snap.exists:
            raise ApiError(
                code="VEHICLE_NOT_FOUND",
                message=f"vehicle {vid} not found",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        vehicles_data[vid] = snap.to_dict() or {}

    # 3. Resolve depot from the first shipment's origin warehouse.
    depot_loc = _resolve_depot(shipments_data, db)

    # 4. Build solver inputs.
    stops_in: list[OptimizeStop] = []
    for sid, data in shipments_data.items():
        loc = _coerce_geopoint(data.get("dropoffLocation"))
        if loc is None:
            raise ApiError(
                code="SHIPMENT_NO_DROPOFF",
                message=f"shipment {sid} has no dropoff location",
                status_code=http_status.HTTP_400_BAD_REQUEST,
            )
        priority = data.get("priority") or "normal"
        stops_in.append(
            OptimizeStop(
                shipmentId=sid,
                location=loc,
                address=data.get("dropoffAddress", ""),
                demand_kg=float(data.get("totalKg") or 0.0),
                priority=priority,
                serviceMin=10,
                timeWindow=None,
            )
        )

    vehicles_in: list[OptimizeVehicle] = []
    volunteer_by_vehicle: dict[str, str | None] = {}
    for vid, data in vehicles_data.items():
        # Find the volunteer assigned to this vehicle (most recent active record).
        vol_q = (
            db.collection(VOLUNTEERS)
            .where(filter=ff("vehicleId", "==", vid))
            .limit(1)
            .stream()
        )
        vol = next(iter(vol_q), None)
        vol_uid = (vol.to_dict() or {}).get("userId") if vol else None
        volunteer_by_vehicle[vid] = vol_uid
        vehicles_in.append(
            OptimizeVehicle(
                vehicleId=vid,
                volunteerId=vol_uid,
                capacityKg=float(data.get("capacityKg") or 1000),
                avgSpeedKmh=30.0,
                startLocation=depot_loc,
            )
        )

    # 5. Run the optimizer.
    blocked = [_normalize_polygon(p) for p in payload.blockedAreas if p]
    start_dt = datetime.now(timezone.utc).replace(microsecond=0)

    solved, locations, computed_by, blocked_applied = await optimizer.optimize(
        stops=stops_in,
        vehicles=vehicles_in,
        blocked_polygons=blocked,
        time_limit_seconds=payload.timeLimitSeconds,
        start_dt=start_dt,
    )

    # 6. Persist a routes/{id} per non-empty solved route + return.
    out: list[Route] = []
    for sr in solved:
        veh = vehicles_in[sr.vehicle_idx]
        # Build RouteStops, skipping the artificial depot endpoints.
        route_stops: list[RouteStop] = []
        for i, node in enumerate(sr.stop_indexes):
            if node == 0 or node >= len(locations):
                continue
            stop_meta = stops_in[node - 1]  # node 0 is depot
            route_stops.append(
                RouteStop(
                    location=stop_meta.location,
                    address=stop_meta.address,
                    etaArrive=absolute_time(start_dt, sr.arrival_min[i]),
                    etaDepart=absolute_time(start_dt, sr.depart_min[i]),
                    shipmentId=stop_meta.shipmentId,
                    stopType="dropoff",
                )
            )
        if not route_stops:
            continue

        polyline = _encode_polyline_simple(
            [(depot_loc.lat, depot_loc.lng)]
            + [(s.location.lat, s.location.lng) for s in route_stops]
            + [(depot_loc.lat, depot_loc.lng)]
        )

        ref = db.collection(ROUTES).document()
        doc: dict[str, Any] = {
            "shipmentIds": [s.shipmentId for s in route_stops],
            "vehicleId": veh.vehicleId,
            "volunteerId": volunteer_by_vehicle.get(veh.vehicleId),
            "stops": [
                {
                    "location": fb_firestore.GeoPoint(s.location.lat, s.location.lng),
                    "address": s.address,
                    "etaArrive": s.etaArrive,
                    "etaDepart": s.etaDepart,
                    "shipmentId": s.shipmentId,
                    "stopType": s.stopType,
                }
                for s in route_stops
            ],
            "totalKm": sr.total_km,
            "totalMin": sr.total_min,
            "polyline": polyline,
            "computedBy": computed_by,
            "blockedAreasApplied": blocked_applied,
            "createdAt": fb_firestore.SERVER_TIMESTAMP,
            "orgId": org_id,
        }
        ref.set(doc)

        # Cross-link onto the shipment so the detail page can read it.
        for sid in doc["shipmentIds"]:
            db.collection(SHIPMENTS).document(sid).update(
                {"routeId": ref.id, "etaInitial": route_stops[0].etaArrive,
                 "etaCurrent": route_stops[-1].etaDepart}
            )

        out.append(
            Route(
                id=ref.id,
                shipmentIds=doc["shipmentIds"],
                vehicleId=veh.vehicleId,
                volunteerId=doc["volunteerId"],
                stops=route_stops,
                totalKm=sr.total_km,
                totalMin=sr.total_min,
                polyline=polyline,
                computedBy=computed_by,
                blockedAreasApplied=blocked_applied,
                createdAt=start_dt,
                orgId=org_id,
            )
        )

    write_audit_log(
        actor_uid=actor_uid,
        action="route.optimize",
        resource="routes",
        resource_id=",".join(r.id for r in out) or "(no routes)",
        after={"shipments": len(stops_in), "vehicles": len(vehicles_in), "routes": len(out), "computedBy": computed_by},
        org_id=org_id,
    )

    log.info("route.optimized", routes=len(out), shipments=len(stops_in), computed_by=computed_by)
    return out


def get_route(route_id: str) -> Route | None:
    snap = get_firestore().collection(ROUTES).document(route_id).get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    data["id"] = snap.id
    # Coerce GeoPoint nested in stops
    for st in data.get("stops", []):
        loc = st.get("location")
        if loc is not None and hasattr(loc, "latitude"):
            st["location"] = {"lat": loc.latitude, "lng": loc.longitude}
    return Route.model_validate(data)


def list_routes(*, vehicle_id: str | None, limit: int = 50) -> list[Route]:
    db = get_firestore()
    q: gc_firestore.Query = db.collection(ROUTES)
    if vehicle_id:
        q = q.where(filter=gc_firestore.FieldFilter("vehicleId", "==", vehicle_id))
    q = q.limit(limit)
    docs = list(q.stream())
    docs.sort(key=lambda d: (d.to_dict() or {}).get("createdAt") or 0, reverse=True)
    out: list[Route] = []
    for d in docs:
        data = d.to_dict() or {}
        data["id"] = d.id
        for st in data.get("stops", []):
            loc = st.get("location")
            if loc is not None and hasattr(loc, "latitude"):
                st["location"] = {"lat": loc.latitude, "lng": loc.longitude}
        out.append(Route.model_validate(data))
    return out


# ── Helpers ─────────────────────────────────────────────────────────────────


def _coerce_geopoint(v: Any) -> GeoPoint | None:
    if v is None:
        return None
    if hasattr(v, "latitude") and hasattr(v, "longitude"):
        return GeoPoint(lat=v.latitude, lng=v.longitude)
    if isinstance(v, dict) and "lat" in v and "lng" in v:
        return GeoPoint(lat=float(v["lat"]), lng=float(v["lng"]))
    return None


def _resolve_depot(
    shipments: dict[str, dict[str, Any]], db: gc_firestore.Client
) -> GeoPoint:
    # Use the first shipment's originWarehouseId.
    first = next(iter(shipments.values()), None)
    if not first:
        return GeoPoint(lat=21.4272, lng=92.0058)  # Cox's Bazar fallback
    wh_id = first.get("originWarehouseId")
    if not wh_id:
        return GeoPoint(lat=21.4272, lng=92.0058)
    snap = db.collection(WAREHOUSES).document(wh_id).get()
    if snap.exists:
        loc = _coerce_geopoint((snap.to_dict() or {}).get("location"))
        if loc:
            return loc
    return GeoPoint(lat=21.4272, lng=92.0058)


def _normalize_polygon(p: Any) -> dict[str, Any]:
    """Accept either a real GeoJSON `{type,coordinates}` or our `{type,rings:[{points:[]}]}`."""
    if isinstance(p, dict):
        if "rings" in p:
            return {"type": "Polygon", "rings": p["rings"]}
        if "coordinates" in p and p["coordinates"]:
            ring = p["coordinates"][0]
            points = [{"lng": c[0], "lat": c[1]} for c in ring]
            return {"type": "Polygon", "rings": [{"points": points}]}
    return {"type": "Polygon", "rings": []}


def _encode_polyline_simple(points: list[tuple[float, float]]) -> str:
    """JSON-encoded array of `[lat, lng]` pairs.

    Replaced with Google's encoded-polyline format in COMMIT 10 once Maps is wired.
    For now this is enough for the web client to draw the route as a polyline
    via Leaflet (COMMIT 8 swap) or any other map widget.
    """
    return json.dumps([[round(p[0], 6), round(p[1], 6)] for p in points])
