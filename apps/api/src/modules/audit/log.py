"""Append-only audit log writer.

Every state-changing API call should call `write_audit_log(...)`. Firestore
security rules forbid update/delete on the `audit_logs` collection, so entries
are tamper-evident.
"""
from __future__ import annotations

from typing import Any

from firebase_admin import firestore

from src.core.firebase import get_firestore
from src.core.logging import get_logger

log = get_logger("relief.audit")


def write_audit_log(
    *,
    actor_uid: str,
    action: str,
    resource: str,
    resource_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    org_id: str | None = None,
) -> None:
    """Best-effort audit log entry. Never raises into the calling request."""
    try:
        db = get_firestore()
        db.collection("audit_logs").add(
            {
                "actorUid": actor_uid,
                "action": action,
                "resource": resource,
                "resourceId": resource_id,
                "before": before,
                "after": after,
                "orgId": org_id,
                "ts": firestore.SERVER_TIMESTAMP,
            }
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "audit.write_failed",
            action=action,
            resource=resource,
            resource_id=resource_id,
            error=str(exc),
        )
