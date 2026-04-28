"""Admin-only routes for ops triggers (disruption monitor, etc.)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.core.auth import CurrentUser
from src.core.errors import ApiResponse
from src.core.rbac import require_admin
from src.workers import disruption_monitor

router = APIRouter(prefix="/api/admin", tags=["admin"])


class DisruptionRunResult(BaseModel):
    ok: bool
    alertsWritten: int
    shipmentsRerouted: int
    alertIds: list[str] = []


class DisruptionRunPayload(ApiResponse[DisruptionRunResult]):
    pass


@router.post(
    "/disruption/run",
    response_model=DisruptionRunPayload,
    dependencies=[Depends(require_admin)],
)
async def disruption_run(
    user: CurrentUser, country: str = "BGD"
) -> DisruptionRunPayload:
    """Trigger the disruption monitor cron path manually.

    Cloud Scheduler will hit this endpoint daily once Cloud Run is wired.
    """
    result = await disruption_monitor.run_once(actor_uid=user.uid, country_iso=country)
    return DisruptionRunPayload(data=DisruptionRunResult(**result))


class InjectAlertRequest(BaseModel):
    headline: str = Field(..., min_length=1, max_length=200)
    severity: int = Field(..., ge=1, le=5)
    lat: float
    lng: float
    orgId: str | None = None


class InjectResult(BaseModel):
    ok: bool
    alertId: str
    shipmentsRerouted: int
    affectedShipmentIds: list[str] = []


class InjectPayload(ApiResponse[InjectResult]):
    pass


@router.post(
    "/disruption/inject",
    response_model=InjectPayload,
    dependencies=[Depends(require_admin)],
)
async def disruption_inject(body: InjectAlertRequest, user: CurrentUser) -> InjectPayload:
    """Demo-time controllable disruption: stage hits this with a one-click alert."""
    result = await disruption_monitor.inject_demo_alert(
        headline=body.headline,
        severity=body.severity,
        lat=body.lat,
        lng=body.lng,
        org_id=body.orgId or user.org_id,
        actor_uid=user.uid,
    )
    return InjectPayload(data=InjectResult(**result))
