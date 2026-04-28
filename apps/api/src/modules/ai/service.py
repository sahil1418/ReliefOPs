"""AI Insights + Activity service.

`generate_insights()` — collects current operational state from Firestore and
asks Gemini 2.5 Flash for a 2-3 sentence brief plus a punch list. Cached for
60s so dashboard auto-refresh doesn't burn quota.

`recent_activity()` — tails the `audit_logs` collection for AI-attributed
actions (demand classifications, damage assessments) plus `ai_conversations`
for copilot calls. Returns a flat, ordered feed for the dashboard.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore as gc_firestore
from pydantic import BaseModel

from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.gemini.client import MODEL_FLASH, get_client, is_configured

log = get_logger("relief.ai")

# Audit-log actions that map to a Gemini call.
_GEMINI_ACTIONS: dict[str, str] = {
    "demand_request.create": "Demand classified",
    "demand_request.reclassify": "Demand reclassified",
    "damage.assess": "Damage assessed",
}


class Insight(BaseModel):
    summary: str
    bullets: list[str]
    model: str
    latencyMs: int
    generatedAt: str


class ActivityItem(BaseModel):
    id: str
    kind: str  # "classify" | "vision" | "chat" | "embed"
    label: str
    detail: str | None = None
    model: str
    actorUid: str | None = None
    ts: str


# ─── Insights ──────────────────────────────────────────────────────────────

_insight_cache: dict[str, tuple[float, Insight]] = {}
_INSIGHT_TTL_S = 60


_SYSTEM_PROMPT = (
    "You are the operational AI for ReliefOps, a disaster-logistics platform. "
    "Given a snapshot of the current state, write a concise situation brief in two parts:\n"
    "1. A single 'summary' sentence (max 30 words) naming the most pressing operational fact.\n"
    "2. Three short 'bullets' (each under 14 words) — concrete, action-oriented observations or "
    "recommendations a dispatcher should act on now. No hedging, no boilerplate, no greetings.\n"
    "Respond as JSON: {\"summary\": str, \"bullets\": [str, str, str]}."
)


async def _gather_state() -> dict[str, Any]:
    """Collect a small operational snapshot from Firestore (synchronous reads in a thread)."""
    def _read() -> dict[str, Any]:
        db = get_firestore()
        ff = gc_firestore.FieldFilter

        disasters = []
        for d in db.collection("disasters").where(filter=ff("status", "==", "active")).limit(10).stream():
            data = d.to_dict() or {}
            disasters.append(
                {
                    "name": data.get("name"),
                    "type": data.get("type"),
                    "severity": data.get("severityScale"),
                    "affected": data.get("affectedPopulationEstimate"),
                }
            )

        in_transit = 0
        delivered_today = 0
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        for s in db.collection("shipments").stream():
            sd = s.to_dict() or {}
            if sd.get("status") == "in_transit":
                in_transit += 1
            elif sd.get("status") == "delivered":
                delivered_at = sd.get("deliveredAt")
                if isinstance(delivered_at, datetime) and delivered_at >= today:
                    delivered_today += 1

        # Top 5 highest-urgency open requests (any disaster).
        urgent = []
        for r in (
            db.collection("demand_requests")
            .where(filter=ff("status", "in", ["new", "matched", "in_progress"]))
            .limit(20)
            .stream()
        ):
            rd = r.to_dict() or {}
            urgent.append(
                {
                    "urgency": rd.get("urgency"),
                    "category": rd.get("category"),
                    "raw": (rd.get("rawText") or "")[:120],
                }
            )
        urgent.sort(key=lambda x: 0 if x["urgency"] == "critical" else 1)

        return {
            "activeDisasters": disasters,
            "shipmentsInTransit": in_transit,
            "shipmentsDeliveredToday": delivered_today,
            "openRequestsTop5": urgent[:5],
        }

    return await asyncio.to_thread(_read)


async def generate_insights(force: bool = False) -> Insight:
    """Generate a Gemini-backed brief, cached 60s.

    Falls back to a deterministic stub if Gemini isn't configured (so the
    dashboard never errors during local dev).
    """
    cached = _insight_cache.get("global")
    now = time.time()
    if cached and not force and now - cached[0] < _INSIGHT_TTL_S:
        return cached[1]

    state = await _gather_state()

    if not is_configured():
        stub = _heuristic_insight(state)
        _insight_cache["global"] = (now, stub)
        return stub

    client = get_client()
    started = time.perf_counter()

    def _call() -> str:
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.3,
        )
        response = client.models.generate_content(
            model=MODEL_FLASH,
            contents=[{"text": f"OPERATIONAL_STATE: {state}"}],
            config=cfg,
        )
        return response.text or "{}"

    try:
        raw = await asyncio.to_thread(_call)
    except Exception as exc:  # noqa: BLE001
        log.warning("ai.insights.gemini_failed", error=str(exc))
        stub = _heuristic_insight(state)
        _insight_cache["global"] = (now, stub)
        return stub

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    summary, bullets = _parse_insight_json(raw)
    insight = Insight(
        summary=summary,
        bullets=bullets,
        model=MODEL_FLASH,
        latencyMs=elapsed_ms,
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )
    _insight_cache["global"] = (now, insight)
    return insight


def _parse_insight_json(text: str) -> tuple[str, list[str]]:
    import json

    try:
        obj = json.loads(text)
        summary = str(obj.get("summary") or "").strip()
        raw_bullets = obj.get("bullets") or []
        bullets = [str(b).strip() for b in raw_bullets if str(b).strip()][:3]
        if summary and bullets:
            return summary, bullets
    except Exception:  # noqa: BLE001
        pass
    return (
        "Live operational data was processed but Gemini returned an unparseable response.",
        ["Retry the brief — transient model output formatting issue."],
    )


def _heuristic_insight(state: dict[str, Any]) -> Insight:
    n_dis = len(state["activeDisasters"])
    in_transit = state["shipmentsInTransit"]
    open_reqs = len(state["openRequestsTop5"])
    summary = (
        f"{n_dis} active disasters, {in_transit} shipments in transit, "
        f"{open_reqs} open requests pending dispatch."
    )
    bullets = [
        f"Re-run the matcher on {open_reqs} open requests to pick up new volunteer availability.",
        f"Verify ETA confidence on {in_transit} live shipments before next status sync.",
        "Escalate to coordinator if any severity-5 disaster lacks an active relief route.",
    ]
    return Insight(
        summary=summary,
        bullets=bullets,
        model="heuristic-fallback",
        latencyMs=0,
        generatedAt=datetime.now(timezone.utc).isoformat(),
    )


# ─── Activity feed ─────────────────────────────────────────────────────────


async def recent_activity(limit: int = 12) -> list[ActivityItem]:
    """Tail audit_logs + ai_conversations for AI-attributed activity."""

    def _read() -> list[ActivityItem]:
        db = get_firestore()
        items: list[ActivityItem] = []

        # Audit logs — demand classifications + damage assessments.
        audit_q = (
            db.collection("audit_logs")
            .order_by("ts", direction=gc_firestore.Query.DESCENDING)
            .limit(60)
        )
        for doc in audit_q.stream():
            d = doc.to_dict() or {}
            action = d.get("action") or ""
            if action not in _GEMINI_ACTIONS:
                continue
            ts = d.get("ts")
            ts_iso = ts.isoformat() if isinstance(ts, datetime) else datetime.now(timezone.utc).isoformat()
            kind = "vision" if action == "damage.assess" else "classify"
            after = d.get("after") or {}
            detail = _format_audit_detail(action, after)
            items.append(
                ActivityItem(
                    id=doc.id,
                    kind=kind,
                    label=_GEMINI_ACTIONS[action],
                    detail=detail,
                    model="gemini-2.5-flash",
                    actorUid=d.get("actorUid"),
                    ts=ts_iso,
                )
            )

        # Copilot conversations — count latest messages as chat events.
        conv_q = (
            db.collection("ai_conversations")
            .order_by("lastMessageAt", direction=gc_firestore.Query.DESCENDING)
            .limit(8)
        )
        for doc in conv_q.stream():
            d = doc.to_dict() or {}
            ts = d.get("lastMessageAt") or d.get("createdAt")
            ts_iso = ts.isoformat() if isinstance(ts, datetime) else datetime.now(timezone.utc).isoformat()
            messages = d.get("messages") or []
            n_msgs = len(messages)
            last_user = next(
                (m for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "user"),
                None,
            )
            preview = ""
            if last_user and isinstance(last_user.get("content"), str):
                preview = last_user["content"][:90]
            items.append(
                ActivityItem(
                    id=doc.id,
                    kind="chat",
                    label="Copilot turn",
                    detail=preview or f"{n_msgs} messages",
                    model="gemini-2.5-pro",
                    actorUid=d.get("userId"),
                    ts=ts_iso,
                )
            )

        items.sort(key=lambda x: x.ts, reverse=True)
        return items[:limit]

    return await asyncio.to_thread(_read)


def _format_audit_detail(action: str, after: dict[str, Any]) -> str | None:
    if action == "damage.assess":
        sev = after.get("severityScale") or after.get("severity") or "?"
        blocked = after.get("blocked")
        suffix = " · reroute" if blocked else ""
        return f"severity {sev}/5{suffix}"
    if action.startswith("demand_request"):
        urgency = after.get("urgency") or "?"
        category = after.get("category") or "?"
        return f"{urgency} · {category}"
    return None
