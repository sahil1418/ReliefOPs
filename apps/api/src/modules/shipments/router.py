"""Shipments routes — GET / POST / PATCH /:id/status / POST /:id/assign."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from src.core.auth import CurrentUser
from src.core.errors import ApiError, ApiResponse
from src.core.rbac import require_admin_or_coord
from src.modules.shipments import service
from src.modules.shipments.models import (
    Shipment,
    ShipmentAssign,
    ShipmentCreate,
    ShipmentListFilters,
    ShipmentStatus,
    ShipmentStatusUpdate,
)

router = APIRouter(prefix="/api/shipments", tags=["shipments"])


class ShipmentListPayload(ApiResponse[list[Shipment]]):
    pass


class ShipmentPayload(ApiResponse[Shipment]):
    pass


@router.get("", response_model=ShipmentListPayload)
async def list_shipments(
    user: CurrentUser,
    status_q: ShipmentStatus | None = Query(default=None, alias="status"),
    disasterId: str | None = Query(default=None),
    volunteerId: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> ShipmentListPayload:
    filters = ShipmentListFilters(
        status=status_q, disasterId=disasterId, volunteerId=volunteerId, limit=limit
    )
    rows = service.list_shipments(
        filters=filters,
        requester_uid=user.uid,
        requester_role=user.role,
        requester_org_id=user.org_id,
    )
    return ShipmentListPayload(data=rows)


@router.post(
    "",
    response_model=ShipmentPayload,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_coord)],
)
async def create_shipment(payload: ShipmentCreate, user: CurrentUser) -> ShipmentPayload:
    if not user.org_id:
        raise ApiError(
            code="NO_ORG",
            message="Caller has no orgId claim — call /api/auth/set-role first.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    ship = service.create_shipment(payload, actor_uid=user.uid, actor_org_id=user.org_id)
    return ShipmentPayload(data=ship)


@router.get("/{shipment_id}", response_model=ShipmentPayload)
async def get_shipment(shipment_id: str, _user: CurrentUser) -> ShipmentPayload:
    ship = service.get_shipment(shipment_id)
    if not ship:
        raise ApiError(
            code="SHIPMENT_NOT_FOUND",
            message=f"shipment {shipment_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return ShipmentPayload(data=ship)


@router.patch("/{shipment_id}/status", response_model=ShipmentPayload)
async def update_status(
    shipment_id: str, body: ShipmentStatusUpdate, user: CurrentUser
) -> ShipmentPayload:
    ship = service.update_status(
        shipment_id,
        body,
        actor_uid=user.uid,
        actor_role=user.role,
        actor_org_id=user.org_id,
    )
    return ShipmentPayload(data=ship)


@router.post(
    "/{shipment_id}/assign",
    response_model=ShipmentPayload,
    dependencies=[Depends(require_admin_or_coord)],
)
async def assign(
    shipment_id: str, body: ShipmentAssign, user: CurrentUser
) -> ShipmentPayload:
    ship = service.assign_volunteer(
        shipment_id, body.volunteerId, actor_uid=user.uid, actor_org_id=user.org_id
    )
    return ShipmentPayload(data=ship)
