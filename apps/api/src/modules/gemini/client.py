"""Gemini API client wrapper.

The new `google-genai` SDK is the unified entry point for both the Gemini
Developer API (free tier, AI-Studio-issued keys) and Vertex AI. We use the
Developer API path with `GEMINI_API_KEY` for COMMITs 5 + 9.

`get_client()` is lazily cached so importing this module without a key set
doesn't error — only the first actual call does.
"""
from __future__ import annotations

from functools import lru_cache

from src.core.config import get_settings
from src.core.errors import ApiError
from src.core.logging import get_logger

log = get_logger("relief.gemini")

# Default model selection per BLUEPRINT Phase 4:
#   - Flash for extraction / classification / ETA (cheap + fast)
#   - Pro for the AI copilot (reasoning + tool calling)
# Override via env: free-tier API keys often have RPD=0 for gemini-2.5-pro,
# so we fall back to Flash for the copilot until billing is enabled. Flash
# also supports function calling and structured output.
import os as _os
MODEL_FLASH = _os.environ.get("GEMINI_MODEL_FLASH", "gemini-2.5-flash")
MODEL_PRO = _os.environ.get("GEMINI_MODEL_PRO", "gemini-2.5-flash")
MODEL_PRO_PRODUCTION = "gemini-2.5-pro"  # The production target.


@lru_cache(maxsize=1)
def get_client():  # noqa: ANN201 — return type is google.genai.Client; avoid heavy import at module load
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ApiError(
            code="GEMINI_NOT_CONFIGURED",
            message=(
                "GEMINI_API_KEY is not set. "
                "Get a key at https://aistudio.google.com/app/apikey and put it in apps/api/.env."
            ),
            status_code=503,
        )
    from google import genai  # local import — avoids hard dep at module load

    log.debug("gemini.client_init")
    return genai.Client(api_key=settings.gemini_api_key)


def is_configured() -> bool:
    return bool(get_settings().gemini_api_key)
