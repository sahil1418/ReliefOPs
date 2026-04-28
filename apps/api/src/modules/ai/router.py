"""AI Insights + Activity router.

Surfaces the Gemini-powered features so the dashboard can showcase them
without waiting for a user to click into Copilot.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from src.core.auth import CurrentUser
from src.core.errors import ApiResponse
from src.modules.ai.service import (
    ActivityItem,
    Insight,
    generate_insights,
    recent_activity,
)

router = APIRouter(prefix="/api/ai", tags=["ai"])


class InsightPayload(ApiResponse[Insight]):
    pass


class ActivityPayload(ApiResponse[list[ActivityItem]]):
    pass


@router.get("/insights", response_model=InsightPayload)
async def insights(
    _user: CurrentUser,
    refresh: bool = Query(default=False, description="Bypass the 60s cache"),
) -> InsightPayload:
    data = await generate_insights(force=refresh)
    return InsightPayload(data=data)


@router.get("/activity", response_model=ActivityPayload)
async def activity(
    _user: CurrentUser,
    limit: int = Query(default=12, ge=1, le=50),
) -> ActivityPayload:
    data = await recent_activity(limit=limit)
    return ActivityPayload(data=data)
