"""Inventory service — atomic reservations + expiry monitor.

`reserve()` runs as a Firestore transaction so concurrent shipment-creation
flows can't oversell the same SKU.

Schema decision (BLUEPRINT Phase 6 Module 3):
  - `qty`         = currently *available* (unreserved) units
  - `reservedQty` = units earmarked for in-flight shipments
  - total stock   = qty + reservedQty

Reserve  : qty -= n, reservedQty += n
Ship     : reservedQty -= n  (called from shipments service when status flips
           to in_transit; not yet wired in COMMIT 7).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import status as http_status
from firebase_admin import firestore as fb_firestore
from google.cloud import firestore as gc_firestore

from src.core.errors import ApiError
from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.audit.log import write_audit_log
from src.modules.disasters.models import GeoPoint
from src.modules.events import publisher
from src.modules.inventory.models import (
    ExpiringItem,
    InventoryItem,
    InventoryItemCreate,
    InventoryItemPatch,
    ReserveResponseData,
    Warehouse,
    WarehouseCreate,
    WarehousePatch,
    WarehouseStockSummary,
)

log = get_logger("relief.inventory")

WAREHOUSES = "warehouses"
INVENTORY = "inventory_items"
RESERVATIONS = "inventory_reservations"
ALERTS = "alerts"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _coerce_geopoint(v: Any) -> GeoPoint | None:
    if v is None:
        return None
    if hasattr(v, "latitude") and hasattr(v, "longitude"):
        return GeoPoint(lat=v.latitude, lng=v.longitude)
    if isinstance(v, dict) and "lat" in v and "lng" in v:
        return GeoPoint(lat=float(v["lat"]), lng=float(v["lng"]))
    return None


def _doc_to_warehouse(snap: gc_firestore.DocumentSnapshot) -> Warehouse:
    data = snap.to_dict() or {}
    data["id"] = snap.id
    if "location" in data:
        data["location"] = _coerce_geopoint(data["location"]) or {"lat": 0, "lng": 0}
    return Warehouse.model_validate(data)


def _doc_to_item(snap: gc_firestore.DocumentSnapshot) -> InventoryItem:
    data = snap.to_dict() or {}
    data["id"] = snap.id
    return InventoryItem.model_validate(data)


# ── Warehouse CRUD ──────────────────────────────────────────────────────────


def list_warehouses(*, org_id: str | None) -> list[Warehouse]:
    db = get_firestore()
    q: gc_firestore.Query = db.collection(WAREHOUSES)
    if org_id:
        q = q.where(filter=gc_firestore.FieldFilter("orgId", "==", org_id))
    return [_doc_to_warehouse(d) for d in q.stream()]


def get_warehouse(wh_id: str) -> Warehouse | None:
    snap = get_firestore().collection(WAREHOUSES).document(wh_id).get()
    if not snap.exists:
        return None
    return _doc_to_warehouse(snap)


def create_warehouse(payload: WarehouseCreate, *, actor_uid: str, org_id: str) -> Warehouse:
    db = get_firestore()
    ref = db.collection(WAREHOUSES).document()
    doc: dict[str, Any] = {
        "name": payload.name,
        "location": fb_firestore.GeoPoint(payload.location.lat, payload.location.lng),
        "address": payload.address,
        "capacityKg": payload.capacityKg,
        "coldChainCapable": payload.coldChainCapable,
        "contactPhone": payload.contactPhone,
        "orgId": org_id,
        "createdAt": fb_firestore.SERVER_TIMESTAMP,
    }
    ref.set(doc)
    write_audit_log(
        actor_uid=actor_uid,
        action="warehouse.create",
        resource="warehouses",
        resource_id=ref.id,
        after={k: v for k, v in doc.items() if k not in ("location", "createdAt")},
        org_id=org_id,
    )
    return _doc_to_warehouse(ref.get())


def patch_warehouse(
    wh_id: str, body: WarehousePatch, *, actor_uid: str, org_id: str | None
) -> Warehouse:
    db = get_firestore()
    ref = db.collection(WAREHOUSES).document(wh_id)
    snap = ref.get()
    if not snap.exists:
        raise ApiError("WAREHOUSE_NOT_FOUND", f"warehouse {wh_id} not found", http_status.HTTP_404_NOT_FOUND)
    update = body.model_dump(exclude_none=True)
    if not update:
        return _doc_to_warehouse(snap)
    ref.update(update)
    write_audit_log(
        actor_uid=actor_uid,
        action="warehouse.patch",
        resource="warehouses",
        resource_id=wh_id,
        after=update,
        org_id=org_id or (snap.to_dict() or {}).get("orgId"),
    )
    return _doc_to_warehouse(ref.get())


# ── Inventory CRUD ──────────────────────────────────────────────────────────


def list_inventory(
    *,
    warehouse_id: str | None,
    expiring_within_days: int | None,
    sku: str | None = None,
    category: str | None = None,
    limit: int = 500,
) -> list[InventoryItem]:
    db = get_firestore()
    q: gc_firestore.Query = db.collection(INVENTORY)
    if warehouse_id:
        q = q.where(filter=gc_firestore.FieldFilter("warehouseId", "==", warehouse_id))
    if sku:
        q = q.where(filter=gc_firestore.FieldFilter("sku", "==", sku))
    if category:
        q = q.where(filter=gc_firestore.FieldFilter("category", "==", category))
    if expiring_within_days is not None:
        cutoff = datetime.now(timezone.utc) + timedelta(days=expiring_within_days)
        q = q.where(filter=gc_firestore.FieldFilter("expiry", "<=", cutoff))
    q = q.limit(limit)
    return [_doc_to_item(d) for d in q.stream()]


def create_inventory_item(
    payload: InventoryItemCreate, *, actor_uid: str, org_id: str
) -> InventoryItem:
    db = get_firestore()
    # Composite ID keeps lookups simple in tests + admin SDK scripts.
    iid = f"inv-{payload.warehouseId}-{payload.sku}".lower()
    ref = db.collection(INVENTORY).document(iid)
    doc: dict[str, Any] = {
        **payload.model_dump(),
        "reservedQty": 0,
        "updatedAt": fb_firestore.SERVER_TIMESTAMP,
    }
    ref.set(doc)
    write_audit_log(
        actor_uid=actor_uid,
        action="inventory.create",
        resource="inventory_items",
        resource_id=iid,
        after={k: v for k, v in doc.items() if k not in ("updatedAt",)},
        org_id=org_id,
    )
    return _doc_to_item(ref.get())


def patch_inventory_item(
    item_id: str, body: InventoryItemPatch, *, actor_uid: str, org_id: str | None
) -> InventoryItem:
    db = get_firestore()
    ref = db.collection(INVENTORY).document(item_id)
    snap = ref.get()
    if not snap.exists:
        raise ApiError("ITEM_NOT_FOUND", f"inventory item {item_id} not found", http_status.HTTP_404_NOT_FOUND)
    update = body.model_dump(exclude_none=True)
    if not update:
        return _doc_to_item(snap)
    update["updatedAt"] = fb_firestore.SERVER_TIMESTAMP
    ref.update(update)
    write_audit_log(
        actor_uid=actor_uid,
        action="inventory.patch",
        resource="inventory_items",
        resource_id=item_id,
        after=update,
        org_id=org_id,
    )
    return _doc_to_item(ref.get())


# ── Atomic reservation ─────────────────────────────────────────────────────


def reserve(
    *, warehouse_id: str, sku: str, qty: float, shipment_id: str | None, actor_uid: str, org_id: str | None
) -> ReserveResponseData:
    """Atomic Firestore transaction:
      - Find the inventory_items doc keyed by `(warehouseId, sku)`
      - If `qty >= requested`: subtract from `qty`, add to `reservedQty`, write
        a reservations doc.
      - Else: raise 409 INSUFFICIENT_STOCK with the available count.

    Concurrent reserves on the same item are serialized by Firestore's
    optimistic concurrency.
    """
    db = get_firestore()
    transaction = db.transaction()
    iid = f"inv-{warehouse_id}-{sku}".lower()
    item_ref = db.collection(INVENTORY).document(iid)
    reservation_ref = db.collection(RESERVATIONS).document()

    @fb_firestore.transactional
    def _txn(tx: fb_firestore.Transaction) -> dict[str, Any]:
        snap = item_ref.get(transaction=tx)
        if not snap.exists:
            raise ApiError(
                "ITEM_NOT_FOUND",
                f"No inventory_items entry for sku={sku} at warehouse={warehouse_id}.",
                http_status.HTTP_404_NOT_FOUND,
            )
        data = snap.to_dict() or {}
        available = float(data.get("qty") or 0.0)
        if available < qty:
            raise ApiError(
                "INSUFFICIENT_STOCK",
                f"Only {available} {sku} available at {warehouse_id}; cannot reserve {qty}.",
                http_status.HTTP_409_CONFLICT,
                details={"available": available, "requested": qty},
            )
        new_qty = available - qty
        new_reserved = float(data.get("reservedQty") or 0.0) + qty
        tx.update(item_ref, {
            "qty": new_qty,
            "reservedQty": new_reserved,
            "updatedAt": fb_firestore.SERVER_TIMESTAMP,
        })
        tx.set(reservation_ref, {
            "warehouseId": warehouse_id,
            "sku": sku,
            "qty": qty,
            "shipmentId": shipment_id,
            "actorUid": actor_uid,
            "orgId": org_id,
            "createdAt": fb_firestore.SERVER_TIMESTAMP,
            "status": "active",
        })
        return {
            "remainingQty": new_qty,
            "reservedQty": new_reserved,
            "reservationId": reservation_ref.id,
        }

    result = _txn(transaction)

    write_audit_log(
        actor_uid=actor_uid,
        action="inventory.reserve",
        resource="inventory_items",
        resource_id=iid,
        after={"qty_delta": -qty, "reservedQty_delta": qty, "shipmentId": shipment_id},
        org_id=org_id,
    )
    publisher.publish(
        "inventory.reserved",
        {"sku": sku, "qty": qty, "warehouseId": warehouse_id, "shipmentId": shipment_id or ""},
        org_id=org_id or "",
    )

    return ReserveResponseData(
        reservationId=result["reservationId"],
        warehouseId=warehouse_id,
        sku=sku,
        qty=qty,
        remainingQty=result["remainingQty"],
        reservedQty=result["reservedQty"],
    )


# ── Expiry monitor ─────────────────────────────────────────────────────────


def find_expiring(*, days: int, org_id: str | None = None) -> list[ExpiringItem]:
    """Return items expiring within `days` days, sorted by soonest first."""
    cutoff = datetime.now(timezone.utc) + timedelta(days=days)
    items = list_inventory(warehouse_id=None, expiring_within_days=days, limit=500)

    # Filter by org via the parent warehouse if requested.
    if org_id:
        whs = {w.id: w for w in list_warehouses(org_id=org_id)}
        items = [it for it in items if it.warehouseId in whs]

    out: list[ExpiringItem] = []
    now = datetime.now(timezone.utc)
    for it in items:
        delta = it.expiry - now
        days_left = max(0, delta.days)
        if days_left <= 1:
            severity: int = 5
        elif days_left <= 3:
            severity = 4
        elif days_left <= 7:
            severity = 3
        elif days_left <= 14:
            severity = 2
        else:
            severity = 1
        out.append(ExpiringItem(item=it, daysToExpiry=days_left, severity=severity))  # type: ignore[arg-type]
    out.sort(key=lambda e: e.daysToExpiry)
    return out


def write_expiry_alert(expiring: list[ExpiringItem], *, org_id: str | None) -> str | None:
    """Aggregate expiring items into a single `alerts` doc per call.

    Designed to be invoked by the daily Cloud Scheduler job (COMMIT 10) — the
    job either calls `/api/inventory/expiring?days=7` then this helper, or
    we add a sibling endpoint that does both in one step.
    """
    if not expiring:
        return None
    db = get_firestore()
    most_severe = max((e.severity for e in expiring), default=1)
    headline = (
        f"{len(expiring)} inventory items expire in ≤ {expiring[-1].daysToExpiry} days"
    )
    ref = db.collection(ALERTS).document()
    ref.set(
        {
            "type": "other",  # 'expiry' isn't in the disaster-alert enum
            "subtype": "inventory_expiry",
            "severity": most_severe,
            "headline": headline,
            "source": "inventory_monitor",
            "classifiedBy": "human",
            "detectedAt": fb_firestore.SERVER_TIMESTAMP,
            "affectedItems": [e.item.id for e in expiring][:50],
            "resolved": False,
            "orgId": org_id,
        }
    )
    publisher.publish(
        "alert.created",
        {"alertId": ref.id, "type": "inventory_expiry", "severity": most_severe},
        org_id=org_id or "",
    )
    log.info("inventory.expiry_alert", alert_id=ref.id, items=len(expiring), severity=most_severe)
    return ref.id


# ── Stock summary ──────────────────────────────────────────────────────────


def stock_summary(*, org_id: str | None) -> list[WarehouseStockSummary]:
    """Per-warehouse rollup used by /warehouses list page."""
    whs = list_warehouses(org_id=org_id)
    if not whs:
        return []
    items = list_inventory(warehouse_id=None, expiring_within_days=None, limit=2000)
    by_wh: dict[str, list[InventoryItem]] = {}
    for it in items:
        by_wh.setdefault(it.warehouseId, []).append(it)

    cutoff = datetime.now(timezone.utc) + timedelta(days=7)
    out: list[WarehouseStockSummary] = []
    for wh in whs:
        inv = by_wh.get(wh.id, [])
        total_kg = sum(it.qty * it.unitWeight_kg for it in inv)
        cats: dict[str, float] = {}
        for it in inv:
            cats[it.category] = cats.get(it.category, 0.0) + it.qty
        expiring_soon = sum(1 for it in inv if it.expiry <= cutoff)
        out.append(
            WarehouseStockSummary(
                warehouseId=wh.id,
                name=wh.name,
                address=wh.address,
                location=wh.location,
                coldChainCapable=wh.coldChainCapable,
                capacityKg=wh.capacityKg,
                totalQty=sum(it.qty for it in inv),
                totalReservedQty=sum(it.reservedQty for it in inv),
                totalKgInStock=round(total_kg, 2),
                itemsByCategory=cats,
                distinctSkus=len({it.sku for it in inv}),
                expiringSoon=expiring_soon,
            )
        )
    return out
