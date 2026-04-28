"""Copilot API routes — POST /api/copilot/chat (SSE) + conversation history."""
from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.core.auth import CurrentUser
from src.core.errors import ApiError, ApiResponse
from src.core.firebase import get_firestore
from src.modules.ai_copilot.chat import stream_chat

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversationId: str | None = None


@router.post("/chat")
async def chat(body: ChatRequest, user: CurrentUser) -> StreamingResponse:
    """SSE streaming endpoint. The browser parses each `data:` event as JSON."""
    return StreamingResponse(
        stream_chat(
            user_message=body.message,
            conversation_id=body.conversationId,
            user=user,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


class ConversationSummary(BaseModel):
    id: str
    lastMessageAt: str | None = None
    messageCount: int


class ConversationListPayload(ApiResponse[list[ConversationSummary]]):
    pass


class ConversationDetail(BaseModel):
    id: str
    messages: list[dict] = Field(default_factory=list)


class ConversationDetailPayload(ApiResponse[ConversationDetail]):
    pass


@router.get("/conversations", response_model=ConversationListPayload)
async def list_conversations(user: CurrentUser) -> ConversationListPayload:
    db = get_firestore()
    from google.cloud import firestore as gc_firestore

    docs = (
        db.collection("ai_conversations")
        .where(filter=gc_firestore.FieldFilter("userId", "==", user.uid))
        .limit(50)
        .stream()
    )
    rows = []
    for d in docs:
        data = d.to_dict() or {}
        last = data.get("lastMessageAt")
        rows.append(
            ConversationSummary(
                id=d.id,
                lastMessageAt=last.isoformat() if hasattr(last, "isoformat") else None,
                messageCount=len(data.get("messages") or []),
            )
        )
    rows.sort(key=lambda r: r.lastMessageAt or "", reverse=True)
    return ConversationListPayload(data=rows)


@router.get("/conversations/{conv_id}", response_model=ConversationDetailPayload)
async def get_conversation(conv_id: str, user: CurrentUser) -> ConversationDetailPayload:
    snap = get_firestore().collection("ai_conversations").document(conv_id).get()
    if not snap.exists:
        raise ApiError(
            "CONVERSATION_NOT_FOUND",
            "conversation not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    data = snap.to_dict() or {}
    if data.get("userId") != user.uid:
        raise ApiError(
            "FORBIDDEN",
            "this conversation belongs to another user",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return ConversationDetailPayload(
        data=ConversationDetail(id=conv_id, messages=list(data.get("messages") or []))
    )
