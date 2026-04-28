"""Inventory + reservation tests.

The atomic-reserve test runs against a fresh Firestore emulator. It's gated by
a probe so CI without an emulator running auto-skips.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from src.core.errors import ApiError
from src.modules.inventory import service as inv_service
from src.modules.inventory.models import ExpiringItem, InventoryItem


def _emulator_running() -> bool:
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    try:
        httpx.get(f"http://{host}", timeout=0.5)
        return True
    except Exception:  # noqa: BLE001
        return False


needs_emulator = pytest.mark.skipif(
    not _emulator_running(), reason="Needs Firestore emulator running on 127.0.0.1:8080"
)


def _seed_item(
    *, warehouse_id: str, sku: str, qty: float, days_to_expiry: int = 30
) -> str:
    """Direct Admin-SDK write so the test isn't coupled to the create_inventory_item route."""
    from firebase_admin import firestore as fb_firestore

    from src.core.firebase import get_firestore

    db = get_firestore()
    iid = f"inv-{warehouse_id}-{sku}".lower()
    db.collection("inventory_items").document(iid).set({
        "warehouseId": warehouse_id,
        "sku": sku,
        "name": f"test {sku}",
        "category": "food",
        "qty": qty,
        "reservedQty": 0,
        "expiry": datetime.now(timezone.utc) + timedelta(days=days_to_expiry),
        "coldChainRequired": False,
        "unitWeight_kg": 1.0,
        "updatedAt": fb_firestore.SERVER_TIMESTAMP,
    })
    return iid


@needs_emulator
def test_reserve_decrements_qty_and_increments_reserved() -> None:
    iid = _seed_item(warehouse_id="wh-test", sku="TEST-RICE", qty=200)

    out = inv_service.reserve(
        warehouse_id="wh-test",
        sku="TEST-RICE",
        qty=50,
        shipment_id="ship-x",
        actor_uid="tester",
        org_id="org-test",
    )
    assert out.remainingQty == 150
    assert out.reservedQty == 50
    assert out.reservationId

    # Read back to confirm Firestore really updated.
    from src.core.firebase import get_firestore
    snap = get_firestore().collection("inventory_items").document(iid).get()
    data = snap.to_dict() or {}
    assert data["qty"] == 150
    assert data["reservedQty"] == 50


@needs_emulator
def test_reserve_409_on_insufficient_stock() -> None:
    _seed_item(warehouse_id="wh-test2", sku="TINY-SKU", qty=10)
    with pytest.raises(ApiError) as excinfo:
        inv_service.reserve(
            warehouse_id="wh-test2",
            sku="TINY-SKU",
            qty=50,
            shipment_id=None,
            actor_uid="tester",
            org_id="org-test",
        )
    assert excinfo.value.code == "INSUFFICIENT_STOCK"
    assert excinfo.value.status_code == 409
    assert excinfo.value.details
    assert excinfo.value.details["available"] == 10
    assert excinfo.value.details["requested"] == 50


@needs_emulator
def test_reserve_404_when_sku_absent() -> None:
    with pytest.raises(ApiError) as excinfo:
        inv_service.reserve(
            warehouse_id="wh-test",
            sku="NOPE-SKU",
            qty=1,
            shipment_id=None,
            actor_uid="tester",
            org_id="org-test",
        )
    assert excinfo.value.code == "ITEM_NOT_FOUND"
    assert excinfo.value.status_code == 404


@needs_emulator
def test_find_expiring_orders_and_grades_severity() -> None:
    _seed_item(warehouse_id="wh-exp", sku="ALMOST-OUT", qty=100, days_to_expiry=2)
    _seed_item(warehouse_id="wh-exp", sku="SOON-OUT", qty=100, days_to_expiry=5)
    _seed_item(warehouse_id="wh-exp", sku="FINE-FOR-NOW", qty=100, days_to_expiry=180)

    expiring = inv_service.find_expiring(days=7)
    skus = [e.item.sku for e in expiring]
    assert "ALMOST-OUT" in skus
    assert "SOON-OUT" in skus
    assert "FINE-FOR-NOW" not in skus

    almost = next(e for e in expiring if e.item.sku == "ALMOST-OUT")
    soon = next(e for e in expiring if e.item.sku == "SOON-OUT")
    # Tighter window → higher severity.
    assert almost.severity > soon.severity
    assert almost.daysToExpiry < soon.daysToExpiry
