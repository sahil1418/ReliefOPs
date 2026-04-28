"""Classifier + SMS-parser tests.

Live-Gemini test runs ONLY when GEMINI_API_KEY is set in the environment.
The heuristic-fallback path is always tested so CI can run without a key.
"""
import pytest

from src.core.config import get_settings
from src.modules.requests.classifier import _heuristic_classify, classify
from src.modules.requests.service import parse_sms_body


def test_heuristic_picks_up_rice_and_ors() -> None:
    result = _heuristic_classify(
        "Need 100kg rice and 50 ORS packets urgently in flood zone"
    )
    skus = {it.sku for it in result.items}
    assert "RICE" in skus
    assert "ORS" in skus
    # Word "urgently" → urgency 5 → severity critical
    assert result.urgency == 5
    assert result.severity == "critical"
    # ORS is medicine-category which dominates over food.
    assert result.category == "medicine"


def test_heuristic_unknown_text_returns_low_confidence() -> None:
    result = _heuristic_classify("hello world")
    assert result.items == []
    assert result.urgency <= 2
    assert result.confidence < 0.5


def test_sms_parser_extracts_lat_lng() -> None:
    geo, cleaned = parse_sms_body("Cox's Bazar NEED 50 RICE 21.44,91.98")
    assert geo is not None
    assert geo.lat == pytest.approx(21.44)
    assert geo.lng == pytest.approx(91.98)
    assert "Cox" in cleaned
    assert "RICE" in cleaned


def test_sms_parser_rejects_invalid_coords() -> None:
    geo, _cleaned = parse_sms_body("hello 999.0,99.0")
    assert geo is None


def test_sms_parser_no_coords_returns_none() -> None:
    geo, cleaned = parse_sms_body("just a message")
    assert geo is None
    assert cleaned == "just a message"


@pytest.mark.skipif(not get_settings().gemini_api_key, reason="Needs GEMINI_API_KEY in apps/api/.env")
@pytest.mark.asyncio
async def test_live_gemini_classifies_rice_and_ors() -> None:
    """Real network call — gated on env var so CI without a key still passes.

    Gemini occasionally returns 503 UNAVAILABLE under load. Retry up to 3x with
    short backoff so a transient outage doesn't fail the suite.
    """
    import asyncio

    from src.core.errors import ApiError

    async def _try():
        return await classify("Need 100kg rice and 50 ORS packets urgently in flood zone")

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            result = await _try()
            break
        except ApiError as exc:
            last_exc = exc
            if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                await asyncio.sleep(2 + attempt * 2)
                continue
            raise
    else:
        pytest.skip(f"Gemini 503 after retries: {last_exc}")

    assert result.urgency >= 4
    assert result.severity in {"critical", "high"}
    assert result.category in {"food", "medicine"}
    skus = {it.sku.upper() for it in result.items}
    assert any("RICE" in s for s in skus)
    assert any("ORS" in s for s in skus)
    assert result.confidence > 0
