"""Pydantic models for the demand_requests module."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.modules.disasters.models import GeoPoint

DemandSource = Literal["app", "sms", "web", "satellite", "news"]
DemandStatus = Literal["pending", "matched", "shipped", "delivered"]
DemandSeverity = Literal["critical", "high", "medium", "low"]
DemandCategory = Literal["food", "medicine", "shelter", "water", "rescue", "other"]


class DemandItem(BaseModel):
    sku: str = Field(..., min_length=1)
    qty: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1)


class DemandRequestCreate(BaseModel):
    """Body of `POST /api/requests` — disasterId optional, classified inline."""

    disasterId: str | None = None
    items: list[DemandItem] | None = None  # If omitted, the classifier extracts from `raw`.
    location: GeoPoint
    raw: str = Field(..., min_length=1, max_length=2000)
    photos: list[str] = Field(default_factory=list, max_length=3)
    source: DemandSource = "web"


class ClassifiedRequest(BaseModel):
    """The Gemini-output schema; mirrors the schema we send to Flash."""

    items: list[DemandItem]
    urgency: int = Field(..., ge=1, le=5)
    severity: DemandSeverity
    category: DemandCategory
    confidence: float = Field(..., ge=0, le=1)
    summary: str = Field(default="", max_length=300)


class DemandRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    disasterId: str | None
    source: DemandSource
    requesterId: str | None = None
    items: list[DemandItem]
    location: GeoPoint
    urgency: int
    severity: DemandSeverity
    category: DemandCategory | None = None
    raw: str
    photos: list[str] = Field(default_factory=list)
    createdAt: datetime
    status: DemandStatus
    classifiedBy: Literal["gemini", "human"]
    confidence: float = 0.0
    orgId: str | None = None
