"""Pydantic models for the shipments module.

Mirrors the Firestore schema in BLUEPRINT.md Phase 8 / Phase 6 Module 4.
GeoPoints are serialized as plain {lat, lng} dicts on the wire — the service
layer converts to/from `firebase_admin.firestore.GeoPoint` when persisting.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ShipmentStatus = Literal["created", "assigned", "in_transit", "delivered", "failed"]
Priority = Literal["critical", "high", "normal"]


class GeoPointJson(BaseModel):
    """Wire format for a Firestore GeoPoint."""

    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class ShipmentItem(BaseModel):
    sku: str = Field(..., min_length=1)
    qty: int = Field(..., gt=0)
    unit: str = Field(..., min_length=1)
    warehouseId: str | None = Field(default=None)
    unitWeight_kg: float | None = Field(default=None, ge=0)


class ShipmentCreate(BaseModel):
    """Payload accepted by `POST /api/shipments`."""

    disasterId: str = Field(..., min_length=1)
    requestIds: list[str] = Field(default_factory=list)
    items: list[ShipmentItem] = Field(..., min_length=1)
    originWarehouseId: str = Field(..., min_length=1)
    dropoffLocation: GeoPointJson
    dropoffAddress: str = Field(..., min_length=1)
    priority: Priority = "normal"
    requiredSkills: list[str] = Field(default_factory=list)


class ShipmentStatusUpdate(BaseModel):
    status: ShipmentStatus
    note: str | None = Field(default=None, max_length=500)


class ShipmentAssign(BaseModel):
    volunteerId: str = Field(..., min_length=1)


class Shipment(BaseModel):
    """Full Firestore document representation."""

    model_config = ConfigDict(extra="ignore")

    id: str
    disasterId: str
    requestIds: list[str] = Field(default_factory=list)
    items: list[ShipmentItem]
    totalKg: float
    originWarehouseId: str
    dropoffLocation: GeoPointJson
    dropoffAddress: str
    priority: Priority
    status: ShipmentStatus
    assignedVolunteerId: str | None = None
    vehicleId: str | None = None
    routeId: str | None = None
    etaInitial: datetime | None = None
    etaCurrent: datetime | None = None
    delayPredictedMin: int | None = None
    delayConfidence: float | None = None
    co2KgEstimate: float | None = None
    createdAt: datetime
    deliveredAt: datetime | None = None
    orgId: str
    requiredSkills: list[str] = Field(default_factory=list)

    @field_validator("dropoffLocation", mode="before")
    @classmethod
    def _coerce_geopoint(cls, v: Any) -> Any:  # noqa: ANN401
        # Firestore GeoPoint comes back with .latitude / .longitude attributes.
        if hasattr(v, "latitude") and hasattr(v, "longitude"):
            return {"lat": v.latitude, "lng": v.longitude}
        return v


class ShipmentListFilters(BaseModel):
    status: ShipmentStatus | None = None
    disasterId: str | None = None
    volunteerId: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
