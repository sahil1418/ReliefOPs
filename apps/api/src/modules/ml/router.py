"""ML module REST endpoints — anomaly detection, disruption prediction, graph routing.

Endpoints:
  GET  /api/ml/anomalies           — list recent anomaly events
  GET  /api/ml/risk-corridors      — current corridor risk scores
  POST /api/ml/predict-disruptions — on-demand disruption prediction
  GET  /api/ml/model-status        — model metadata + health
  GET  /api/ml/graph/stats         — transit graph statistics
  POST /api/ml/graph/shortest-path — Dijkstra / A* shortest path query
  POST /api/ml/detect-anomaly      — one-shot anomaly detection on a ping
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query
from google.cloud import firestore as gc_firestore
from pydantic import BaseModel, Field

from src.core.auth import CurrentUser
from src.core.errors import ApiError, ApiResponse
from src.core.firebase import get_firestore
from src.core.logging import get_logger
from src.modules.ml import anomaly_detector, disruption_predictor, graph_router

log = get_logger("relief.ml.router")

router = APIRouter(prefix="/api/ml", tags=["ml"])


# ── Anomaly Detection ───────────────────────────────────────────────────────


class AnomalyEventOut(BaseModel):
    id: str
    anomaly_type: str
    score: float
    confidence: float
    recommended_action: str
    lat: float
    lng: float
    volunteer_id: str | None = None
    shipment_id: str | None = None
    detected_at: str | None = None
    features: dict[str, float] = {}


class AnomalyListPayload(ApiResponse[list[AnomalyEventOut]]):
    pass


@router.get("/anomalies", response_model=AnomalyListPayload)
async def list_anomalies(
    _user: CurrentUser,
    hours: int = Query(default=4, ge=1, le=48),
    limit: int = Query(default=50, ge=1, le=200),
) -> AnomalyListPayload:
    """List recent anomaly events from Firestore."""
    db = get_firestore()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    try:
        docs = list(
            db.collection("anomaly_events")
            .where("detectedAt", ">=", cutoff)
            .order_by("detectedAt", direction=gc_firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
    except Exception:
        docs = []

    out = []
    for d in docs:
        data = d.to_dict() or {}
        det = data.get("detectedAt")
        out.append(AnomalyEventOut(
            id=d.id,
            anomaly_type=data.get("anomaly_type", "unknown"),
            score=float(data.get("score", 0)),
            confidence=float(data.get("confidence", 0)),
            recommended_action=data.get("recommended_action", ""),
            lat=float(data.get("lat", 0)),
            lng=float(data.get("lng", 0)),
            volunteer_id=data.get("volunteerId"),
            shipment_id=data.get("shipmentId"),
            detected_at=det.isoformat() if isinstance(det, datetime) else str(det) if det else None,
            features=data.get("features", {}),
        ))

    return AnomalyListPayload(data=out)


class DetectRequest(BaseModel):
    lat: float
    lng: float
    speedKmh: float = 0.0
    heading: float = 0.0
    accuracy: float = 0.0
    ts: str | None = None
    previous_lat: float | None = None
    previous_lng: float | None = None
    previous_speedKmh: float | None = None
    previous_heading: float | None = None
    previous_ts: str | None = None


class DetectPayload(ApiResponse[dict[str, Any]]):
    pass


@router.post("/detect-anomaly", response_model=DetectPayload)
async def detect_anomaly(
    body: DetectRequest,
    _user: CurrentUser,
) -> DetectPayload:
    """One-shot anomaly detection on a single GPS ping."""
    current = {
        "lat": body.lat,
        "lng": body.lng,
        "speedKmh": body.speedKmh,
        "heading": body.heading,
        "ts": body.ts or datetime.now(timezone.utc).isoformat(),
    }
    previous = None
    if body.previous_lat is not None:
        previous = {
            "lat": body.previous_lat,
            "lng": body.previous_lng,
            "speedKmh": body.previous_speedKmh or 0,
            "heading": body.previous_heading or 0,
            "ts": body.previous_ts,
        }

    result = anomaly_detector.detect(current, previous)
    return DetectPayload(data={
        "score": result.score,
        "is_anomaly": result.is_anomaly,
        "anomaly_type": result.anomaly_type.value,
        "confidence": result.confidence,
        "recommended_action": result.recommended_action,
        "features": result.features_used,
    })


# ── Disruption Prediction ──────────────────────────────────────────────────


class RiskCorridorsPayload(ApiResponse[disruption_predictor.DisruptionPrediction]):
    pass


@router.get("/risk-corridors", response_model=RiskCorridorsPayload)
async def risk_corridors(_user: CurrentUser) -> RiskCorridorsPayload:
    """Get current corridor risk scores (cached heuristic, fast)."""
    result = await disruption_predictor.predict_disruptions()
    return RiskCorridorsPayload(data=result)


@router.post("/predict-disruptions", response_model=RiskCorridorsPayload)
async def predict_disruptions(_user: CurrentUser) -> RiskCorridorsPayload:
    """On-demand full disruption prediction (may call Gemini)."""
    result = await disruption_predictor.predict_disruptions()
    return RiskCorridorsPayload(data=result)


# ── Model Status ────────────────────────────────────────────────────────────


class ModelStatusPayload(ApiResponse[dict[str, Any]]):
    pass


@router.get("/model-status", response_model=ModelStatusPayload)
async def model_status(_user: CurrentUser) -> ModelStatusPayload:
    """Model metadata, health, and graph statistics."""
    anomaly_info = anomaly_detector.get_model_info()
    graph = graph_router.get_graph()

    return ModelStatusPayload(data={
        "anomaly_detector": anomaly_info,
        "graph_router": {
            "algorithm": "Dijkstra + A*",
            "graph_stats": graph.stats,
            "demo_nodes": list(graph.nodes.keys()),
        },
        "disruption_predictor": {
            "model": "gemini-2.5-flash + heuristic-hybrid",
            "corridors_monitored": len(disruption_predictor.DEFAULT_CORRIDORS),
            "corridor_ids": [c.id for c in disruption_predictor.DEFAULT_CORRIDORS],
        },
    })


# ── Graph Routing ───────────────────────────────────────────────────────────


class ShortestPathRequest(BaseModel):
    from_node: str
    to_node: str
    algorithm: str = "dijkstra"  # dijkstra | astar


class ShortestPathResult(BaseModel):
    path: list[str]
    total_distance_km: float
    total_time_min: float
    algorithm_used: str
    disrupted_edges: int = 0


class ShortestPathPayload(ApiResponse[ShortestPathResult | None]):
    pass


@router.post("/graph/shortest-path", response_model=ShortestPathPayload)
async def shortest_path(
    body: ShortestPathRequest,
    _user: CurrentUser,
) -> ShortestPathPayload:
    """Compute shortest path through the transit graph using Dijkstra or A*."""
    graph = graph_router.get_graph()

    if body.algorithm == "astar":
        result = graph.a_star(body.from_node, body.to_node)
    else:
        result = graph.dijkstra(body.from_node, body.to_node)

    if result is None:
        return ShortestPathPayload(data=None)

    path, dist_km, time_min = result
    return ShortestPathPayload(data=ShortestPathResult(
        path=path,
        total_distance_km=round(dist_km, 2),
        total_time_min=round(time_min, 1),
        algorithm_used=body.algorithm,
        disrupted_edges=graph.stats["disrupted_edges"],
    ))


class GraphStatsPayload(ApiResponse[dict[str, Any]]):
    pass


@router.get("/graph/stats", response_model=GraphStatsPayload)
async def graph_stats(_user: CurrentUser) -> GraphStatsPayload:
    """Transit graph statistics."""
    graph = graph_router.get_graph()
    return GraphStatsPayload(data={
        **graph.stats,
        "nodes_detail": [
            {"id": n.id, "type": n.node_type, "lat": n.lat, "lng": n.lng, "name": n.metadata.get("name", "")}
            for n in graph.nodes.values()
        ],
    })
