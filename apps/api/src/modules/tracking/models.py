"""Pydantic models for live GPS tracking."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.modules.disasters.models import GeoPoint


class TrackingEventCreate(BaseModel):
    """Volunteer-side post body. The server fills volunteerId from the auth token."""

    shipmentId: str | None = Field(default=None)
    location: GeoPoint
    speedKmh: float = Field(default=0, ge=0, le=400)
    accuracy: float = Field(default=0, ge=0, le=10000, description="meters")
    heading: float | None = Field(default=None, ge=0, lt=360)


class TrackingEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    shipmentId: str | None = None
    volunteerId: str
    location: GeoPoint
    ts: datetime
    speedKmh: float = 0
    accuracy: float = 0
    heading: float | None = None
