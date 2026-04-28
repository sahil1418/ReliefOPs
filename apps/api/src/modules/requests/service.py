"""Firestore I/O for demand_requests."""
from __future__ import annotations

import re
from typing import Any

from fastapi import status as http_status
from firebase_admin import firestore as fb_firestore
from google.cloud import firestore as gc_firestore

from src.core.errors import ApiError
from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.audit.log import write_audit_log
from src.modules.disasters.models import GeoPoint
from src.modules.events import publisher
from src.modules.requests import classifier
from src.modules.requests.models import (
    ClassifiedRequest,
    DemandItem,
    DemandRequest,
    DemandRequestCreate,
    DemandSource,
    DemandStatus,
)

log = get_logger("relief.requests")
COLLECTION = "demand_requests"


def _doc_to_request(snap: gc_firestore.DocumentSnapshot) -> DemandRequest:
    data = snap.to_dict() or {}
    data["id"] = snap.id

    # Normalize the location GeoPoint into our Pydantic shape.
    loc = data.get("location")
    if loc is not None and hasattr(loc, "latitude"):
        data["location"] = {"lat": loc.latitude, "lng": loc.longitude}

    return DemandRequest.model_validate(data)


def list_requests(
    *,
    disaster_id: str | None,
    status: DemandStatus | None,
    org_id: str | None,
    limit: int = 100,
) -> list[DemandRequest]:
    db = get_firestore()
    q: gc_firestore.Query = db.collection(COLLECTION)
    if disaster_id:
        q = q.where(filter=gc_firestore.FieldFilter("disasterId", "==", disaster_id))
    if status:
        q = q.where(filter=gc_firestore.FieldFilter("status", "==", status))
    if org_id:
        q = q.where(filter=gc_firestore.FieldFilter("orgId", "==", org_id))
    q = q.limit(limit)

    docs = list(q.stream())
    docs.sort(key=lambda d: (d.to_dict() or {}).get("urgency") or 0, reverse=True)
    return [_doc_to_request(d) for d in docs]


def get_request(req_id: str) -> DemandRequest | None:
    snap = get_firestore().collection(COLLECTION).document(req_id).get()
    if not snap.exists:
        return None
    return _doc_to_request(snap)


async def create_request(
    payload: DemandRequestCreate,
    *,
    requester_uid: str | None,
    org_id: str | None,
) -> DemandRequest:
    """Create + classify in one shot."""
    classification = await classifier.classify(payload.raw, payload.photos)

    # Caller-supplied items override classifier extraction (when present + non-empty).
    items: list[dict[str, Any]] = (
        [it.model_dump() for it in payload.items] if payload.items else
        [it.model_dump() for it in classification.items]
    )

    db = get_firestore()
    ref = db.collection(COLLECTION).document()
    doc: dict[str, Any] = {
        "disasterId": payload.disasterId,
        "source": payload.source,
        "requesterId": requester_uid,
        "items": items,
        "location": fb_firestore.GeoPoint(payload.location.lat, payload.location.lng),
        "urgency": classification.urgency,
        "severity": classification.severity,
        "category": classification.category,
        "raw": payload.raw,
        "photos": payload.photos,
        "createdAt": fb_firestore.SERVER_TIMESTAMP,
        "status": "pending",
        "classifiedBy": "gemini" if classifier.is_configured() else "human",
        "confidence": classification.confidence,
        "summary": classification.summary,
        "orgId": org_id,
    }
    ref.set(doc)
    log.info(
        "demand_request.created",
        id=ref.id,
        urgency=classification.urgency,
        category=classification.category,
        items=len(items),
    )

    write_audit_log(
        actor_uid=requester_uid or "anonymous",
        action="demand_request.create",
        resource="demand_requests",
        resource_id=ref.id,
        after={k: v for k, v in doc.items() if k not in ("location", "createdAt")},
        org_id=org_id,
    )

    publisher.publish(
        "demand.created",
        {
            "id": ref.id,
            "disasterId": payload.disasterId,
            "urgency": classification.urgency,
            "category": classification.category,
        },
        org_id=org_id or "",
    )

    return _doc_to_request(ref.get())


async def reclassify(req_id: str, *, actor_uid: str) -> DemandRequest:
    db = get_firestore()
    ref = db.collection(COLLECTION).document(req_id)
    snap = ref.get()
    if not snap.exists:
        raise ApiError(
            code="REQUEST_NOT_FOUND",
            message=f"demand_request {req_id} not found",
            status_code=http_status.HTTP_404_NOT_FOUND,
        )
    before = snap.to_dict() or {}
    raw = before.get("raw") or ""
    photos = list(before.get("photos") or [])

    cls = await classifier.classify(raw, photos)
    update = {
        "items": [it.model_dump() for it in cls.items],
        "urgency": cls.urgency,
        "severity": cls.severity,
        "category": cls.category,
        "confidence": cls.confidence,
        "summary": cls.summary,
        "classifiedBy": "gemini" if classifier.is_configured() else "human",
    }
    ref.update(update)

    write_audit_log(
        actor_uid=actor_uid,
        action="demand_request.reclassify",
        resource="demand_requests",
        resource_id=req_id,
        before={"urgency": before.get("urgency"), "category": before.get("category")},
        after={"urgency": cls.urgency, "category": cls.category},
        org_id=before.get("orgId"),
    )
    return _doc_to_request(ref.get())


# ── SMS parsing ─────────────────────────────────────────────────────────────

# Loose format: "<DISTRICT> NEED <QTY> <ITEM> <LAT,LNG>"
# Examples:
#   "Cox's Bazar NEED 50 RICE 21.44,91.98"
#   "kerala NEED 100 ors packets 9.93,76.27"
_LATLNG_RE = re.compile(r"(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)")


def parse_sms_body(body: str) -> tuple[GeoPoint | None, str]:
    """Pull out a `lat,lng` pair from the message and return (geo, body_text)."""
    body = body.strip()
    m = _LATLNG_RE.search(body)
    if not m:
        return None, body
    lat = float(m.group(1))
    lng = float(m.group(2))
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, body
    cleaned = (body[: m.start()] + body[m.end():]).strip()
    return GeoPoint(lat=lat, lng=lng), cleaned
