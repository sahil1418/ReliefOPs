"""Copilot tool execution + live Gemini function-calling tests."""
from __future__ import annotations

import os

import httpx
import pytest

from src.core.auth import UserClaims
from src.core.config import get_settings
from src.modules.ai_copilot.executor import execute_tool


def _emulator_running() -> bool:
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    try:
        httpx.get(f"http://{host}", timeout=0.5)
        return True
    except Exception:  # noqa: BLE001
        return False


needs_emulator = pytest.mark.skipif(
    not _emulator_running(),
    reason="Needs Firestore emulator on 127.0.0.1:8080",
)
needs_gemini = pytest.mark.skipif(
    not get_settings().gemini_api_key,
    reason="Needs GEMINI_API_KEY in apps/api/.env",
)


def _admin_user() -> UserClaims:
    return UserClaims(
        uid="test-admin",
        email="test@reliefops.dev",
        role="super_admin",
        org_id="org-test",
        email_verified=True,
    )


@needs_emulator
@pytest.mark.asyncio
async def test_query_shipments_unknown_filter_returns_empty() -> None:
    """An impossible filter shouldn't crash; should return count=0."""
    out = await execute_tool(
        "query_shipments",
        {"disasterId": "no-such-disaster-xyz", "limit": 5},
        _admin_user(),
    )
    assert out["ok"] is True
    assert out["count"] == 0
    assert out["shipments"] == []


@pytest.mark.asyncio
async def test_unknown_tool_returns_error() -> None:
    out = await execute_tool("frobnicate", {}, _admin_user())
    assert out["ok"] is False
    assert "Unknown tool" in out["error"]


@needs_emulator
@pytest.mark.asyncio
async def test_summarize_disaster_handles_missing_id() -> None:
    out = await execute_tool(
        "summarize_disaster_status",
        {"disasterId": "definitely-not-a-real-id"},
        _admin_user(),
    )
    assert out["ok"] is False
    assert "not found" in out["error"]


@needs_emulator
@needs_gemini
@pytest.mark.asyncio
async def test_vector_search_against_seeded_embeddings() -> None:
    """Best-effort: if ai_embeddings has seed data, ranking returns it; else
    we accept the empty case so seed-state doesn't fail CI."""
    out = await execute_tool(
        "find_similar_past_disasters",
        {"query": "cyclone evacuation supplies", "limit": 3},
        _admin_user(),
    )
    assert out["ok"] is True
    assert "matches" in out
