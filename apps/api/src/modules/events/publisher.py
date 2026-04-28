"""Pub/Sub event publisher with emulator + auto-create-topic support.

Failures never propagate — pubsub is observability/fan-out, not request-critical.
The Pub/Sub emulator does not seed topics; `_ensure_topic` lazily creates them.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from google.api_core import exceptions as gax_exceptions
from google.cloud import pubsub_v1

from src.core.config import get_settings
from src.core.logging import get_logger

log = get_logger("relief.events")


@lru_cache(maxsize=1)
def _publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


def _topic_path(topic: str) -> str:
    settings = get_settings()
    return _publisher().topic_path(settings.gcp_project_id, topic)


_topic_cache: set[str] = set()


def _ensure_topic(topic: str) -> str:
    path = _topic_path(topic)
    if path in _topic_cache:
        return path
    pub = _publisher()
    try:
        pub.create_topic(name=path)
        log.info("pubsub.topic_created", topic=topic)
    except gax_exceptions.AlreadyExists:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("pubsub.topic_create_failed", topic=topic, error=str(exc))
        return path
    _topic_cache.add(path)
    return path


def publish(topic: str, payload: dict[str, Any], **attrs: str) -> None:
    """Fire-and-forget JSON publish. Failures only log."""
    try:
        path = _ensure_topic(topic)
        data = json.dumps(payload, default=str).encode("utf-8")
        future = _publisher().publish(path, data=data, **attrs)
        future.result(timeout=5)
        log.debug("pubsub.published", topic=topic, **attrs)
    except Exception as exc:  # noqa: BLE001
        log.warning("pubsub.publish_failed", topic=topic, error=str(exc))
