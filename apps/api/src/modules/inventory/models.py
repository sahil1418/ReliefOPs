"""Pydantic models for warehouses + inventory_items."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.modules.disasters.models import GeoPoint

ItemCategory = Literal["food", "medicine", "shelter", "water", "rescue", "other"]


class WarehouseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    location: GeoPoint
    address: str = Field(..., min_length=1, max_length=300)
    capacityKg: float = Field(..., gt=0)
    coldChainCapable: bool = False
    contactPhone: str | None = None


class WarehousePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    capacityKg: float | None = Field(default=None, gt=0)
    coldChainCapable: bool | None = None
    contactPhone: str | None = None


class Warehouse(WarehouseCreate):
    model_config = ConfigDict(extra="ignore")
    id: str
    orgId: str
    createdAt: datetime | None = None


class InventoryItemCreate(BaseModel):
    warehouseId: str = Field(..., min_length=1)
    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    category: ItemCategory
    qty: float = Field(..., ge=0)
    lot: str | None = None
    expiry: datetime
    coldChainRequired: bool = False
    unitWeight_kg: float = Field(..., gt=0)


class InventoryItemPatch(BaseModel):
    qty: float | None = Field(default=None, ge=0)
    reservedQty: float | None = Field(default=None, ge=0)
    expiry: datetime | None = None
    coldChainRequired: bool | None = None
    unitWeight_kg: float | None = Field(default=None, gt=0)


class InventoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    warehouseId: str
    sku: str
    name: str
    category: ItemCategory
    qty: float
    reservedQty: float = 0
    lot: str | None = None
    expiry: datetime
    coldChainRequired: bool = False
    unitWeight_kg: float = 1.0
    updatedAt: datetime | None = None


class ReserveRequest(BaseModel):
    warehouseId: str = Field(..., min_length=1)
    sku: str = Field(..., min_length=1)
    qty: float = Field(..., gt=0)
    shipmentId: str | None = None


class ReserveResponseData(BaseModel):
    ok: bool = True
    reservationId: str
    warehouseId: str
    sku: str
    qty: float
    remainingQty: float
    reservedQty: float


class ExpiringItem(BaseModel):
    item: InventoryItem
    daysToExpiry: int
    severity: Literal[1, 2, 3, 4, 5]


class ExpiryAlertResponseData(BaseModel):
    alertId: str | None
    itemsAffected: int


class WarehouseStockSummary(BaseModel):
    warehouseId: str
    name: str
    address: str
    location: GeoPoint
    coldChainCapable: bool
    capacityKg: float
    totalQty: float = 0
    totalReservedQty: float = 0
    totalKgInStock: float = 0
    itemsByCategory: dict[str, float] = Field(default_factory=dict)  # category → qty
    distinctSkus: int = 0
    expiringSoon: int = 0  # items expiring in <= 7 days
