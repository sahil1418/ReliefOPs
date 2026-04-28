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


# ── Demo Seed ───────────────────────────────────────────────────────────────


class SeedResult(BaseModel):
    anomalies_created: int
    tracking_events_created: int
    corridors_populated: list[str]


class SeedPayload(ApiResponse[SeedResult]):
    pass


@router.post("/seed-demo", response_model=SeedPayload)
async def seed_demo(_user: CurrentUser) -> SeedPayload:
    """Populate Firestore with realistic demo anomaly + tracking data.

    Generates synthetic but realistic GPS anomaly events across all
    monitored corridors for the last 4 hours. Useful for demo/hackathon
    presentations to show the dashboard working with live data.
    """
    import random

    db = get_firestore()
    now = datetime.now(timezone.utc)
    rng = random.Random(int(now.timestamp()) // 300)  # Changes every 5 min.

    corridors = disruption_predictor.DEFAULT_CORRIDORS
    anomaly_types = ["stuck", "drift", "slowdown", "congestion", "spoofing"]
    actions = {
        "stuck": "alert_coordinator_vehicle_stuck",
        "drift": "verify_volunteer_location_drift",
        "slowdown": "check_route_for_congestion",
        "congestion": "consider_alternate_route",
        "spoofing": "verify_gps_integrity",
    }

    anomalies_created = 0
    tracking_created = 0
    corridors_populated: list[str] = []

    for corridor in corridors:
        # Each corridor gets 3–8 anomalies proportional to its base_risk.
        n_anomalies = rng.randint(2, max(3, int(corridor.base_risk * 15)))
        n_tracking = rng.randint(5, 15)

        for i in range(n_anomalies):
            # Scatter events within corridor radius.
            offset_lat = rng.uniform(-0.08, 0.08) * (corridor.radius_km / 10)
            offset_lng = rng.uniform(-0.08, 0.08) * (corridor.radius_km / 10)
            a_type = rng.choices(
                anomaly_types,
                weights=[3, 2, 4, 3, 1],  # slowdown most common
                k=1,
            )[0]
            score = rng.uniform(0.6, 0.95)
            minutes_ago = rng.randint(5, 230)

            ref = db.collection("anomaly_events").document()
            ref.set({
                "anomaly_type": a_type,
                "score": round(score, 4),
                "confidence": round(score * rng.uniform(0.8, 1.1), 3),
                "recommended_action": actions.get(a_type, "escalate_to_stage_b"),
                "features": {
                    "speed_kmh": round(rng.uniform(0, 15 if a_type == "stuck" else 45), 1),
                    "acceleration_delta": round(rng.uniform(-20, 20), 2),
                    "dwell_time_sec": round(rng.uniform(0, 600 if a_type == "stuck" else 30), 1),
                    "distance_from_route_km": round(rng.uniform(0, 8 if a_type == "drift" else 1), 2),
                    "heading_change_deg": round(rng.uniform(0, 180 if a_type == "congestion" else 30), 1),
                },
                "lat": round(corridor.center_lat + offset_lat, 6),
                "lng": round(corridor.center_lng + offset_lng, 6),
                "volunteerId": f"vol_{rng.randint(1000, 9999)}",
                "shipmentId": f"shp_{rng.randint(10000, 99999)}",
                "detectedAt": now - timedelta(minutes=minutes_ago),
            })
            anomalies_created += 1

        # Tracking events — normal + some anomalous speeds.
        for j in range(n_tracking):
            offset_lat = rng.uniform(-0.05, 0.05) * (corridor.radius_km / 10)
            offset_lng = rng.uniform(-0.05, 0.05) * (corridor.radius_km / 10)
            minutes_ago = rng.randint(5, 120)
            speed = rng.choices(
                [rng.uniform(0, 3), rng.uniform(5, 15), rng.uniform(25, 55)],
                weights=[2, 3, 5],
                k=1,
            )[0]

            ref = db.collection("tracking_events").document()
            ref.set({
                "location": {
                    "lat": round(corridor.center_lat + offset_lat, 6),
                    "lng": round(corridor.center_lng + offset_lng, 6),
                },
                "speedKmh": round(speed, 1),
                "heading": round(rng.uniform(0, 360), 1),
                "accuracy": round(rng.uniform(3, 25), 1),
                "volunteerId": f"vol_{rng.randint(1000, 9999)}",
                "ts": now - timedelta(minutes=minutes_ago),
            })
            tracking_created += 1

        corridors_populated.append(corridor.id)

    log.info(
        "ml.seed_demo_complete",
        anomalies=anomalies_created,
        tracking=tracking_created,
    )

    return SeedPayload(data=SeedResult(
        anomalies_created=anomalies_created,
        tracking_events_created=tracking_created,
        corridors_populated=corridors_populated,
    ))
