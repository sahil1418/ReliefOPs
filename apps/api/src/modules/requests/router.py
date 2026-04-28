"""Demand requests routes — including the Twilio SMS webhook."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import Response

from src.core.auth import CurrentUser
from src.core.errors import ApiError, ApiResponse
from src.core.logging import get_logger
from src.modules.disasters.models import GeoPoint
from src.modules.requests import service
from src.modules.requests.models import (
    DemandRequest,
    DemandRequestCreate,
    DemandStatus,
)

log = get_logger("relief.requests.router")

router = APIRouter(prefix="/api/requests", tags=["requests"])


class DemandListPayload(ApiResponse[list[DemandRequest]]):
    pass


class DemandPayload(ApiResponse[DemandRequest]):
    pass


@router.get("", response_model=DemandListPayload)
async def list_requests(
    user: CurrentUser,
    disasterId: str | None = Query(default=None),
    status_q: DemandStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> DemandListPayload:
    org_id = user.org_id if user.role != "super_admin" else None
    rows = service.list_requests(
        disaster_id=disasterId, status=status_q, org_id=org_id, limit=limit
    )
    return DemandListPayload(data=rows)


@router.post("", response_model=DemandPayload, status_code=status.HTTP_201_CREATED)
async def create_request(payload: DemandRequestCreate, user: CurrentUser) -> DemandPayload:
    """Authenticated submit. SMS goes through `/sms-webhook` instead."""
    req = await service.create_request(
        payload, requester_uid=user.uid, org_id=user.org_id
    )
    return DemandPayload(data=req)


@router.get("/{req_id}", response_model=DemandPayload)
async def get_request(req_id: str, _user: CurrentUser) -> DemandPayload:
    req = service.get_request(req_id)
    if not req:
        raise ApiError(
            code="REQUEST_NOT_FOUND",
            message=f"demand_request {req_id} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DemandPayload(data=req)


@router.post("/{req_id}/classify", response_model=DemandPayload)
async def reclassify(req_id: str, user: CurrentUser) -> DemandPayload:
    req = await service.reclassify(req_id, actor_uid=user.uid)
    return DemandPayload(data=req)


# ── Twilio SMS webhook ─────────────────────────────────────────────────────


@router.post("/sms-webhook", include_in_schema=False)
async def sms_webhook(
    request: Request,
    From: Annotated[str | None, Form()] = None,
    Body: Annotated[str | None, Form()] = None,
) -> Response:
    """Twilio webhook — receives SMS messages and stores them as demand_requests.

    Twilio posts as `application/x-www-form-urlencoded` with `From`, `Body`, etc.
    We accept this without auth (it's an inbound webhook).
    Response must be valid TwiML so Twilio can confirm delivery to the sender.
    """
    if not Body:
        # Some Twilio integrations send JSON in test rigs; fall back gracefully.
        try:
            payload = await request.json()
            Body = payload.get("Body") if isinstance(payload, dict) else None
            From = From or (payload.get("From") if isinstance(payload, dict) else None)
        except Exception:  # noqa: BLE001
            pass

    if not Body:
        return _twiml("Couldn't parse your message. Please retry.")

    geo, cleaned = service.parse_sms_body(Body)
    if not geo:
        return _twiml("Please include your GPS as 'lat,lng' at the end of the message.")

    payload = DemandRequestCreate(
        disasterId=None,
        items=None,  # Let the classifier extract.
        location=GeoPoint(lat=geo.lat, lng=geo.lng),
        raw=cleaned or Body,
        photos=[],
        source="sms",
    )

    try:
        req = await service.create_request(
            payload,
            requester_uid=f"sms:{From or 'unknown'}",
            org_id=None,
        )
    except Exception as exc:  # noqa: BLE001
        log.error("sms_webhook.failure", error=str(exc))
        return _twiml("System error — please retry in a few minutes.")

    return _twiml(
        f"Received: {req.severity} {req.category} request. "
        f"Coordinator will reach out shortly. Ref: {req.id[:8]}"
    )


def _twiml(message: str) -> Response:
    """Produce a minimal TwiML <Response><Message>...</Message></Response>."""
    safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    body = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{safe}</Message></Response>'
    return Response(content=body, media_type="application/xml")
