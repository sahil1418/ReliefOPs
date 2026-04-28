"""Firestore I/O for disasters."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import status as http_status
from firebase_admin import firestore as fb_firestore
from google.cloud import firestore as gc_firestore

from src.core.errors import ApiError
from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.audit.log import write_audit_log
from src.modules.disasters.models import (
    Disaster,
    DisasterCreate,
    DisasterPatch,
    DisasterStatus,
)

log = get_logger("relief.disasters")
COLLECTION = "disasters"


def _doc_to_disaster(snap: gc_firestore.DocumentSnapshot) -> Disaster:
    data = snap.to_dict() or {}
    data["id"] = snap.id
    return Disaster.model_validate(data)


def list_disasters(
    *,
    status: DisasterStatus | None,
    org_id: str | None,
    limit: int = 100,
) -> list[Disaster]:
    db = get_firestore()
    q: gc_firestore.Query = db.collection(COLLECTION)
    if status:
        q = q.where(filter=gc_firestore.FieldFilter("status", "==", status))
    if org_id:
        q = q.where(filter=gc_firestore.FieldFilter("orgId", "==", org_id))
    q = q.limit(limit)

    docs = list(q.stream())
    docs.sort(key=lambda d: (d.to_dict() or {}).get("declaredAt") or 0, reverse=True)
    return [_doc_to_disaster(d) for d in docs]


def get_disaster(disaster_id: str) -> Disaster | None:
    snap = get_firestore().collection(COLLECTION).document(disaster_id).get()
    if not snap.exists:
        return None
    return _doc_to_disaster(snap)


def create_disaster(payload: DisasterCreate, *, actor_uid: str, org_id: str) -> Disaster:
    db = get_firestore()
    ref = db.collection(COLLECTION).document()

    geo_json = json.dumps(
        {
            "type": "Polygon",
            "coordinates": [
                [[p.lng, p.lat] for p in ring.points] for ring in payload.geo.rings
            ],
        }
    )

    doc: dict[str, Any] = {
        "name": payload.name,
        "type": payload.type,
        "geo": payload.geo.model_dump(),
        "bbox": payload.bbox.model_dump(),
        "geoJson": geo_json,
        "declaredAt": fb_firestore.SERVER_TIMESTAMP,
        "declaredBy": actor_uid,
        "status": "active",
        "severityScale": payload.severityScale,
        "affectedPopulationEstimate": payload.affectedPopulationEstimate,
        "sdgTags": payload.sdgTags,
        "orgId": org_id,
    }
    ref.set(doc)
    log.info("disaster.created", id=ref.id, type=payload.type, severity=payload.severityScale)

    write_audit_log(
        actor_uid=actor_uid,
        action="disaster.create",
        resource="disasters",
        resource_id=ref.id,
        after={k: v for k, v in doc.items() if k not in ("declaredAt",)},
        org_id=org_id,
    )

    return _doc_to_disaster(ref.get())


def patch_disaster(
    disaster_id: str,
    body: DisasterPatch,
    *,
    actor_uid: str,
    org_id: str | None,
) -> Disaster:
    db = get_firestore()
    ref = db.collection(COLLECTION).document(disaster_id)
    snap = ref.get()
    if not snap.exists:
        raise ApiError(
            code="DISASTER_NOT_FOUND",
            message=f"disaster {disaster_id} not found",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )
    before = snap.to_dict() or {}

    update = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if not update:
        return _doc_to_disaster(snap)

    ref.update(update)

    write_audit_log(
        actor_uid=actor_uid,
        action="disaster.patch",
        resource="disasters",
        resource_id=disaster_id,
        before={k: before.get(k) for k in update.keys()},
        after=update,
        org_id=org_id or before.get("orgId"),
    )
    return _doc_to_disaster(ref.get())
