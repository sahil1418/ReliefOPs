"""Predictions API — damage assessment + delay prediction (COMMIT 9 stub)."""
from __future__ import annotations

from fastapi import APIRouter

from src.core.auth import CurrentUser
from src.core.errors import ApiResponse
from src.modules.predictions.damage import (
    DamageAssessRequest,
    DamageAssessResult,
    assess_damage,
)

router = APIRouter(prefix="/api/predict", tags=["predictions"])


class DamageAssessPayload(ApiResponse[DamageAssessResult]):
    pass


@router.post("/damage-assess", response_model=DamageAssessPayload)
async def damage_assess(
    body: DamageAssessRequest, user: CurrentUser
) -> DamageAssessPayload:
    result = await assess_damage(body, actor_uid=user.uid)
    return DamageAssessPayload(data=result)
