"""POST /api/notify — generic dispatcher used by ops + the disruption worker."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from src.core.auth import CurrentUser
from src.core.errors import ApiError, ApiResponse
from src.core.rbac import require_admin_or_coord
from src.modules.audit.log import write_audit_log
from src.modules.notifications import fcm, sms

router = APIRouter(prefix="/api/notify", tags=["notifications"])


class NotifyRequest(BaseModel):
    channel: Literal["push", "sms"]
    audience: dict = Field(
        ...,
        description=(
            "For push: {topic: 'disaster_<id>'} or {tokens: ['...']}. "
            "For sms: {phones: ['+8801...']}."
        ),
    )
    template: dict = Field(
        ..., description="{title, body, data?: {...}} for push; {body} for sms"
    )


class NotifyResult(BaseModel):
    channel: str
    success: int
    failure: int
    messageId: str | None = None


class NotifyPayload(ApiResponse[NotifyResult]):
    pass


@router.post(
    "",
    response_model=NotifyPayload,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin_or_coord)],
)
async def notify(body: NotifyRequest, user: CurrentUser) -> NotifyPayload:
    if body.channel == "push":
        topic = body.audience.get("topic")
        tokens = body.audience.get("tokens") or []
        title = body.template.get("title") or ""
        msg_body = body.template.get("body") or ""
        data = body.template.get("data") or {}
        if topic:
            mid = fcm.send_to_topic(topic, title=title, body=msg_body, data=data)
            result = NotifyResult(
                channel="push",
                success=1 if mid else 0,
                failure=0 if mid else 1,
                messageId=mid,
            )
        elif tokens:
            counts = fcm.send_to_tokens(tokens, title=title, body=msg_body, data=data)
            result = NotifyResult(channel="push", **counts)
        else:
            raise ApiError(
                "MISSING_AUDIENCE",
                "Provide audience.topic or audience.tokens for push.",
                status.HTTP_400_BAD_REQUEST,
            )
    elif body.channel == "sms":
        phones = body.audience.get("phones") or []
        msg_body = body.template.get("body") or ""
        ok = 0
        fail = 0
        for p in phones:
            sid = sms.send_sms(to=p, body=msg_body)
            if sid:
                ok += 1
            else:
                fail += 1
        result = NotifyResult(channel="sms", success=ok, failure=fail)
    else:
        raise ApiError("BAD_CHANNEL", f"Unsupported channel {body.channel}", status.HTTP_400_BAD_REQUEST)

    write_audit_log(
        actor_uid=user.uid,
        action="notify.send",
        resource="notifications",
        resource_id=body.channel,
        after={"audience_keys": list(body.audience.keys()), "result": result.model_dump()},
        org_id=user.org_id,
    )
    return NotifyPayload(data=result)
