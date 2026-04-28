"""SSE-streaming chat endpoint with Gemini function calling.

Wire format (newline-delimited `data: <json>`):
  data: {"type":"text","content":"…"}
  data: {"type":"tool_call","content":{"name":"…","args":{…}}}
  data: {"type":"tool_result","content":{"name":"…","result":{…}}}
  data: {"type":"conversation","content":{"id":"…"}}
  data: {"type":"done"}

Why this format? The web client just splits on `\n\n`, parses each `data:` line
as JSON, and re-renders. No special Vercel `ai`-style SDK needed.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator

from firebase_admin import firestore as fb_firestore

from src.core.auth import UserClaims
from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.ai_copilot.executor import execute_tool
from src.modules.ai_copilot.tools import SYSTEM_PROMPT, TOOL_DECLARATIONS
from src.modules.gemini.client import MODEL_PRO, get_client, is_configured

log = get_logger("relief.copilot.chat")

CONVERSATIONS = "ai_conversations"
MAX_TOOL_TURNS = 4


def _sse(event_type: str, content: Any) -> bytes:
    payload = {"type": event_type, "content": content}
    return f"data: {json.dumps(payload, default=str)}\n\n".encode("utf-8")


def _load_or_init(conversation_id: str | None, user: UserClaims) -> tuple[str, list[dict[str, Any]]]:
    db = get_firestore()
    if conversation_id:
        snap = db.collection(CONVERSATIONS).document(conversation_id).get()
        if snap.exists:
            data = snap.to_dict() or {}
            if data.get("userId") == user.uid:
                return conversation_id, list(data.get("messages") or [])
    # Create a fresh conversation
    ref = db.collection(CONVERSATIONS).document()
    ref.set({
        "userId": user.uid,
        "orgId": user.org_id,
        "messages": [],
        "createdAt": fb_firestore.SERVER_TIMESTAMP,
        "lastMessageAt": fb_firestore.SERVER_TIMESTAMP,
    })
    return ref.id, []


def _persist(conversation_id: str, messages: list[dict[str, Any]]) -> None:
    db = get_firestore()
    db.collection(CONVERSATIONS).document(conversation_id).set(
        {
            "messages": messages,
            "lastMessageAt": fb_firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def _to_genai_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate our stored conversation log into google-genai `contents` shape."""
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "user":
            out.append({"role": "user", "parts": [{"text": m.get("content", "")}]})
        elif role == "assistant":
            parts: list[dict[str, Any]] = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for tc in m.get("toolCalls") or []:
                parts.append({"function_call": {"name": tc["name"], "args": tc.get("args") or {}}})
            if parts:
                out.append({"role": "model", "parts": parts})
        elif role == "tool":
            out.append({
                "role": "user",  # google-genai uses 'user' role for function responses
                "parts": [{
                    "function_response": {
                        "name": m["name"],
                        "response": {"content": m.get("result")},
                    },
                }],
            })
    return out


async def stream_chat(
    *,
    user_message: str,
    conversation_id: str | None,
    user: UserClaims,
) -> AsyncIterator[bytes]:
    if not is_configured():
        yield _sse("text", "Gemini is not configured. Please set GEMINI_API_KEY in apps/api/.env.")
        yield _sse("done", None)
        return

    conv_id, messages = _load_or_init(conversation_id, user)
    yield _sse("conversation", {"id": conv_id})

    # Append the user's new message
    messages.append({"role": "user", "content": user_message, "ts": time.time()})

    client = get_client()
    from google.genai import types

    function_decls = types.Tool(function_declarations=TOOL_DECLARATIONS)
    config = types.GenerateContentConfig(
        system_instruction=(
            f"{SYSTEM_PROMPT}\n\n"
            f"User context: role={user.role} orgId={user.org_id} uid={user.uid}"
        ),
        tools=[function_decls],
        temperature=0.3,
    )

    # Multi-turn function-calling loop
    final_text_parts: list[str] = []
    for turn in range(MAX_TOOL_TURNS + 1):
        contents = _to_genai_contents(messages)
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL_PRO,
                contents=contents,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("copilot.gemini_error", error=str(exc))
            yield _sse("error", {"message": str(exc)[:300]})
            yield _sse("done", None)
            return

        # Walk over the candidate's parts.
        candidate = response.candidates[0] if response.candidates else None
        parts = candidate.content.parts if candidate and candidate.content else []

        tool_calls_this_turn: list[dict[str, Any]] = []
        text_this_turn: list[str] = []
        for part in parts:
            fc = getattr(part, "function_call", None)
            if fc and getattr(fc, "name", None):
                # Pydantic-ish proto; use vars() / __dict__ safely.
                args = dict(getattr(fc, "args", {}) or {})
                tool_calls_this_turn.append({"name": fc.name, "args": args})
            text = getattr(part, "text", None)
            if text:
                text_this_turn.append(text)

        # Persist + stream the assistant turn (might contain text AND tool calls)
        assistant_msg: dict[str, Any] = {"role": "assistant", "ts": time.time()}
        if text_this_turn:
            joined = "".join(text_this_turn)
            assistant_msg["content"] = joined
            final_text_parts.append(joined)
            yield _sse("text", joined)
        if tool_calls_this_turn:
            assistant_msg["toolCalls"] = tool_calls_this_turn
        messages.append(assistant_msg)

        if not tool_calls_this_turn:
            break  # Plain text reply — we're done.

        # Execute each tool call sequentially, streaming the calls + results.
        for tc in tool_calls_this_turn:
            yield _sse("tool_call", {"name": tc["name"], "args": tc["args"]})
            result = await execute_tool(tc["name"], tc["args"], user)
            yield _sse("tool_result", {"name": tc["name"], "result": result})
            messages.append({
                "role": "tool",
                "name": tc["name"],
                "result": result,
                "ts": time.time(),
            })

        if turn == MAX_TOOL_TURNS:
            yield _sse("text", "\n\n_(reached tool-call iteration cap; stopping)_")
            break

    _persist(conv_id, messages)
    yield _sse("done", None)
