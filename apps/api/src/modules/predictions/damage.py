"""Multimodal damage assessment from a volunteer-uploaded photo.

Pipeline (BLUEPRINT Phase 6 Module 12):
  1. Volunteer captures a photo of a route blockage (flooded road, collapsed
     bridge, fire, debris).
  2. Web/mobile uploads to Cloud Storage and POSTs the URL here.
  3. Gemini 2.5 Flash (multimodal) returns strict JSON:
     {blocked, blockageType, severity, description, rerouteRecommended, confidenceScore}
  4. If `rerouteRecommended`, an `alerts` doc is written and a Pub/Sub
     `disruption.detected` event fires for the auto-rerouter (COMMIT 10).
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from firebase_admin import firestore as fb_firestore
from pydantic import BaseModel, ConfigDict, Field

from src.core.errors import ApiError
from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.audit.log import write_audit_log
from src.modules.disasters.models import GeoPoint
from src.modules.events import publisher
from src.modules.gemini.client import MODEL_FLASH, get_client, is_configured

log = get_logger("relief.damage")

BlockageType = Literal["flood", "debris", "fire", "crowd", "collapsed_road", "none", "other"]


class DamageAssessRequest(BaseModel):
    photoURL: str = Field(..., min_length=1)
    location: GeoPoint
    disasterId: str | None = None
    shipmentId: str | None = None
    note: str | None = Field(default=None, max_length=300)


class DamageAssessResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    blocked: bool
    blockageType: BlockageType
    severity: int = Field(..., ge=1, le=5)
    description: str
    rerouteRecommended: bool
    confidenceScore: float = Field(..., ge=0, le=1)
    alertId: str | None = None


_PROMPT = """You are a disaster relief route-safety assessor. Analyze the photo
and decide whether a delivery vehicle can pass through this location.

Return strict JSON matching the schema. Be conservative — when in doubt, set
rerouteRecommended=true. Severity scale:
  1 = passable with minor obstacle
  2 = passable but slow (debris, mud)
  3 = single-lane / partial blockage
  4 = impassable for a van or larger vehicle
  5 = catastrophic; do not approach
"""

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "blocked": {"type": "BOOLEAN"},
        "blockageType": {
            "type": "STRING",
            "enum": ["flood", "debris", "fire", "crowd", "collapsed_road", "none", "other"],
        },
        "severity": {"type": "INTEGER"},
        "description": {"type": "STRING"},
        "rerouteRecommended": {"type": "BOOLEAN"},
        "confidenceScore": {"type": "NUMBER"},
    },
    "required": [
        "blocked",
        "blockageType",
        "severity",
        "description",
        "rerouteRecommended",
        "confidenceScore",
    ],
}


async def _fetch_image(url: str) -> tuple[str, bytes]:
    """Fetch image bytes from HTTPS, Firebase Storage emulator, or `data:` URLs."""
    if url.startswith("data:"):
        # data:image/jpeg;base64,xxxxx
        try:
            head, b64 = url.split(",", 1)
        except ValueError as exc:
            raise ValueError("Malformed data URL") from exc
        mime = "image/jpeg"
        if head.startswith("data:") and ";" in head:
            mime = head[5 : head.index(";")]
        return mime, base64.b64decode(b64)

    headers = {
        "User-Agent": "ReliefOps/1.0 (humanitarian disaster relief; +https://reliefops.dev)",
        "Accept": "image/*,*/*;q=0.5",
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as cx:
        res = await cx.get(url)
        res.raise_for_status()
        ct = res.headers.get("content-type", "image/jpeg").split(";")[0]
        if not ct.startswith("image/"):
            ct = "image/jpeg"
        return ct, res.content


async def assess_damage(payload: DamageAssessRequest, *, actor_uid: str) -> DamageAssessResult:
    if not is_configured():
        raise ApiError(
            "GEMINI_NOT_CONFIGURED",
            "GEMINI_API_KEY required for damage assessment.",
            status_code=503,
        )

    try:
        mime, blob = await _fetch_image(payload.photoURL)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            "PHOTO_FETCH_FAILED",
            f"Could not fetch photo: {exc}",
            status_code=400,
        ) from exc

    client = get_client()
    from google.genai import types

    parts: list[Any] = [
        {"text": _PROMPT},
        {"inline_data": {"mime_type": mime, "data": base64.b64encode(blob).decode()}},
        {"text": (
            f"Note from volunteer: {payload.note}" if payload.note else "No additional note."
        )},
    ]

    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_RESPONSE_SCHEMA,
        temperature=0.1,
    )

    def _call() -> str:
        resp = client.models.generate_content(
            model=MODEL_FLASH, contents=parts, config=cfg
        )
        return resp.text or ""

    try:
        text = await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            "GEMINI_ERROR",
            f"Gemini damage assessment failed: {exc}",
            status_code=502,
        ) from exc

    try:
        result = DamageAssessResult.model_validate_json(text)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            "GEMINI_PARSE_ERROR",
            "Gemini returned malformed JSON.",
            status_code=502,
        ) from exc

    log.info(
        "damage.assessed",
        blocked=result.blocked,
        blockageType=result.blockageType,
        severity=result.severity,
        rerouteRecommended=result.rerouteRecommended,
        confidence=result.confidenceScore,
    )

    write_audit_log(
        actor_uid=actor_uid,
        action="damage.assess",
        resource="damage_assessments",
        resource_id=payload.photoURL,
        after={"blocked": result.blocked, "severity": result.severity, "type": result.blockageType},
        org_id=None,
    )

    if result.rerouteRecommended:
        alert_id = _write_disruption_alert(payload, result)
        result.alertId = alert_id
        publisher.publish(
            "disruption.detected",
            {
                "alertId": alert_id,
                "type": result.blockageType,
                "severity": result.severity,
                "lat": payload.location.lat,
                "lng": payload.location.lng,
                "disasterId": payload.disasterId,
                "shipmentId": payload.shipmentId,
            },
        )

    return result


def _write_disruption_alert(
    payload: DamageAssessRequest, result: DamageAssessResult
) -> str:
    db = get_firestore()
    ref = db.collection("alerts").document()

    radius_deg = 0.005  # ~500 m square — small bbox around the report point.
    polygon = {
        "type": "Polygon",
        "rings": [{
            "points": [
                {"lat": payload.location.lat - radius_deg, "lng": payload.location.lng - radius_deg},
                {"lat": payload.location.lat - radius_deg, "lng": payload.location.lng + radius_deg},
                {"lat": payload.location.lat + radius_deg, "lng": payload.location.lng + radius_deg},
                {"lat": payload.location.lat + radius_deg, "lng": payload.location.lng - radius_deg},
                {"lat": payload.location.lat - radius_deg, "lng": payload.location.lng - radius_deg},
            ],
        }],
    }

    ref.set({
        "type": result.blockageType if result.blockageType != "none" else "other",
        "subtype": "damage_assessment",
        "severity": result.severity,
        "headline": f"Route blocked ({result.blockageType}): {result.description}",
        "source": "damage_assessment",
        "classifiedBy": "gemini",
        "detectedAt": fb_firestore.SERVER_TIMESTAMP,
        "disasterId": payload.disasterId,
        "shipmentId": payload.shipmentId,
        "photoURL": payload.photoURL,
        "location": fb_firestore.GeoPoint(payload.location.lat, payload.location.lng),
        "area": polygon,
        "resolved": False,
        "rerouteRecommended": True,
        "confidenceScore": result.confidenceScore,
    })

    log.info("damage.alert_written", alert_id=ref.id, severity=result.severity)
    return ref.id
