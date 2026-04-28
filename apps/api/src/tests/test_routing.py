"""VRPTW + gmaps unit tests.

The OR-Tools tests build the SolverInput by hand so they don't need Firestore.
gmaps fallback paths run without GOOGLE_MAPS_API_KEY because we explicitly use
`haversine_km`. The Firestore-cache layer is exercised by the integration smoke
test (run separately).
"""
import math
from datetime import datetime, timedelta, timezone

import pytest

from src.modules.routing.gmaps import (
    _point_in_polygon,
    _apply_blocked_penalty,
    _haversine_km_matrix,
    haversine_km,
)


def test_haversine_known_distance() -> None:
    # Cox's Bazar (21.4272, 92.0058) to Chittagong (22.3569, 91.7832) ≈ 110 km × 1.35 ≈ 148 km.
    d = haversine_km(21.4272, 92.0058, 22.3569, 91.7832)
    assert 130 < d < 170


def test_matrix_is_symmetric_and_zero_diagonal() -> None:
    stops = [(21.43, 92.00), (21.45, 92.02), (22.35, 91.78)]
    km = _haversine_km_matrix(stops)
    for i in range(len(stops)):
        assert km[i][i] == 0
    for i in range(len(stops)):
        for j in range(len(stops)):
            assert math.isclose(km[i][j], km[j][i], rel_tol=1e-9)


def test_blocked_polygon_inflates_cost() -> None:
    stops = [(21.40, 92.00), (21.50, 92.00)]
    km = [[0.0, 10.0], [10.0, 0.0]]
    mins = [[0, 30], [30, 0]]
    blocked = [
        {
            "rings": [
                {
                    "points": [
                        {"lat": 21.44, "lng": 91.95},
                        {"lat": 21.44, "lng": 92.05},
                        {"lat": 21.46, "lng": 92.05},
                        {"lat": 21.46, "lng": 91.95},
                    ]
                }
            ]
        }
    ]
    _apply_blocked_penalty(km, mins, stops, blocked)
    assert km[0][1] == 50.0
    assert mins[0][1] == 150


def test_point_in_polygon_inside_and_outside() -> None:
    poly = {
        "rings": [
            {
                "points": [
                    {"lat": 0, "lng": 0},
                    {"lat": 10, "lng": 0},
                    {"lat": 10, "lng": 10},
                    {"lat": 0, "lng": 10},
                ]
            }
        ]
    }
    assert _point_in_polygon(5, 5, poly) is True
    assert _point_in_polygon(15, 15, poly) is False


@pytest.mark.skipif(
    pytest.importorskip("ortools", reason="OR-Tools not installed yet") is None,
    reason="OR-Tools missing",
)
def test_vrptw_three_stops_two_vehicles() -> None:
    """Smoke test: 3 stops, 2 vehicles, capacity-bounded — solver returns assignments
    that respect capacity and visit every stop exactly once.
    """
    from src.modules.routing.ortools_fallback import SolverInput, solve

    locations = [
        (21.4272, 92.0058),  # 0 = depot (Cox's Bazar warehouse)
        (21.45, 92.02),       # 1
        (21.50, 91.99),       # 2
        (21.42, 92.05),       # 3
    ]
    n = len(locations)

    # Symmetric distance/time matrices via haversine.
    km = _haversine_km_matrix(locations)
    mins = [[max(1, round(d / 30 * 60)) for d in row] for row in km]

    inp = SolverInput(
        locations=locations,
        demands_kg=[0, 200, 800, 300],
        time_windows_min=[(0, 24 * 60)] * n,
        service_min=[0, 10, 10, 10],
        vehicle_capacities_kg=[600, 1000],
        distance_km_matrix=km,
        time_min_matrix=mins,
        start_dt=datetime.now(timezone.utc),
        time_limit_seconds=4,
    )
    routes = solve(inp)
    assert len(routes) >= 1

    # Every non-depot node should appear in exactly one route.
    visited: set[int] = set()
    for r in routes:
        for n_idx in r.stop_indexes:
            if n_idx != 0:
                assert n_idx not in visited, f"node {n_idx} visited twice"
                visited.add(n_idx)
    assert visited == {1, 2, 3}

    # Capacity must be respected.
    for r in routes:
        load = sum(inp.demands_kg[i] for i in r.stop_indexes if i != 0)
        assert load <= inp.vehicle_capacities_kg[r.vehicle_idx]


@pytest.mark.skipif(
    pytest.importorskip("ortools", reason="OR-Tools not installed yet") is None,
    reason="OR-Tools missing",
)
def test_vrptw_respects_time_window() -> None:
    """If a stop has a tight time window, the solver must arrive within it."""
    from src.modules.routing.ortools_fallback import SolverInput, solve

    locations = [(21.4272, 92.0058), (21.50, 92.10)]
    km = _haversine_km_matrix(locations)
    mins = [[max(1, round(d / 30 * 60)) for d in row] for row in km]

    inp = SolverInput(
        locations=locations,
        demands_kg=[0, 50],
        time_windows_min=[(0, 24 * 60), (60, 120)],  # stop must be served between 60 and 120 min
        service_min=[0, 5],
        vehicle_capacities_kg=[1000],
        distance_km_matrix=km,
        time_min_matrix=mins,
        start_dt=datetime.now(timezone.utc),
        time_limit_seconds=4,
    )
    routes = solve(inp)
    assert routes
    r = routes[0]
    # Index 1 in stop_indexes corresponds to either stop 0 (depot start) or stop 1 (delivery).
    # The arrival at stop 1 must be within [60, 120].
    for i, node in enumerate(r.stop_indexes):
        if node == 1:
            assert 60 <= r.arrival_min[i] <= 120
