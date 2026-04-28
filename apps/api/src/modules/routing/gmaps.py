"""Google Maps Platform integration for distance + duration matrices.

Architecture per BLUEPRINT Phase 6 Module 5:
  primary path  → ComputeRouteMatrix (Routes API)
  fallback      → haversine + road-factor multiplier (no network call)

The fallback runs whenever:
  1. `GOOGLE_MAPS_API_KEY` is unset, OR
  2. The Routes API returns 4xx (most often "API not enabled on project"), OR
  3. The request times out.

Results are cached in Firestore `route_cache/{hash}` with a 1h TTL so repeat
optimization runs over the same stops are free.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from firebase_admin import firestore as fb_firestore

from src.core.config import get_settings
from src.core.firebase import get_firestore
from src.core.logging import get_logger

log = get_logger("relief.gmaps")

# ── Constants ────────────────────────────────────────────────────────────────

EARTH_RADIUS_KM = 6371.0
ROAD_FACTOR = 1.35  # Empirical: real road distance ≈ 1.35 × great-circle.
DEFAULT_AVG_SPEED_KMH = 30.0  # Bangladesh urban average; tunable per-vehicle.

CACHE_TTL = timedelta(hours=1)
CACHE_COLLECTION = "route_cache"


# ── Public API ───────────────────────────────────────────────────────────────


async def distance_matrix_with_blocked(
    stops: list[tuple[float, float]],
    blocked_polygons: list[dict[str, Any]] | None = None,
    avg_speed_kmh: float = DEFAULT_AVG_SPEED_KMH,
) -> tuple[list[list[float]], list[list[int]], bool]:
    """Return (km_matrix, minutes_matrix, used_google).

    Caches the result in Firestore for 1h.
    """
    blocked_polygons = blocked_polygons or []
    cache_key = _matrix_cache_key(stops, blocked_polygons, avg_speed_kmh)
    cached = _read_cache(cache_key)
    if cached:
        return cached["km"], cached["min"], cached.get("usedGoogle", False)

    settings = get_settings()
    if settings.google_maps_api_key:
        try:
            km, mins = await _compute_via_google(stops, settings.google_maps_api_key)
            _apply_blocked_penalty(km, mins, stops, blocked_polygons)
            _write_cache(cache_key, km, mins, used_google=True)
            return km, mins, True
        except Exception as exc:  # noqa: BLE001
            log.warning("gmaps.fallback_to_haversine", reason=str(exc)[:200])

    km = _haversine_km_matrix(stops)
    mins = _minutes_from_km(km, avg_speed_kmh)
    _apply_blocked_penalty(km, mins, stops, blocked_polygons)
    _write_cache(cache_key, km, mins, used_google=False)
    return km, mins, False


# ── Google Routes API ────────────────────────────────────────────────────────


async def _compute_via_google(
    stops: list[tuple[float, float]], api_key: str
) -> tuple[list[list[float]], list[list[int]]]:
    """ComputeRouteMatrix → (km matrix, minutes matrix). Raises on any failure."""
    waypoints = [
        {"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lng}}}}
        for lat, lng in stops
    ]
    body = {
        "origins": waypoints,
        "destinations": waypoints,
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "originIndex,destinationIndex,duration,distanceMeters,status",
    }
    async with httpx.AsyncClient(timeout=20) as cx:
        res = await cx.post(
            "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix",
            json=body,
            headers=headers,
        )
        res.raise_for_status()
        rows = res.json()

    n = len(stops)
    km = [[0.0] * n for _ in range(n)]
    mins = [[0] * n for _ in range(n)]
    for r in rows:
        oi = r.get("originIndex", 0)
        di = r.get("destinationIndex", 0)
        if r.get("status") and r["status"].get("code"):
            continue
        meters = float(r.get("distanceMeters", 0))
        duration_str = r.get("duration", "0s")
        seconds = int(duration_str.rstrip("s")) if duration_str.endswith("s") else 0
        km[oi][di] = round(meters / 1000.0, 3)
        mins[oi][di] = max(1, round(seconds / 60))
    return km, mins


# ── Haversine fallback ───────────────────────────────────────────────────────


def haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    """Great-circle distance × road factor — close enough for VRP demo."""
    p1 = math.radians(a_lat)
    p2 = math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlmb = math.radians(b_lng - a_lng)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a)) * ROAD_FACTOR


def _haversine_km_matrix(stops: list[tuple[float, float]]) -> list[list[float]]:
    n = len(stops)
    km = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            km[i][j] = round(haversine_km(stops[i][0], stops[i][1], stops[j][0], stops[j][1]), 3)
    return km


def _minutes_from_km(km: list[list[float]], speed_kmh: float) -> list[list[int]]:
    return [[max(1, round(d / max(speed_kmh, 1.0) * 60)) for d in row] for row in km]


# ── Blocked-area penalty ────────────────────────────────────────────────────


def _apply_blocked_penalty(
    km: list[list[float]],
    mins: list[list[int]],
    stops: list[tuple[float, float]],
    blocked_polygons: list[dict[str, Any]],
) -> None:
    """If a straight line between two stops crosses a blocked area, multiply the
    travel cost by 5x. Crude but enough for the demo — UPS does similar penalty
    encoding for road closures.
    """
    if not blocked_polygons:
        return
    for i in range(len(stops)):
        for j in range(len(stops)):
            if i == j:
                continue
            mid_lat = (stops[i][0] + stops[j][0]) / 2
            mid_lng = (stops[i][1] + stops[j][1]) / 2
            for poly in blocked_polygons:
                if _point_in_polygon(mid_lat, mid_lng, poly):
                    km[i][j] *= 5
                    mins[i][j] *= 5
                    break


def _point_in_polygon(lat: float, lng: float, poly: dict[str, Any]) -> bool:
    """Ray-casting test against the first ring of a `{rings:[{points:[]}]}` polygon."""
    rings = poly.get("rings") or []
    if not rings:
        return False
    points = rings[0].get("points") or []
    if len(points) < 3:
        return False
    inside = False
    j = len(points) - 1
    for i, p in enumerate(points):
        pi_lat, pi_lng = p["lat"], p["lng"]
        pj_lat, pj_lng = points[j]["lat"], points[j]["lng"]
        intersect = ((pi_lng > lng) != (pj_lng > lng)) and (
            lat < (pj_lat - pi_lat) * (lng - pi_lng) / ((pj_lng - pi_lng) or 1e-12) + pi_lat
        )
        if intersect:
            inside = not inside
        j = i
    return inside


# ── Cache ────────────────────────────────────────────────────────────────────


def _matrix_cache_key(
    stops: list[tuple[float, float]],
    blocked_polygons: list[dict[str, Any]],
    speed: float,
) -> str:
    raw = json.dumps(
        {"stops": stops, "blocked": blocked_polygons, "speed": speed},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _read_cache(key: str) -> dict[str, Any] | None:
    try:
        snap = get_firestore().collection(CACHE_COLLECTION).document(key).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        expires_at = data.get("expiresAt")
        if isinstance(expires_at, datetime) and expires_at < datetime.now(timezone.utc):
            return None
        # Matrices stored as JSON strings (Firestore disallows nested arrays).
        if isinstance(data.get("km"), str):
            data["km"] = json.loads(data["km"])
        if isinstance(data.get("min"), str):
            data["min"] = json.loads(data["min"])
        return data
    except Exception as exc:  # noqa: BLE001
        log.warning("gmaps.cache_read_failed", error=str(exc))
        return None


def _write_cache(
    key: str, km: list[list[float]], mins: list[list[int]], *, used_google: bool
) -> None:
    try:
        # Firestore can't store nested arrays directly — JSON-stringify the matrices.
        get_firestore().collection(CACHE_COLLECTION).document(key).set(
            {
                "km": json.dumps(km),
                "min": json.dumps(mins),
                "usedGoogle": used_google,
                "createdAt": fb_firestore.SERVER_TIMESTAMP,
                "expiresAt": datetime.now(timezone.utc) + CACHE_TTL,
            }
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("gmaps.cache_write_failed", error=str(exc))
