"""Pydantic models for the disasters module.

Firestore can't store nested arrays directly, so the GeoJSON polygon ring is
held as `{type: 'Polygon', rings: [{points: [{lat, lng}, ...]}]}` plus a flat
`bbox` for fast geospatial queries. Same shape the seed produces.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DisasterType = Literal["flood", "earthquake", "cyclone", "heatwave", "drought", "other"]
DisasterStatus = Literal["active", "contained", "closed"]


class GeoPoint(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class PolygonRing(BaseModel):
    points: list[GeoPoint]


class GeoPolygon(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    rings: list[PolygonRing]


class Bbox(BaseModel):
    west: float
    south: float
    east: float
    north: float


class DisasterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: DisasterType
    geo: GeoPolygon
    bbox: Bbox
    severityScale: Literal[1, 2, 3, 4, 5] = 3
    affectedPopulationEstimate: int = Field(default=0, ge=0)
    sdgTags: list[str] = Field(default_factory=lambda: ["SDG2", "SDG3", "SDG11", "SDG13"])


class DisasterPatch(BaseModel):
    status: DisasterStatus | None = None
    severityScale: Literal[1, 2, 3, 4, 5] | None = None
    affectedPopulationEstimate: int | None = Field(default=None, ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=200)


class Disaster(DisasterCreate):
    model_config = ConfigDict(extra="ignore")

    id: str
    declaredAt: datetime
    declaredBy: str
    status: DisasterStatus
    orgId: str
    geoJson: str | None = None
