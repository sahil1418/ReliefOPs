"""Gemini-2.5-Flash structured-output classifier for demand requests.

The classifier takes raw text (and optionally up to 3 photo URLs) and returns
strict JSON matching `ClassifiedRequest`. Per BLUEPRINT Phase 6 Module 2:
  - response_mime_type=application/json + response_schema → Gemini guarantees
    parseable output without prompt-engineering tricks.
  - Cache the system prompt for the 75% prompt-cache discount when we have
    enough volume (free tier doesn't bill, so omitted in COMMIT 5).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
from functools import lru_cache
from typing import Any

import httpx

from src.core.errors import ApiError
from src.core.logging import get_logger
from src.modules.gemini.client import MODEL_FLASH, get_client, is_configured
from src.modules.requests.models import ClassifiedRequest

log = get_logger("relief.classifier")


SYSTEM_PROMPT = """You are a humanitarian disaster relief logistics classifier.

Your job: extract STRUCTURED supply needs from a disaster relief request that
came from a beneficiary, NGO worker, or SMS gateway. The text may be in English,
Bengali, or transliterated.

Conventions:
  * `sku` should be UPPER_SNAKE_CASE — pick from this catalogue when possible:
    RICE, DAL, OIL, BISCUIT, ORS, PARACETAMOL, INSULIN, BANDAGE, FIRSTAID_KIT,
    TARP, BLANKET, TENT, MAT, WATER, WATER_PURIF, FILTER, TORCH, WHISTLE,
    ROPE, LIFEJACKET. Else use a UPPER_SNAKE_CASE form of the noun.
  * `qty` is the requested quantity; pick a sensible number when not given.
  * `unit` is one of: kg, L, pcs, packets, bottles.
  * `urgency`: 1 = routine, 5 = life-threatening.
  * `severity`: critical (urgency 5), high (urgency 4), medium (urgency 3), low (urgency 1-2).
  * `category` reflects the dominant item type. If multiple categories appear,
    pick the most urgent: medicine > rescue > water > food > shelter > other.
  * `confidence`: your subjective 0-1 estimate that the extraction is correct.
  * `summary`: 1-sentence rephrasing for a coordinator (max 300 chars).

If the text is empty or non-actionable (e.g. "thanks!"), return urgency=1,
severity=low, category=other, items=[], confidence=0.1.

Return ONLY the JSON. No prose."""


_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "sku": {"type": "STRING"},
                    "qty": {"type": "NUMBER"},
                    "unit": {"type": "STRING"},
                },
                "required": ["sku", "qty", "unit"],
            },
        },
        "urgency": {"type": "INTEGER"},
        "severity": {"type": "STRING", "enum": ["critical", "high", "medium", "low"]},
        "category": {
            "type": "STRING",
            "enum": ["food", "medicine", "shelter", "water", "rescue", "other"],
        },
        "confidence": {"type": "NUMBER"},
        "summary": {"type": "STRING"},
    },
    "required": ["items", "urgency", "severity", "category", "confidence"],
}


# Tiny in-process cache so re-classify on the same input doesn't re-call Gemini.
@lru_cache(maxsize=256)
def _cached(_hash: str) -> ClassifiedRequest | None:
    return None


def _hash_inputs(raw: str, photos: tuple[str, ...]) -> str:
    h = hashlib.sha256()
    h.update(raw.encode())
    for p in photos:
        h.update(b"|")
        h.update(p.encode())
    return h.hexdigest()


async def _fetch_image(url: str) -> tuple[str, bytes]:
    """Best-effort image fetch — returns (mime, bytes) or raises."""
    async with httpx.AsyncClient(timeout=15) as cx:
        res = await cx.get(url)
        res.raise_for_status()
        mime = res.headers.get("content-type", "image/jpeg").split(";")[0]
        return mime, res.content


async def classify(raw: str, photo_urls: list[str] | None = None) -> ClassifiedRequest:
    """Run the classifier. Falls back to a heuristic stub when GEMINI_API_KEY is unset."""
    photo_urls = photo_urls or []

    if not is_configured():
        log.warning("classifier.fallback_heuristic")
        return _heuristic_classify(raw)

    cache_key = _hash_inputs(raw, tuple(photo_urls))
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    client = get_client()
    parts: list[Any] = [{"text": f"REQUEST: {raw}"}]
    for url in photo_urls[:3]:
        try:
            mime, blob = await _fetch_image(url)
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(blob).decode()}})
        except Exception as exc:  # noqa: BLE001
            log.warning("classifier.image_fetch_failed", url=url, error=str(exc))

    def _call() -> str:
        # google-genai's client is sync; run in a thread to keep the route async.
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
            temperature=0.2,
        )
        response = client.models.generate_content(
            model=MODEL_FLASH,
            contents=parts,
            config=cfg,
        )
        return response.text or ""

    try:
        text = await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001
        log.error("classifier.gemini_error", error=str(exc))
        raise ApiError(
            code="GEMINI_ERROR",
            message=f"Gemini classification failed: {exc}",
            status_code=502,
        ) from exc

    try:
        result = ClassifiedRequest.model_validate_json(text)
    except Exception as exc:  # noqa: BLE001
        log.error("classifier.parse_error", error=str(exc), payload=text[:300])
        raise ApiError(
            code="GEMINI_PARSE_ERROR",
            message="Gemini returned malformed JSON; please retry.",
            status_code=502,
        ) from exc

    log.info(
        "classifier.classified",
        urgency=result.urgency,
        severity=result.severity,
        category=result.category,
        items=len(result.items),
    )

    # Update LRU cache (lru_cache returns the cached value, so store via a dict-like trick)
    _cached.cache_clear()
    # Because lru_cache returns None on misses, we re-define a sub-cache keyed by hash:
    _result_cache[cache_key] = result
    return result


# Manual cache because lru_cache can't store mutating values per-arg without re-call.
_result_cache: dict[str, ClassifiedRequest] = {}


def _heuristic_classify(raw: str) -> ClassifiedRequest:
    """Offline fallback when no Gemini key is set — keeps tests + CI green."""
    text = raw.lower()
    items: list[dict[str, Any]] = []

    # Very rough keyword extraction so the demo at least produces *some* result.
    keywords = {
        "rice": ("RICE", "kg"),
        "dal": ("DAL", "kg"),
        "ors": ("ORS", "packets"),
        "water": ("WATER", "L"),
        "blanket": ("BLANKET", "pcs"),
        "tent": ("TENT", "pcs"),
        "tarp": ("TARP", "pcs"),
        "bandage": ("BANDAGE", "pcs"),
        "insulin": ("INSULIN", "vials"),
    }
    for kw, (sku, unit) in keywords.items():
        if kw in text:
            items.append({"sku": sku, "qty": 50, "unit": unit})

    has_urgent = any(w in text for w in ("urgent", "emergency", "critical", "stranded", "dying"))
    urgency = 5 if has_urgent else (3 if items else 2)
    severity = "critical" if urgency == 5 else ("high" if urgency == 4 else ("medium" if urgency == 3 else "low"))
    category = "medicine" if any(it["sku"] in ("ORS", "INSULIN", "BANDAGE") for it in items) else \
               "water" if any(it["sku"] == "WATER" for it in items) else \
               "shelter" if any(it["sku"] in ("TENT", "TARP", "BLANKET") for it in items) else \
               "food" if items else "other"

    return ClassifiedRequest.model_validate(
        {
            "items": items,
            "urgency": urgency,
            "severity": severity,
            "category": category,
            "confidence": 0.5 if items else 0.1,
            "summary": raw[:280],
        }
    )
