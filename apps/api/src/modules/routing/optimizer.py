"""Top-level route optimizer — dispatches between Google Route Optimization API
(production / when service-account credentials are available) and the OR-Tools
fallback. The fallback is the runtime path for the current build.

Architecture (BLUEPRINT Phase 6 Module 5):
  primary path  → Google Route Optimization API (`routeoptimization.googleapis.com`)
                  - requires OAuth2 / service account, NOT API key
                  - 1,000 free Enterprise events / month
  fallback      → OR-Tools VRPTW (this module)
                  - runs locally, no network
                  - same input/output contract → call-sites are unchanged

When `GOOGLE_APPLICATION_CREDENTIALS` is set AND the service account has
`roles/routeoptimization.editor`, we'll attempt the Google API first. Until
COMMIT 10 wires that, we always fall through.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.core.logging import get_logger
from src.modules.routing import gmaps, ortools_fallback
from src.modules.routing.models import (
    OptimizeRequest,
    OptimizeStop,
    OptimizeVehicle,
)

log = get_logger("relief.routing.optimizer")


async def optimize(
    *,
    stops: list[OptimizeStop],
    vehicles: list[OptimizeVehicle],
    blocked_polygons: list[dict[str, Any]] | None = None,
    time_limit_seconds: int = 8,
    start_dt: datetime | None = None,
) -> tuple[list[ortools_fallback.SolvedRoute], list[tuple[float, float]], str, bool]:
    """Run the optimizer. Returns:
      (solved_routes, locations, computed_by, blocked_areas_applied)

    Locations are returned because the router needs them to build RouteStop ETAs.
    """
    start_dt = start_dt or datetime.now(timezone.utc).replace(microsecond=0)
    blocked_polygons = blocked_polygons or []

    # ── Attempt Google Route Optimization API (placeholder) ──────────────────
    # Real wiring lands in COMMIT 10 once a service account is provisioned.
    # When ready, this branch builds an OptimizeToursRequest and POSTs to
    # `routeoptimization.googleapis.com/v1/projects/{p}:optimizeTours`,
    # then translates the response back to SolvedRoute objects.
    if _google_route_optimization_available():
        try:
            log.info("optimizer.google_path", stops=len(stops), vehicles=len(vehicles))
            return await _optimize_with_google(
                stops, vehicles, blocked_polygons, start_dt
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("optimizer.google_failed_fallback", reason=str(exc)[:200])

    # ── OR-Tools fallback (runtime path) ─────────────────────────────────────
    log.info("optimizer.ortools_path", stops=len(stops), vehicles=len(vehicles))

    if not vehicles:
        return [], [], "ortools", False

    # Build a single shared depot. For COMMIT 6 we assume all vehicles depart from
    # the first vehicle's startLocation; multi-depot routing lands later.
    depot_lat = vehicles[0].startLocation.lat
    depot_lng = vehicles[0].startLocation.lng

    locations: list[tuple[float, float]] = [(depot_lat, depot_lng)]
    demands: list[float] = [0.0]
    service: list[int] = [0]
    windows: list[tuple[int, int]] = [(0, 24 * 60)]
    for s in stops:
        locations.append((s.location.lat, s.location.lng))
        demands.append(s.demand_kg)
        service.append(s.serviceMin)
        tw = s.timeWindow
        windows.append(
            ortools_fallback.minutes_from_window(start_dt, tw.start if tw else None, tw.end if tw else None)
        )

    avg_speed = vehicles[0].avgSpeedKmh if vehicles else gmaps.DEFAULT_AVG_SPEED_KMH
    km, mins, _used_google = await gmaps.distance_matrix_with_blocked(
        locations, blocked_polygons, avg_speed
    )

    inp = ortools_fallback.SolverInput(
        locations=locations,
        demands_kg=demands,
        time_windows_min=windows,
        service_min=service,
        vehicle_capacities_kg=[v.capacityKg for v in vehicles],
        distance_km_matrix=km,
        time_min_matrix=mins,
        start_dt=start_dt,
        time_limit_seconds=time_limit_seconds,
    )
    routes = ortools_fallback.solve(inp)
    return routes, locations, "ortools", bool(blocked_polygons)


# ── Google Route Optimization API stub (kept for the architecture deck) ────


def _google_route_optimization_available() -> bool:
    """True only when a usable service-account credential is configured.

    For the demo build this returns False (we use OR-Tools). When COMMIT 10
    wires Cloud Run with a service account, the env-var probe below flips on
    automatically.
    """
    import os
    return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))


async def _optimize_with_google(
    stops: list[OptimizeStop],
    vehicles: list[OptimizeVehicle],
    blocked_polygons: list[dict[str, Any]],
    start_dt: datetime,
) -> tuple[list[ortools_fallback.SolvedRoute], list[tuple[float, float]], str, bool]:
    """Placeholder for the Google Route Optimization API integration.

    Will:
      - Build an OptimizeToursRequest from `stops` + `vehicles`.
      - Encode `blocked_polygons` as `avoid_polygons` constraints.
      - POST to `routeoptimization.googleapis.com/v1/projects/{P}:optimizeTours`.
      - Translate the response back to SolvedRoute objects.

    Until then, raise so the caller falls through to OR-Tools.
    """
    raise NotImplementedError(
        "Google Route Optimization API requires a service account; using OR-Tools fallback."
    )
