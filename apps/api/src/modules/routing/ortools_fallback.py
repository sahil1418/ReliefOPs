"""OR-Tools VRPTW solver — capacity + time windows + blocked-area penalty.

This is the runtime path for COMMIT 6. Even when Google Route Optimization API
is wired (production), OR-Tools remains the on-prem fallback for offline
operation, which matters in disaster zones with intermittent connectivity.

Inputs are plain dicts to keep this module Pydantic-free and easily testable.
The router translates between Pydantic models and these dicts.

Algorithm sketch (BLUEPRINT Phase 6 Module 5):
  1. Build distance + time matrices (haversine + road factor by default).
  2. Configure RoutingModel with capacity (kg) and time-window dimensions.
  3. Solve with PATH_CHEAPEST_ARC + GUIDED_LOCAL_SEARCH for `time_limit_seconds`.
  4. Extract the per-vehicle routes, ETAs at each stop, totals.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass
class SolverInput:
    # Index 0 is always the depot. The vehicle starts and ends there.
    locations: list[tuple[float, float]]  # (lat, lng) per stop, depot at index 0
    demands_kg: list[float]                # 0 for depot
    time_windows_min: list[tuple[int, int]]  # minutes from `start_dt` for each stop
    service_min: list[int]                 # minutes spent on-site at each stop
    vehicle_capacities_kg: list[float]
    distance_km_matrix: list[list[float]]
    time_min_matrix: list[list[int]]
    start_dt: datetime
    time_limit_seconds: int = 8


@dataclass
class SolvedRoute:
    vehicle_idx: int
    stop_indexes: list[int]   # ordered list of node indexes (depot endpoints included)
    arrival_min: list[int]    # arrival time in minutes from start_dt for each stop
    depart_min: list[int]
    total_km: float
    total_min: int


def solve(inp: SolverInput) -> list[SolvedRoute]:
    """Run OR-Tools VRPTW. Returns one SolvedRoute per vehicle (may be empty for unused vehicles)."""
    # Local import: ortools is a heavy native dep — keep it out of import time.
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2

    n = len(inp.locations)
    nv = len(inp.vehicle_capacities_kg)
    if n < 2 or nv < 1:
        return []

    mgr = pywrapcp.RoutingIndexManager(n, nv, 0)
    routing = pywrapcp.RoutingModel(mgr)

    # Travel-cost callback (minutes; OR-Tools wants integers).
    def time_cb(i_idx: int, j_idx: int) -> int:
        i = mgr.IndexToNode(i_idx)
        j = mgr.IndexToNode(j_idx)
        return inp.time_min_matrix[i][j] + inp.service_min[j]

    transit_cb_idx = routing.RegisterTransitCallback(time_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_cb_idx)

    # Capacity dimension.
    def demand_cb(i_idx: int) -> int:
        i = mgr.IndexToNode(i_idx)
        return int(round(inp.demands_kg[i]))

    demand_cb_idx = routing.RegisterUnaryTransitCallback(demand_cb)
    routing.AddDimensionWithVehicleCapacity(
        demand_cb_idx,
        0,
        [int(round(c)) for c in inp.vehicle_capacities_kg],
        True,
        "Capacity",
    )

    # Time dimension (minutes from start_dt).
    horizon_min = max(24 * 60, max((tw[1] for tw in inp.time_windows_min), default=24 * 60) + 60)
    routing.AddDimension(
        transit_cb_idx,
        30,             # waiting slack
        horizon_min,    # max time per vehicle
        False,          # don't force start at 0
        "Time",
    )
    time_dim = routing.GetDimensionOrDie("Time")

    for node_idx in range(1, n):
        idx = mgr.NodeToIndex(node_idx)
        tw_start, tw_end = inp.time_windows_min[node_idx]
        time_dim.CumulVar(idx).SetRange(tw_start, tw_end)

    # Allow vehicles to start any time within the depot's window.
    depot_tw_start, depot_tw_end = inp.time_windows_min[0]
    for v in range(nv):
        time_dim.CumulVar(routing.Start(v)).SetRange(depot_tw_start, depot_tw_end)

    # Make stops droppable rather than infeasible — penalize skipping heavily so
    # the solver only drops a stop if it can't fit anywhere.
    skip_penalty = 100_000
    for node_idx in range(1, n):
        routing.AddDisjunction([mgr.NodeToIndex(node_idx)], skip_penalty)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.seconds = max(1, inp.time_limit_seconds)

    solution = routing.SolveWithParameters(params)
    if solution is None:
        return []

    return _extract_routes(mgr, routing, time_dim, solution, inp, nv)


def _extract_routes(
    mgr: Any,
    routing: Any,
    time_dim: Any,
    solution: Any,
    inp: SolverInput,
    nv: int,
) -> list[SolvedRoute]:
    out: list[SolvedRoute] = []
    for v in range(nv):
        idx = routing.Start(v)
        stops: list[int] = []
        arrivals: list[int] = []
        departs: list[int] = []
        prev_node: int | None = None
        total_km = 0.0
        while not routing.IsEnd(idx):
            node = mgr.IndexToNode(idx)
            arr = solution.Min(time_dim.CumulVar(idx))
            dep = arr + inp.service_min[node]
            stops.append(node)
            arrivals.append(arr)
            departs.append(dep)
            if prev_node is not None and prev_node != node:
                total_km += inp.distance_km_matrix[prev_node][node]
            prev_node = node
            idx = solution.Value(routing.NextVar(idx))
        # Append the depot end node so the route is closed.
        end_node = mgr.IndexToNode(idx)
        end_arr = solution.Min(time_dim.CumulVar(idx))
        stops.append(end_node)
        arrivals.append(end_arr)
        departs.append(end_arr)
        if prev_node is not None and prev_node != end_node:
            total_km += inp.distance_km_matrix[prev_node][end_node]

        # If only depot→depot, the vehicle wasn't used; skip.
        if len(stops) <= 2:
            continue

        out.append(
            SolvedRoute(
                vehicle_idx=v,
                stop_indexes=stops,
                arrival_min=arrivals,
                depart_min=departs,
                total_km=round(total_km, 3),
                total_min=int(end_arr),
            )
        )
    return out


def minutes_from_window(
    start_dt: datetime, tw_start: datetime | None, tw_end: datetime | None
) -> tuple[int, int]:
    """Convert absolute timestamps to minutes-from-start_dt."""
    horizon = 24 * 60
    s = 0 if tw_start is None else max(0, int((tw_start - start_dt).total_seconds() / 60))
    e = horizon if tw_end is None else max(s + 1, int((tw_end - start_dt).total_seconds() / 60))
    return s, e


def absolute_time(start_dt: datetime, minutes: int) -> datetime:
    return (start_dt + timedelta(minutes=minutes)).replace(microsecond=0)


# Make sure tzinfo lives somewhere importable for the router.
__all__ = [
    "SolverInput",
    "SolvedRoute",
    "absolute_time",
    "minutes_from_window",
    "solve",
    "timezone",
]
