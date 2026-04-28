"""Firebase Cloud Messaging — push notifications via the Admin SDK.

Free tier: unlimited pushes. Used for:
  - "Route updated due to flooding on NH-66" (volunteer)
  - "5 inventory items expire within 7 days" (coordinator)
  - "Critical demand request needs assignment" (admin)

`send_to_topic` and `send_to_tokens` both no-op gracefully against the auth
emulator (which lacks an FCM endpoint) — failures only log.
"""
from __future__ import annotations

from typing import Iterable

from firebase_admin import messaging

from src.core.firebase import init_firebase
from src.core.logging import get_logger

log = get_logger("relief.fcm")


def send_to_topic(topic: str, *, title: str, body: str, data: dict[str, str] | None = None) -> str | None:
    init_firebase()
    msg = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        topic=topic.replace("/", "-"),  # FCM topic names are restricted
    )
    try:
        msg_id = messaging.send(msg)
        log.info("fcm.topic_send", topic=topic, message_id=msg_id, title=title)
        return msg_id
    except Exception as exc:  # noqa: BLE001
        log.warning("fcm.topic_send_failed", topic=topic, error=str(exc))
        return None


def send_to_tokens(
    tokens: Iterable[str],
    *,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> dict[str, int]:
    """Multicast push. Returns ``{success, failure}`` counts."""
    init_firebase()
    token_list = [t for t in tokens if t]
    if not token_list:
        return {"success": 0, "failure": 0}

    msg = messaging.MulticastMessage(
        tokens=token_list,
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
    )
    try:
        response = messaging.send_each_for_multicast(msg)
        log.info(
            "fcm.multicast_send",
            tokens=len(token_list),
            success=response.success_count,
            failure=response.failure_count,
        )
        return {"success": response.success_count, "failure": response.failure_count}
    except Exception as exc:  # noqa: BLE001
        log.warning("fcm.multicast_send_failed", error=str(exc))
        return {"success": 0, "failure": len(token_list)}
