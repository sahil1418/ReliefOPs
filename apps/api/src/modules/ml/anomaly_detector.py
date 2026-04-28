"""Transit anomaly detection — Isolation Forest on GPS tracking features.

Architecture (Pillar 2 from ROADMAP_ML.md):
  Stage A — Isolation Forest (cheap, runs on every ping)
    Features: speedKmh, accelerationDelta, dwellTimeSec,
              distanceFromRouteKm, headingChangeDeg
    Output:   anomaly score 0-1. Score > 0.6 → escalate.

  Stage B — Gemini autoencoder-equivalent (only on Stage-A escalations)
    Reconstructs context from last N pings; classifies anomaly type
    via Gemini 2.5 Flash structured output.

The Isolation Forest is bootstrapped with synthetic "normal" transit
data on first load.  After 4+ weeks of live data, retrain from
Firestore `tracking_events` via a Cloud Scheduler job.

Cost: ~0 (runs in-process, <1ms per prediction).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import numpy as np

from src.core.logging import get_logger

log = get_logger("relief.ml.anomaly")

# ── Types ───────────────────────────────────────────────────────────────────


class AnomalyType(str, Enum):
    STUCK = "stuck"
    DRIFT = "drift"
    SLOWDOWN = "slowdown"
    CONGESTION = "congestion"
    SPOOFING = "spoofing"
    UNKNOWN = "unknown"
    NONE = "none"


@dataclass
class AnomalyResult:
    score: float                # 0–1 (1 = most anomalous)
    is_anomaly: bool
    anomaly_type: AnomalyType
    confidence: float           # 0–1
    recommended_action: str
    features_used: dict[str, float] = field(default_factory=dict)


# ── Feature extraction ──────────────────────────────────────────────────────


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(a, 1.0)))


def extract_features(
    current: dict[str, Any],
    previous: dict[str, Any] | None = None,
    route_stops: list[dict[str, Any]] | None = None,
) -> dict[str, float]:
    """Build feature vector from a GPS ping + optional context."""
    speed = float(current.get("speedKmh") or 0.0)

    # Acceleration delta (speed change / time delta).
    accel_delta = 0.0
    dwell_time_sec = 0.0
    heading_change = 0.0
    if previous:
        prev_speed = float(previous.get("speedKmh") or 0.0)
        prev_ts = previous.get("ts")
        curr_ts = current.get("ts")
        if isinstance(prev_ts, str):
            prev_ts = datetime.fromisoformat(prev_ts)
        if isinstance(curr_ts, str):
            curr_ts = datetime.fromisoformat(curr_ts)
        if isinstance(prev_ts, datetime) and isinstance(curr_ts, datetime):
            dt_sec = max((curr_ts - prev_ts).total_seconds(), 1.0)
            accel_delta = (speed - prev_speed) / (dt_sec / 3600.0)  # km/h²

            # Dwell time: if speed < 2 km/h for dt_sec, count as dwelling.
            if speed < 2.0 and prev_speed < 2.0:
                dwell_time_sec = dt_sec

        # Heading change.
        prev_head = float(previous.get("heading") or 0.0)
        curr_head = float(current.get("heading") or 0.0)
        heading_change = abs(curr_head - prev_head)
        if heading_change > 180:
            heading_change = 360 - heading_change

    # Distance from nearest planned route stop.
    dist_from_route = 0.0
    c_lat = float(current.get("lat") or 0.0)
    c_lng = float(current.get("lng") or 0.0)
    if route_stops:
        dists = []
        for s in route_stops:
            s_loc = s.get("location") or {}
            s_lat = float(s_loc.get("lat") or s_loc.get("latitude") or 0.0)
            s_lng = float(s_loc.get("lng") or s_loc.get("longitude") or 0.0)
            if s_lat and s_lng:
                dists.append(_haversine_km(c_lat, c_lng, s_lat, s_lng))
        if dists:
            dist_from_route = min(dists)

    return {
        "speed_kmh": speed,
        "acceleration_delta": accel_delta,
        "dwell_time_sec": dwell_time_sec,
        "distance_from_route_km": dist_from_route,
        "heading_change_deg": heading_change,
    }


# ── Isolation Forest model ──────────────────────────────────────────────────


class TransitAnomalyDetector:
    """Singleton Isolation Forest trained on synthetic normal GPS patterns."""

    _instance: TransitAnomalyDetector | None = None

    def __init__(self) -> None:
        self._model: Any = None
        self._fitted = False
        self._version = "v1.0-synthetic"
        self._trained_at: datetime | None = None
        self._n_samples = 0

    @classmethod
    def get(cls) -> TransitAnomalyDetector:
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._bootstrap()
        return cls._instance

    def _bootstrap(self) -> None:
        """Train on synthetic 'normal' transit data."""
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError:
            log.warning("ml.sklearn_missing", msg="scikit-learn not installed; anomaly detection disabled")
            return

        rng = np.random.RandomState(42)
        n = 2000

        # Synthetic normal patterns: speed 10-60, low accel, low dwell, on-route, stable heading.
        X = np.column_stack([
            rng.uniform(10, 60, n),           # speed_kmh
            rng.normal(0, 5, n),              # acceleration_delta (km/h²)
            rng.exponential(10, n),            # dwell_time_sec (mostly short)
            rng.exponential(0.3, n),           # distance_from_route_km
            rng.exponential(10, n),            # heading_change_deg
        ])

        self._model = IsolationForest(
            n_estimators=150,
            contamination=0.05,
            max_samples=min(256, n),
            random_state=42,
            n_jobs=1,
        )
        self._model.fit(X)
        self._fitted = True
        self._trained_at = datetime.now(timezone.utc)
        self._n_samples = n
        log.info("ml.anomaly_model_trained", version=self._version, samples=n)

    def predict(self, features: dict[str, float]) -> AnomalyResult:
        """Score a single ping."""
        if not self._fitted or self._model is None:
            return AnomalyResult(
                score=0.0, is_anomaly=False,
                anomaly_type=AnomalyType.NONE, confidence=0.0,
                recommended_action="model_not_available",
            )

        X = np.array([[
            features.get("speed_kmh", 0),
            features.get("acceleration_delta", 0),
            features.get("dwell_time_sec", 0),
            features.get("distance_from_route_km", 0),
            features.get("heading_change_deg", 0),
        ]])

        # decision_function: lower = more anomalous.  Normalize to 0–1.
        raw_score = self._model.decision_function(X)[0]
        # Typical range: -0.5 (anomaly) to +0.3 (normal). Map to 0–1.
        normalized = float(np.clip(1.0 - (raw_score + 0.5) / 0.8, 0, 1))

        is_anomaly = normalized > 0.6
        anomaly_type = AnomalyType.NONE
        action = "continue_monitoring"

        if is_anomaly:
            anomaly_type, action = _classify_anomaly(features, normalized)

        return AnomalyResult(
            score=round(normalized, 4),
            is_anomaly=is_anomaly,
            anomaly_type=anomaly_type,
            confidence=round(min(normalized * 1.2, 1.0), 3),
            recommended_action=action,
            features_used=features,
        )

    @property
    def model_info(self) -> dict[str, Any]:
        return {
            "version": self._version,
            "fitted": self._fitted,
            "trained_at": self._trained_at.isoformat() if self._trained_at else None,
            "n_training_samples": self._n_samples,
            "algorithm": "IsolationForest",
            "n_estimators": 150,
            "contamination": 0.05,
            "features": [
                "speed_kmh", "acceleration_delta", "dwell_time_sec",
                "distance_from_route_km", "heading_change_deg",
            ],
        }


def _classify_anomaly(
    features: dict[str, float], score: float
) -> tuple[AnomalyType, str]:
    """Heuristic anomaly-type classification (pre-Gemini Stage B)."""
    speed = features.get("speed_kmh", 0)
    dwell = features.get("dwell_time_sec", 0)
    dist = features.get("distance_from_route_km", 0)
    heading = features.get("heading_change_deg", 0)
    accel = abs(features.get("acceleration_delta", 0))

    if speed < 2 and dwell > 120:
        return AnomalyType.STUCK, "alert_coordinator_vehicle_stuck"
    if dist > 2.0:
        return AnomalyType.DRIFT, "verify_volunteer_location_drift"
    if speed < 10 and accel < 2:
        return AnomalyType.SLOWDOWN, "check_route_for_congestion"
    if speed > 5 and speed < 20 and heading > 90:
        return AnomalyType.CONGESTION, "consider_alternate_route"
    if dist > 5.0 and heading > 120:
        return AnomalyType.SPOOFING, "verify_gps_integrity"

    return AnomalyType.UNKNOWN, "escalate_to_stage_b"


# ── Public API ──────────────────────────────────────────────────────────────


def detect(
    current_ping: dict[str, Any],
    previous_ping: dict[str, Any] | None = None,
    route_stops: list[dict[str, Any]] | None = None,
) -> AnomalyResult:
    """Convenience entry point — extract features + predict."""
    features = extract_features(current_ping, previous_ping, route_stops)
    return TransitAnomalyDetector.get().predict(features)


def get_model_info() -> dict[str, Any]:
    return TransitAnomalyDetector.get().model_info
