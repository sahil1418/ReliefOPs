"""Inventory + warehouses routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from src.core.auth import CurrentUser
from src.core.errors import ApiError, ApiResponse
from src.core.rbac import require_admin, require_admin_or_coord
from src.modules.inventory import service
from src.modules.inventory.models import (
    ExpiringItem,
    ExpiryAlertResponseData,
    InventoryItem,
    InventoryItemCreate,
    InventoryItemPatch,
    ReserveRequest,
    ReserveResponseData,
    Warehouse,
    WarehouseCreate,
    WarehousePatch,
    WarehouseStockSummary,
)

router = APIRouter(prefix="/api", tags=["inventory"])


# ── Warehouses ──────────────────────────────────────────────────────────────


class WarehouseListPayload(ApiResponse[list[Warehouse]]):
    pass


class WarehousePayload(ApiResponse[Warehouse]):
    pass


class WarehouseStockPayload(ApiResponse[list[WarehouseStockSummary]]):
    pass


@router.get("/warehouses", response_model=WarehouseListPayload)
async def list_warehouses(user: CurrentUser) -> WarehouseListPayload:
    org_id = user.org_id if user.role != "super_admin" else None
    rows = service.list_warehouses(org_id=org_id)
    return WarehouseListPayload(data=rows)


@router.get("/warehouses/stock", response_model=WarehouseStockPayload)
async def warehouses_stock(user: CurrentUser) -> WarehouseStockPayload:
    org_id = user.org_id if user.role != "super_admin" else None
    rows = service.stock_summary(org_id=org_id)
    return WarehouseStockPayload(data=rows)


@router.get("/warehouses/{wh_id}", response_model=WarehousePayload)
async def get_warehouse(wh_id: str, _user: CurrentUser) -> WarehousePayload:
    wh = service.get_warehouse(wh_id)
    if not wh:
        raise ApiError("WAREHOUSE_NOT_FOUND", f"warehouse {wh_id} not found", status.HTTP_404_NOT_FOUND)
    return WarehousePayload(data=wh)


@router.post(
    "/warehouses",
    response_model=WarehousePayload,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_warehouse(payload: WarehouseCreate, user: CurrentUser) -> WarehousePayload:
    if not user.org_id:
        raise ApiError("NO_ORG", "Caller has no orgId claim.", status.HTTP_400_BAD_REQUEST)
    wh = service.create_warehouse(payload, actor_uid=user.uid, org_id=user.org_id)
    return WarehousePayload(data=wh)


@router.patch(
    "/warehouses/{wh_id}",
    response_model=WarehousePayload,
    dependencies=[Depends(require_admin)],
)
async def patch_warehouse(
    wh_id: str, body: WarehousePatch, user: CurrentUser
) -> WarehousePayload:
    wh = service.patch_warehouse(wh_id, body, actor_uid=user.uid, org_id=user.org_id)
    return WarehousePayload(data=wh)


# ── Inventory items ─────────────────────────────────────────────────────────


class InventoryListPayload(ApiResponse[list[InventoryItem]]):
    pass


class InventoryItemPayload(ApiResponse[InventoryItem]):
    pass


@router.get("/warehouses/{wh_id}/inventory", response_model=InventoryListPayload)
async def warehouse_inventory(
    wh_id: str,
    _user: CurrentUser,
    expiringWithinDays: int | None = Query(default=None, ge=0, le=3650),
    sku: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
) -> InventoryListPayload:
    rows = service.list_inventory(
        warehouse_id=wh_id,
        expiring_within_days=expiringWithinDays,
        sku=sku,
        category=category,
        limit=limit,
    )
    return InventoryListPayload(data=rows)


@router.post(
    "/inventory",
    response_model=InventoryItemPayload,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_coord)],
)
async def create_inventory_item(
    payload: InventoryItemCreate, user: CurrentUser
) -> InventoryItemPayload:
    if not user.org_id:
        raise ApiError("NO_ORG", "Caller has no orgId claim.", status.HTTP_400_BAD_REQUEST)
    item = service.create_inventory_item(payload, actor_uid=user.uid, org_id=user.org_id)
    return InventoryItemPayload(data=item)


@router.patch(
    "/inventory/{item_id}",
    response_model=InventoryItemPayload,
    dependencies=[Depends(require_admin_or_coord)],
)
async def patch_inventory_item(
    item_id: str, body: InventoryItemPatch, user: CurrentUser
) -> InventoryItemPayload:
    item = service.patch_inventory_item(item_id, body, actor_uid=user.uid, org_id=user.org_id)
    return InventoryItemPayload(data=item)


# ── Reservation ─────────────────────────────────────────────────────────────


class ReservePayload(ApiResponse[ReserveResponseData]):
    pass


@router.post(
    "/inventory/reserve",
    response_model=ReservePayload,
    dependencies=[Depends(require_admin_or_coord)],
)
async def reserve_inventory(
    body: ReserveRequest, user: CurrentUser
) -> ReservePayload:
    """Atomic Firestore transaction. Returns 409 INSUFFICIENT_STOCK on overflow."""
    data = service.reserve(
        warehouse_id=body.warehouseId,
        sku=body.sku,
        qty=body.qty,
        shipment_id=body.shipmentId,
        actor_uid=user.uid,
        org_id=user.org_id,
    )
    return ReservePayload(data=data)


# ── Expiry monitor ──────────────────────────────────────────────────────────


class ExpiringListPayload(ApiResponse[list[ExpiringItem]]):
    pass


class ExpiryAlertPayload(ApiResponse[ExpiryAlertResponseData]):
    pass


@router.get("/inventory/expiring", response_model=ExpiringListPayload)
async def list_expiring(
    user: CurrentUser,
    days: int = Query(default=7, ge=1, le=365),
) -> ExpiringListPayload:
    org_id = user.org_id if user.role != "super_admin" else None
    rows = service.find_expiring(days=days, org_id=org_id)
    return ExpiringListPayload(data=rows)


@router.post(
    "/inventory/expiring/alert",
    response_model=ExpiryAlertPayload,
    dependencies=[Depends(require_admin_or_coord)],
)
async def create_expiry_alert(
    user: CurrentUser,
    days: int = Query(default=7, ge=1, le=365),
) -> ExpiryAlertPayload:
    """Compute expiring items + write a single aggregated `alerts` doc. Designed
    to be called by the daily Cloud Scheduler cron (COMMIT 10)."""
    expiring = service.find_expiring(days=days, org_id=user.org_id)
    alert_id = service.write_expiry_alert(expiring, org_id=user.org_id)
    return ExpiryAlertPayload(
        data=ExpiryAlertResponseData(alertId=alert_id, itemsAffected=len(expiring))
    )
