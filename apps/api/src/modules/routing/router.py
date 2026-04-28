"""Routes API: optimize / get / reroute."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.core.auth import CurrentUser
from src.core.errors import ApiError, ApiResponse
from src.core.rbac import require_admin_or_coord
from src.modules.routing import service
from src.modules.routing.models import OptimizeRequest, Route

router = APIRouter(prefix="/api/routes", tags=["routes"])


class RouteListPayload(ApiResponse[list[Route]]):
    pass


class RoutePayload(ApiResponse[Route]):
    pass


@router.post(
    "/optimize",
    response_model=RouteListPayload,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin_or_coord)],
)
async def optimize(payload: OptimizeRequest, user: CurrentUser) -> RouteListPayload:
    if not user.org_id:
        raise ApiError(
            code="NO_ORG",
            message="Caller has no orgId claim — call /api/auth/set-role first.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    routes = await service.optimize_routes(payload, actor_uid=user.uid, org_id=user.org_id)
    return RouteListPayload(data=routes)


@router.get("/{route_id}", response_model=RoutePayload)
async def get_route(route_id: str, _user: CurrentUser) -> RoutePayload:
    route = service.get_route(route_id)
    if not route:
        raise ApiError(
            code="ROUTE_NOT_FOUND",
            message=f"route {route_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return RoutePayload(data=route)


@router.post(
    "/{route_id}/reroute",
    response_model=RoutePayload,
    dependencies=[Depends(require_admin_or_coord)],
)
async def reroute(
    route_id: str, body: OptimizeRequest, user: CurrentUser
) -> RoutePayload:
    """Force re-optimization of an existing route — typically triggered by a
    `disruption.detected` event in COMMIT 10. For COMMIT 6 it just re-runs the
    solver with the supplied request and returns the first new route.
    """
    if not user.org_id:
        raise ApiError(
            code="NO_ORG",
            message="Caller has no orgId claim.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    routes = await service.optimize_routes(body, actor_uid=user.uid, org_id=user.org_id)
    if not routes:
        raise ApiError(
            code="NO_ROUTE",
            message="Re-optimization produced no routes.",
            status_code=status.HTTP_409_CONFLICT,
        )
    return RoutePayload(data=routes[0])
