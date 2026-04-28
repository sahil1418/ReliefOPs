"""Tracking routes — /api/tracking/event + /api/tracking/{shipmentId}."""
from __future__ import annotations

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from src.core.auth import CurrentUser
from src.core.errors import ApiResponse
from src.modules.tracking import service
from src.modules.tracking.models import TrackingEvent, TrackingEventCreate

router = APIRouter(prefix="/api/tracking", tags=["tracking"])


class TrackingEventResponseData(BaseModel):
    ok: bool
    aggregated: bool
    lastEventTs: str


class TrackingEventResponse(ApiResponse[TrackingEventResponseData]):
    pass


class TrackingListResponse(ApiResponse[list[TrackingEvent]]):
    pass


@router.post("/event", response_model=TrackingEventResponse, status_code=status.HTTP_200_OK)
async def post_event(payload: TrackingEventCreate, user: CurrentUser) -> TrackingEventResponse:
    data = service.record_event(payload, volunteer_uid=user.uid, actor_role=user.role)
    return TrackingEventResponse(data=TrackingEventResponseData(**data))


@router.get("/{shipment_id}", response_model=TrackingListResponse)
async def list_events(
    shipment_id: str,
    user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=1000),
) -> TrackingListResponse:
    rows = service.list_events(
        shipment_id=shipment_id,
        limit=limit,
        requester_uid=user.uid,
        requester_role=user.role,
    )
    return TrackingListResponse(data=rows)
