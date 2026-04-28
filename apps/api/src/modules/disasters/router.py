"""Disasters routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from src.core.auth import CurrentUser
from src.core.errors import ApiError, ApiResponse
from src.core.rbac import require_admin_or_coord
from src.modules.disasters import service
from src.modules.disasters.models import (
    Disaster,
    DisasterCreate,
    DisasterPatch,
    DisasterStatus,
)

router = APIRouter(prefix="/api/disasters", tags=["disasters"])


class DisasterListPayload(ApiResponse[list[Disaster]]):
    pass


class DisasterPayload(ApiResponse[Disaster]):
    pass


@router.get("", response_model=DisasterListPayload)
async def list_disasters(
    user: CurrentUser,
    status_q: DisasterStatus | None = Query(default=None, alias="status"),
    org_id_q: str | None = Query(default=None, alias="orgId"),
    limit: int = Query(default=100, ge=1, le=500),
) -> DisasterListPayload:
    org_id = org_id_q or (user.org_id if user.role != "super_admin" else None)
    rows = service.list_disasters(status=status_q, org_id=org_id, limit=limit)
    return DisasterListPayload(data=rows)


@router.post(
    "",
    response_model=DisasterPayload,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_coord)],
)
async def create_disaster(payload: DisasterCreate, user: CurrentUser) -> DisasterPayload:
    if not user.org_id:
        raise ApiError(
            code="NO_ORG",
            message="Caller has no orgId claim — call /api/auth/set-role first.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    disaster = service.create_disaster(payload, actor_uid=user.uid, org_id=user.org_id)
    return DisasterPayload(data=disaster)


@router.get("/{disaster_id}", response_model=DisasterPayload)
async def get_disaster(disaster_id: str, _user: CurrentUser) -> DisasterPayload:
    disaster = service.get_disaster(disaster_id)
    if not disaster:
        raise ApiError(
            code="DISASTER_NOT_FOUND",
            message=f"disaster {disaster_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DisasterPayload(data=disaster)


@router.patch(
    "/{disaster_id}",
    response_model=DisasterPayload,
    dependencies=[Depends(require_admin_or_coord)],
)
async def patch_disaster(
    disaster_id: str, body: DisasterPatch, user: CurrentUser
) -> DisasterPayload:
    disaster = service.patch_disaster(
        disaster_id, body, actor_uid=user.uid, org_id=user.org_id
    )
    return DisasterPayload(data=disaster)
