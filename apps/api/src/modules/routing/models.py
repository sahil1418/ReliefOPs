"""Pydantic models for the routing module."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.modules.disasters.models import GeoPoint
from src.modules.shipments.models import Priority

StopType = Literal["pickup", "dropoff", "depot"]


class TimeWindow(BaseModel):
    """ISO-8601 timestamps. If omitted, defaults to "any time today"."""

    start: datetime | None = None
    end: datetime | None = None


class OptimizeStop(BaseModel):
    """A single shipment we want delivered (pickup→dropoff pair).

    For COMMIT 6 we treat each shipment as one stop at its dropoffLocation;
    pickup at the warehouse is handled implicitly via the depot. Multi-pickup
    routing lands when we add multi-warehouse fan-out in a later iteration.
    """

    shipmentId: str
    location: GeoPoint
    address: str = ""
    demand_kg: float = Field(default=0.0, ge=0)
    priority: Priority = "normal"
    serviceMin: int = Field(default=10, ge=0, description="Minutes spent at the stop")
    timeWindow: TimeWindow | None = None


class OptimizeVehicle(BaseModel):
    vehicleId: str
    volunteerId: str | None = None
    capacityKg: float = Field(..., gt=0)
    avgSpeedKmh: float = 30.0
    startLocation: GeoPoint  # Usually the origin warehouse.
    endLocation: GeoPoint | None = None  # Defaults to startLocation if absent.


class OptimizeRequest(BaseModel):
    shipmentIds: list[str] = Field(..., min_length=1)
    vehicleIds: list[str] = Field(..., min_length=1)
    blockedAreas: list[dict] = Field(
        default_factory=list,
        description="GeoJSON Polygons (in our `{rings:[{points:[]}]}` shape) to avoid.",
    )
    curfewWindows: list[TimeWindow] = Field(default_factory=list)
    timeLimitSeconds: int = Field(default=8, ge=1, le=60)


class RouteStop(BaseModel):
    location: GeoPoint
    address: str = ""
    etaArrive: datetime
    etaDepart: datetime
    shipmentId: str
    stopType: StopType


class Route(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    shipmentIds: list[str]
    vehicleId: str
    volunteerId: str | None = None
    stops: list[RouteStop]
    totalKm: float
    totalMin: int
    polyline: str = ""
    computedBy: Literal["gmpro", "ortools"] = "ortools"
    blockedAreasApplied: bool = False
    createdAt: datetime
    orgId: str | None = None
