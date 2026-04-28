"""Tool execution against Firestore + supporting services.

Each `_run_*` function maps to one of the declarations in `tools.py`. They
return plain dicts so the result can be serialized straight into the next
Gemini turn.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from google.cloud import firestore as gc_firestore

from src.core.auth import UserClaims
from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.shipments import service as shipments_service
from src.modules.shipments.models import ShipmentAssign

log = get_logger("relief.copilot.executor")


# ── Public dispatch ─────────────────────────────────────────────────────────


async def execute_tool(name: str, args: dict[str, Any], user: UserClaims) -> dict[str, Any]:
    """Run a tool by name. Returns ``{ok: bool, ...}``."""
    handlers = {
        "query_shipments": _run_query_shipments,
        "get_warehouse_stock": _run_warehouse_stock,
        "dispatch_volunteer": _run_dispatch_volunteer,
        "summarize_disaster_status": _run_summarize_disaster,
        "find_similar_past_disasters": _run_vector_search,
    }
    handler = handlers.get(name)
    if not handler:
        return {"ok": False, "error": f"Unknown tool: {name}"}
    try:
        return await handler(args, user)
    except Exception as exc:  # noqa: BLE001
        log.warning("copilot.tool_error", tool=name, error=str(exc))
        return {"ok": False, "error": str(exc)[:300]}


# ── Tool handlers ───────────────────────────────────────────────────────────


async def _run_query_shipments(
    args: dict[str, Any], user: UserClaims
) -> dict[str, Any]:
    db = get_firestore()
    q: gc_firestore.Query = db.collection("shipments")
    if "status" in args:
        q = q.where(filter=gc_firestore.FieldFilter("status", "==", args["status"]))
    if "disasterId" in args:
        q = q.where(filter=gc_firestore.FieldFilter("disasterId", "==", args["disasterId"]))
    if "volunteerId" in args:
        q = q.where(filter=gc_firestore.FieldFilter("assignedVolunteerId", "==", args["volunteerId"]))
    if "priority" in args:
        q = q.where(filter=gc_firestore.FieldFilter("priority", "==", args["priority"]))
    # Org isolation for non-super-admins.
    if user.role != "super_admin" and user.org_id:
        q = q.where(filter=gc_firestore.FieldFilter("orgId", "==", user.org_id))

    limit = int(args.get("limit", 10))
    limit = max(1, min(20, limit))

    docs = list(q.limit(limit).stream())
    rows = []
    for d in docs:
        data = d.to_dict() or {}
        rows.append({
            "id": d.id,
            "status": data.get("status"),
            "priority": data.get("priority"),
            "disasterId": data.get("disasterId"),
            "assignedVolunteerId": data.get("assignedVolunteerId"),
            "totalKg": data.get("totalKg"),
            "dropoffAddress": data.get("dropoffAddress"),
            "createdAt": _ts(data.get("createdAt")),
            "etaCurrent": _ts(data.get("etaCurrent")),
        })

    return {"ok": True, "count": len(rows), "shipments": rows}


async def _run_warehouse_stock(
    args: dict[str, Any], _user: UserClaims
) -> dict[str, Any]:
    db = get_firestore()
    wh_id = args["warehouseId"]
    wh_snap = db.collection("warehouses").document(wh_id).get()
    if not wh_snap.exists:
        return {"ok": False, "error": f"warehouse {wh_id} not found"}
    wh_data = wh_snap.to_dict() or {}

    q: gc_firestore.Query = db.collection("inventory_items").where(
        filter=gc_firestore.FieldFilter("warehouseId", "==", wh_id)
    )
    if "sku" in args:
        q = q.where(filter=gc_firestore.FieldFilter("sku", "==", args["sku"]))

    items = []
    cats: dict[str, float] = {}
    for d in q.stream():
        data = d.to_dict() or {}
        items.append({
            "sku": data.get("sku"),
            "name": data.get("name"),
            "category": data.get("category"),
            "qty": data.get("qty"),
            "reservedQty": data.get("reservedQty"),
            "expiry": _ts(data.get("expiry")),
        })
        cats[data.get("category", "other")] = cats.get(data.get("category", "other"), 0.0) + float(data.get("qty") or 0)

    return {
        "ok": True,
        "warehouse": {
            "id": wh_id,
            "name": wh_data.get("name"),
            "address": wh_data.get("address"),
            "coldChainCapable": wh_data.get("coldChainCapable"),
            "capacityKg": wh_data.get("capacityKg"),
        },
        "items": items[:25],
        "stockByCategory": {k: round(v, 1) for k, v in cats.items()},
    }


async def _run_dispatch_volunteer(
    args: dict[str, Any], user: UserClaims
) -> dict[str, Any]:
    if user.role not in {"super_admin", "ngo_admin", "coordinator"}:
        return {"ok": False, "error": "Only coordinators and admins can dispatch volunteers."}
    ship = shipments_service.assign_volunteer(
        args["shipmentId"],
        args["volunteerId"],
        actor_uid=user.uid,
        actor_org_id=user.org_id,
    )
    return {
        "ok": True,
        "shipmentId": ship.id,
        "status": ship.status,
        "assignedVolunteerId": ship.assignedVolunteerId,
        "vehicleId": ship.vehicleId,
    }


async def _run_summarize_disaster(
    args: dict[str, Any], user: UserClaims
) -> dict[str, Any]:
    db = get_firestore()
    did = args["disasterId"]
    d_snap = db.collection("disasters").document(did).get()
    if not d_snap.exists:
        return {"ok": False, "error": f"disaster {did} not found"}
    d = d_snap.to_dict() or {}

    requests_q = db.collection("demand_requests").where(
        filter=gc_firestore.FieldFilter("disasterId", "==", did)
    )
    by_severity: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    pending = 0
    total_requests = 0
    for r in requests_q.stream():
        rd = r.to_dict() or {}
        total_requests += 1
        sev = rd.get("severity") or "low"
        by_severity[sev] = by_severity.get(sev, 0) + 1
        if rd.get("status") == "pending":
            pending += 1

    shipments_q = db.collection("shipments").where(
        filter=gc_firestore.FieldFilter("disasterId", "==", did)
    )
    by_status: dict[str, int] = {"created": 0, "assigned": 0, "in_transit": 0, "delivered": 0, "failed": 0}
    delivered_kg = 0.0
    total_shipments = 0
    for s in shipments_q.stream():
        sd = s.to_dict() or {}
        total_shipments += 1
        status = sd.get("status") or "created"
        by_status[status] = by_status.get(status, 0) + 1
        if status == "delivered":
            delivered_kg += float(sd.get("totalKg") or 0)

    return {
        "ok": True,
        "disaster": {
            "id": did,
            "name": d.get("name"),
            "type": d.get("type"),
            "status": d.get("status"),
            "severityScale": d.get("severityScale"),
            "affectedPopulationEstimate": d.get("affectedPopulationEstimate"),
        },
        "demandRequests": {
            "total": total_requests,
            "pending": pending,
            "bySeverity": by_severity,
        },
        "shipments": {
            "total": total_shipments,
            "byStatus": by_status,
            "deliveredKg": round(delivered_kg, 1),
        },
    }


async def _run_vector_search(
    args: dict[str, Any], _user: UserClaims
) -> dict[str, Any]:
    """Cosine-similarity top-K over `ai_embeddings`.

    For demo scale we read the whole collection and rank in-memory. When the
    corpus exceeds ~10K docs we'll switch to Firestore native vector search
    via `find_nearest()` (the index `vectorConfig` is already declared in
    firestore.indexes.json).
    """
    from src.modules.gemini.client import get_client, is_configured

    query: str = args["query"]
    limit = int(args.get("limit", 3))

    if not is_configured():
        return {"ok": False, "error": "GEMINI_API_KEY not configured."}

    client = get_client()
    from google.genai import types as _gtypes

    # Embed the query. Output is truncated to 768-dim to match the Firestore
    # vector-search index in infra/firestore.indexes.json (gemini-embedding-001
    # is native 3072-dim; Matryoshka-style truncation works without retraining).
    try:
        emb_resp = client.models.embed_content(
            model="gemini-embedding-001",
            contents=query,
            config=_gtypes.EmbedContentConfig(output_dimensionality=768),
        )
        first = emb_resp.embeddings[0]
        q_vec = list(getattr(first, "values", first))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"embed failed: {exc}"}

    db = get_firestore()
    docs = list(db.collection("ai_embeddings").stream())
    if not docs:
        return {"ok": True, "matches": [], "note": "ai_embeddings is empty."}

    scored: list[tuple[float, dict[str, Any]]] = []
    for d in docs:
        data = d.to_dict() or {}
        vec = data.get("embedding") or []
        # Stored as list of floats; if a Firestore Vector type sneaks in,
        # `to_list()` returns the same shape.
        if hasattr(vec, "to_list"):
            vec = vec.to_list()
        if not vec:
            continue
        score = _cosine(q_vec, vec)
        scored.append((score, {
            "id": d.id,
            "text": data.get("text"),
            "sourceType": data.get("sourceType"),
            "sourceId": data.get("sourceId"),
            "score": round(score, 4),
        }))
    scored.sort(reverse=True, key=lambda x: x[0])
    return {"ok": True, "matches": [m[1] for m in scored[:limit]]}


# ── Helpers ─────────────────────────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _ts(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None
