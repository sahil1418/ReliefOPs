"""Firestore + matcher orchestration for the shipments module."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import status as http_status
from firebase_admin import firestore as fb_firestore
from google.cloud import firestore as gc_firestore

from src.core.errors import ApiError
from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.audit.log import write_audit_log
from src.modules.events import publisher
from src.modules.shipments.matcher import derive_required_skills, match_volunteer
from src.modules.shipments.models import (
    Priority,
    Shipment,
    ShipmentCreate,
    ShipmentItem,
    ShipmentListFilters,
    ShipmentStatus,
    ShipmentStatusUpdate,
)

log = get_logger("relief.shipments")

SHIPMENTS = "shipments"
WAREHOUSES = "warehouses"
INVENTORY = "inventory_items"
VOLUNTEERS = "volunteers"
VEHICLES = "vehicles"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _geo_to_dict(g: Any) -> dict[str, float] | None:
    if g is None:
        return None
    if hasattr(g, "latitude") and hasattr(g, "longitude"):
        return {"lat": g.latitude, "lng": g.longitude}
    if isinstance(g, dict) and "lat" in g and "lng" in g:
        return {"lat": float(g["lat"]), "lng": float(g["lng"])}
    return None


def _doc_to_shipment(doc_snapshot: gc_firestore.DocumentSnapshot) -> Shipment:
    data = doc_snapshot.to_dict() or {}
    data["id"] = doc_snapshot.id
    if "dropoffLocation" in data:
        data["dropoffLocation"] = _geo_to_dict(data["dropoffLocation"]) or data["dropoffLocation"]
    return Shipment.model_validate(data)


def _resolve_item_weights(items: list[ShipmentItem], origin_warehouse_id: str) -> list[ShipmentItem]:
    """Lookup unitWeight_kg from inventory_items where missing; default to 1.0 kg."""
    db = get_firestore()
    resolved: list[ShipmentItem] = []
    for it in items:
        if it.unitWeight_kg is not None and it.warehouseId is not None:
            resolved.append(it)
            continue
        wh = it.warehouseId or origin_warehouse_id
        snap = (
            db.collection(INVENTORY)
            .where(filter=gc_firestore.FieldFilter("warehouseId", "==", wh))
            .where(filter=gc_firestore.FieldFilter("sku", "==", it.sku))
            .limit(1)
            .stream()
        )
        unit_w = 1.0
        for row in snap:
            unit_w = float((row.to_dict() or {}).get("unitWeight_kg") or 1.0)
            break
        resolved.append(it.model_copy(update={"warehouseId": wh, "unitWeight_kg": unit_w}))
    return resolved


def _total_kg(items: list[ShipmentItem]) -> float:
    return round(sum((it.unitWeight_kg or 0.0) * it.qty for it in items), 3)


def _serialize_items(items: list[ShipmentItem]) -> list[dict[str, Any]]:
    return [it.model_dump(exclude_none=False) for it in items]


def _release_reservation(warehouse_id: str, sku: str, qty: float) -> None:
    """Compensating mutation: undo a successful reserve() on rollback.

    Reverses the qty/reservedQty deltas; safe to call from outside a Firestore
    transaction since reservations are best-effort to roll back.
    """
    db = get_firestore()
    iid = f"inv-{warehouse_id}-{sku}".lower()
    ref = db.collection("inventory_items").document(iid)
    snap = ref.get()
    if not snap.exists:
        return
    data = snap.to_dict() or {}
    new_qty = float(data.get("qty") or 0.0) + qty
    new_reserved = max(0.0, float(data.get("reservedQty") or 0.0) - qty)
    ref.update({
        "qty": new_qty,
        "reservedQty": new_reserved,
        "updatedAt": fb_firestore.SERVER_TIMESTAMP,
    })


def _consume_reservation(warehouse_id: str, sku: str, qty: float) -> None:
    """When a shipment is delivered or fails, drain reservedQty by `qty` (no
    refund — the units are gone). Used by `update_status`.
    """
    db = get_firestore()
    iid = f"inv-{warehouse_id}-{sku}".lower()
    ref = db.collection("inventory_items").document(iid)
    snap = ref.get()
    if not snap.exists:
        return
    data = snap.to_dict() or {}
    ref.update({
        "reservedQty": max(0.0, float(data.get("reservedQty") or 0.0) - qty),
        "updatedAt": fb_firestore.SERVER_TIMESTAMP,
    })


# ── Operations ───────────────────────────────────────────────────────────────


def list_shipments(
    *,
    filters: ShipmentListFilters,
    requester_uid: str,
    requester_role: str | None,
    requester_org_id: str | None,
) -> list[Shipment]:
    db = get_firestore()
    q: gc_firestore.Query = db.collection(SHIPMENTS)

    if filters.status:
        q = q.where(filter=gc_firestore.FieldFilter("status", "==", filters.status))
    if filters.disasterId:
        q = q.where(filter=gc_firestore.FieldFilter("disasterId", "==", filters.disasterId))
    if filters.volunteerId:
        q = q.where(filter=gc_firestore.FieldFilter("assignedVolunteerId", "==", filters.volunteerId))
    if requester_role == "volunteer":
        # Volunteers only see their own assignments — even if no explicit filter passed.
        q = q.where(filter=gc_firestore.FieldFilter("assignedVolunteerId", "==", requester_uid))
    if requester_org_id and requester_role not in {"super_admin"}:
        q = q.where(filter=gc_firestore.FieldFilter("orgId", "==", requester_org_id))

    q = q.limit(filters.limit)

    docs = list(q.stream())
    # Sort newest-first in Python so we don't need an index for every filter combo.
    docs.sort(key=lambda d: (d.to_dict() or {}).get("createdAt") or 0, reverse=True)
    return [_doc_to_shipment(d) for d in docs]


def create_shipment(
    payload: ShipmentCreate, *, actor_uid: str, actor_org_id: str
) -> Shipment:
    db = get_firestore()

    # Local import to avoid a top-level cycle: inventory.service uses audit.log
    # which lives in shipments orbit.
    from src.modules.inventory import service as inventory_service

    items = _resolve_item_weights(payload.items, payload.originWarehouseId)
    total_kg = _total_kg(items)

    # Look up the warehouse for distance computations.
    wh_doc = db.collection(WAREHOUSES).document(payload.originWarehouseId).get()
    if not wh_doc.exists:
        raise ApiError(
            code="WAREHOUSE_NOT_FOUND",
            message=f"Origin warehouse '{payload.originWarehouseId}' does not exist.",
            status_code=http_status.HTTP_400_BAD_REQUEST,
        )
    wh = wh_doc.to_dict() or {}
    wh_loc = _geo_to_dict(wh.get("location"))
    if not wh_loc:
        raise ApiError(
            code="WAREHOUSE_NO_LOCATION",
            message=f"Origin warehouse '{payload.originWarehouseId}' has no location.",
            status_code=http_status.HTTP_400_BAD_REQUEST,
        )

    # Auto-match a volunteer.
    item_categories = _categories_for_items(items)
    required_skills = list(derive_required_skills(item_categories) | set(payload.requiredSkills))

    volunteers = [
        ({"id": d.id, **(d.to_dict() or {})})
        for d in db.collection(VOLUNTEERS).stream()
    ]
    vehicles = {
        d.id: (d.to_dict() or {})
        for d in db.collection(VEHICLES).stream()
    }

    match = match_volunteer(
        shipment_total_kg=total_kg,
        shipment_org_id=actor_org_id,
        required_skills=required_skills,
        warehouse_lat=wh_loc["lat"],
        warehouse_lng=wh_loc["lng"],
        volunteers=volunteers,
        vehicles_by_id=vehicles,
    )

    now = datetime.now(timezone.utc)
    shipment_doc: dict[str, Any] = {
        "disasterId": payload.disasterId,
        "requestIds": payload.requestIds,
        "items": _serialize_items(items),
        "totalKg": total_kg,
        "originWarehouseId": payload.originWarehouseId,
        "dropoffLocation": fb_firestore.GeoPoint(
            payload.dropoffLocation.lat, payload.dropoffLocation.lng
        ),
        "dropoffAddress": payload.dropoffAddress,
        "priority": payload.priority,
        "status": "created",
        "assignedVolunteerId": None,
        "vehicleId": None,
        "etaInitial": None,
        "etaCurrent": None,
        "createdAt": fb_firestore.SERVER_TIMESTAMP,
        "deliveredAt": None,
        "orgId": actor_org_id,
        "requiredSkills": required_skills,
    }
    if match is not None:
        v_uid, vehicle_id, score = match
        shipment_doc["status"] = "assigned"
        shipment_doc["assignedVolunteerId"] = v_uid
        shipment_doc["vehicleId"] = vehicle_id
        shipment_doc["matchScore"] = round(score, 2)

    ref = db.collection(SHIPMENTS).document()

    # Reserve inventory atomically (per-SKU). On any 409 we roll back the
    # already-reserved items and re-raise so the shipment doc is never written
    # with mismatched stock.
    rolled_back: list[tuple[str, str, float]] = []  # (warehouseId, sku, qty)
    try:
        for it in items:
            wh_for_item = it.warehouseId or payload.originWarehouseId
            inventory_service.reserve(
                warehouse_id=wh_for_item,
                sku=it.sku,
                qty=float(it.qty),
                shipment_id=ref.id,
                actor_uid=actor_uid,
                org_id=actor_org_id,
            )
            rolled_back.append((wh_for_item, it.sku, float(it.qty)))
    except ApiError:
        # Compensating transaction: release everything we reserved so far.
        for wh, sku, q in rolled_back:
            _release_reservation(wh, sku, q)
        raise

    ref.set(shipment_doc)
    log.info(
        "shipment.created",
        shipment_id=ref.id,
        priority=payload.priority,
        total_kg=total_kg,
        matched_volunteer=shipment_doc.get("assignedVolunteerId"),
    )

    write_audit_log(
        actor_uid=actor_uid,
        action="shipment.create",
        resource="shipments",
        resource_id=ref.id,
        after={k: v for k, v in shipment_doc.items() if k not in ("dropoffLocation",)},
        org_id=actor_org_id,
    )

    publisher.publish(
        "shipment.created",
        {"id": ref.id, "status": shipment_doc["status"], "priority": payload.priority},
        org_id=actor_org_id or "",
    )

    snap = ref.get()
    return _doc_to_shipment(snap)


def update_status(
    shipment_id: str,
    body: ShipmentStatusUpdate,
    *,
    actor_uid: str,
    actor_role: str | None,
    actor_org_id: str | None,
) -> Shipment:
    db = get_firestore()
    ref = db.collection(SHIPMENTS).document(shipment_id)
    snap = ref.get()
    if not snap.exists:
        raise ApiError(
            code="SHIPMENT_NOT_FOUND",
            message=f"shipment {shipment_id} not found",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )
    before = snap.to_dict() or {}

    # Volunteers may only mutate their own assignments.
    if actor_role == "volunteer" and before.get("assignedVolunteerId") != actor_uid:
        raise ApiError(
            code="FORBIDDEN",
            message="You can only update shipments assigned to you.",
            status_code=http_status.HTTP_403_FORBIDDEN,
        )

    update: dict[str, Any] = {"status": body.status}
    if body.status == "delivered":
        update["deliveredAt"] = fb_firestore.SERVER_TIMESTAMP

    ref.update(update)

    # Inventory side-effects on terminal transitions.
    prev_status = before.get("status")
    if body.status == "delivered" and prev_status != "delivered":
        # Units handed over: drain reservedQty (no refund).
        for it in (before.get("items") or []):
            wh = it.get("warehouseId") or before.get("originWarehouseId")
            if wh and it.get("sku") and it.get("qty"):
                _consume_reservation(wh, str(it["sku"]), float(it["qty"]))
    elif body.status == "failed" and prev_status not in {"delivered", "failed"}:
        # Refund reservedQty back into qty so stock can be re-reserved.
        for it in (before.get("items") or []):
            wh = it.get("warehouseId") or before.get("originWarehouseId")
            if wh and it.get("sku") and it.get("qty"):
                _release_reservation(wh, str(it["sku"]), float(it["qty"]))

    write_audit_log(
        actor_uid=actor_uid,
        action="shipment.status_update",
        resource="shipments",
        resource_id=shipment_id,
        before={"status": before.get("status")},
        after={"status": body.status, "note": body.note},
        org_id=actor_org_id or before.get("orgId"),
    )

    publisher.publish(
        "shipment.status_changed",
        {
            "id": shipment_id,
            "status": body.status,
            "previous": before.get("status"),
            "actor_uid": actor_uid,
        },
        org_id=actor_org_id or "",
    )

    return _doc_to_shipment(ref.get())


def assign_volunteer(
    shipment_id: str,
    volunteer_id: str,
    *,
    actor_uid: str,
    actor_org_id: str | None,
) -> Shipment:
    db = get_firestore()
    ref = db.collection(SHIPMENTS).document(shipment_id)
    snap = ref.get()
    if not snap.exists:
        raise ApiError(
            code="SHIPMENT_NOT_FOUND",
            message=f"shipment {shipment_id} not found",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )

    # Pull the volunteer's vehicle so the shipment row stays consistent.
    v_doc = db.collection(VOLUNTEERS).document(volunteer_id).get()
    if not v_doc.exists:
        # Try by userId field (volunteers collection often keyed by uid).
        candidates = list(
            db.collection(VOLUNTEERS)
            .where(filter=gc_firestore.FieldFilter("userId", "==", volunteer_id))
            .limit(1)
            .stream()
        )
        if not candidates:
            raise ApiError(
                code="VOLUNTEER_NOT_FOUND",
                message=f"volunteer {volunteer_id} not found",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        v_doc = candidates[0]

    v_data = v_doc.to_dict() or {}
    update: dict[str, Any] = {
        "assignedVolunteerId": v_data.get("userId") or v_doc.id,
        "vehicleId": v_data.get("vehicleId"),
        "status": "assigned",
    }
    ref.update(update)

    write_audit_log(
        actor_uid=actor_uid,
        action="shipment.assign",
        resource="shipments",
        resource_id=shipment_id,
        before={"assignedVolunteerId": (snap.to_dict() or {}).get("assignedVolunteerId")},
        after=update,
        org_id=actor_org_id,
    )

    publisher.publish(
        "shipment.status_changed",
        {"id": shipment_id, "status": "assigned", "actor_uid": actor_uid},
        org_id=actor_org_id or "",
    )

    return _doc_to_shipment(ref.get())


def get_shipment(shipment_id: str) -> Shipment | None:
    db = get_firestore()
    snap = db.collection(SHIPMENTS).document(shipment_id).get()
    if not snap.exists:
        return None
    return _doc_to_shipment(snap)


# ── Internal helpers ────────────────────────────────────────────────────────


def _categories_for_items(items: list[ShipmentItem]) -> set[str]:
    """Look each SKU's category up from inventory_items."""
    db = get_firestore()
    cats: set[str] = set()
    for it in items:
        wh = it.warehouseId
        if not wh:
            continue
        snap = (
            db.collection(INVENTORY)
            .where(filter=gc_firestore.FieldFilter("warehouseId", "==", wh))
            .where(filter=gc_firestore.FieldFilter("sku", "==", it.sku))
            .limit(1)
            .stream()
        )
        for row in snap:
            cat = (row.to_dict() or {}).get("category")
            if cat:
                cats.add(cat)
            break
    return cats


__all__ = [
    "Priority",
    "ShipmentStatus",
    "assign_volunteer",
    "create_shipment",
    "get_shipment",
    "list_shipments",
    "update_status",
]
