"""Graph-based shortest-path routing — Dijkstra + A* for supply chain networks.

This module provides a weighted directed graph that models the transit network
(warehouses, distribution hubs, delivery points) as nodes, and road segments
as edges with dynamic weights reflecting:
  - Distance (km)
  - Current traffic / congestion (from fleet velocity data)
  - Disruption risk (from anomaly_detector + disruption_predictor)
  - Road blockage status (from alerts collection)

Integration plan (post-hackathon):
  1. Build graph from Firestore `warehouses` + `disasters` + `alerts`.
  2. On each routing request, overlay live disruption weights.
  3. Run Dijkstra or A* for single-vehicle shortest path.
  4. Feed Dijkstra result as initial solution hint to OR-Tools VRPTW for
     multi-vehicle optimization (replaces PATH_CHEAPEST_ARC).

For now, this module provides the graph primitives + Dijkstra implementation
that can slot into the existing `optimizer.py` dispatcher later.

Complexity: O((V + E) log V) with the min-heap implementation.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Edge:
    to_node: str
    distance_km: float
    base_time_min: float
    disruption_weight: float = 0.0  # 0 = clear, 1 = fully blocked
    is_blocked: bool = False

    @property
    def effective_weight(self) -> float:
        """Combined weight for Dijkstra: time + disruption penalty."""
        if self.is_blocked:
            return float("inf")
        # Disruption adds up to 3x the base time as penalty.
        return self.base_time_min * (1.0 + 2.0 * self.disruption_weight)


@dataclass
class Node:
    id: str
    lat: float
    lng: float
    node_type: str = "waypoint"  # warehouse | hub | delivery | waypoint
    metadata: dict[str, Any] = field(default_factory=dict)


class TransitGraph:
    """Weighted directed graph for the supply chain network."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.adjacency: dict[str, list[Edge]] = {}

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node
        if node.id not in self.adjacency:
            self.adjacency[node.id] = []

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        distance_km: float,
        base_time_min: float,
        disruption_weight: float = 0.0,
        is_blocked: bool = False,
        bidirectional: bool = True,
    ) -> None:
        self.adjacency.setdefault(from_id, []).append(
            Edge(to_id, distance_km, base_time_min, disruption_weight, is_blocked)
        )
        if bidirectional:
            self.adjacency.setdefault(to_id, []).append(
                Edge(from_id, distance_km, base_time_min, disruption_weight, is_blocked)
            )

    def update_disruption(
        self, from_id: str, to_id: str, weight: float, blocked: bool = False
    ) -> None:
        """Dynamically update edge disruption weight (from ML predictions)."""
        for edge in self.adjacency.get(from_id, []):
            if edge.to_node == to_id:
                edge.disruption_weight = weight
                edge.is_blocked = blocked
        # Also update reverse if bidirectional.
        for edge in self.adjacency.get(to_id, []):
            if edge.to_node == from_id:
                edge.disruption_weight = weight
                edge.is_blocked = blocked

    def dijkstra(
        self, start: str, end: str
    ) -> tuple[list[str], float, float] | None:
        """Classic Dijkstra's shortest path.

        Returns:
            (path, total_distance_km, total_time_min) or None if unreachable.
        """
        if start not in self.nodes or end not in self.nodes:
            return None

        # Priority queue: (weight, node_id)
        pq: list[tuple[float, str]] = [(0.0, start)]
        dist: dict[str, float] = {start: 0.0}
        km_at: dict[str, float] = {start: 0.0}
        prev: dict[str, str | None] = {start: None}
        visited: set[str] = set()

        while pq:
            d, u = heapq.heappop(pq)
            if u in visited:
                continue
            visited.add(u)

            if u == end:
                # Reconstruct path.
                path: list[str] = []
                node: str | None = end
                while node is not None:
                    path.append(node)
                    node = prev.get(node)
                path.reverse()
                return path, km_at[end], dist[end]

            for edge in self.adjacency.get(u, []):
                if edge.to_node in visited:
                    continue
                w = edge.effective_weight
                if w == float("inf"):
                    continue
                new_dist = d + w
                if new_dist < dist.get(edge.to_node, float("inf")):
                    dist[edge.to_node] = new_dist
                    km_at[edge.to_node] = km_at[u] + edge.distance_km
                    prev[edge.to_node] = u
                    heapq.heappush(pq, (new_dist, edge.to_node))

        return None  # No path found.

    def a_star(
        self, start: str, end: str
    ) -> tuple[list[str], float, float] | None:
        """A* shortest path using haversine heuristic.

        Same interface as dijkstra() but with better performance for
        geospatial graphs.
        """
        if start not in self.nodes or end not in self.nodes:
            return None

        end_node = self.nodes[end]

        def heuristic(node_id: str) -> float:
            n = self.nodes[node_id]
            # Haversine distance / assumed speed → time estimate.
            km = _haversine_km(n.lat, n.lng, end_node.lat, end_node.lng)
            return km / 60.0 * 60  # Assume 60 km/h → minutes.

        pq: list[tuple[float, float, str]] = [(heuristic(start), 0.0, start)]
        g_score: dict[str, float] = {start: 0.0}
        km_at: dict[str, float] = {start: 0.0}
        prev: dict[str, str | None] = {start: None}
        visited: set[str] = set()

        while pq:
            _, g, u = heapq.heappop(pq)
            if u in visited:
                continue
            visited.add(u)

            if u == end:
                path: list[str] = []
                node: str | None = end
                while node is not None:
                    path.append(node)
                    node = prev.get(node)
                path.reverse()
                return path, km_at[end], g_score[end]

            for edge in self.adjacency.get(u, []):
                if edge.to_node in visited:
                    continue
                w = edge.effective_weight
                if w == float("inf"):
                    continue
                new_g = g + w
                if new_g < g_score.get(edge.to_node, float("inf")):
                    g_score[edge.to_node] = new_g
                    km_at[edge.to_node] = km_at[u] + edge.distance_km
                    prev[edge.to_node] = u
                    f = new_g + heuristic(edge.to_node)
                    heapq.heappush(pq, (f, new_g, edge.to_node))

        return None

    @property
    def stats(self) -> dict[str, Any]:
        total_edges = sum(len(edges) for edges in self.adjacency.values())
        blocked = sum(
            1 for edges in self.adjacency.values()
            for e in edges if e.is_blocked
        )
        disrupted = sum(
            1 for edges in self.adjacency.values()
            for e in edges if e.disruption_weight > 0.3
        )
        return {
            "nodes": len(self.nodes),
            "edges": total_edges,
            "blocked_edges": blocked,
            "disrupted_edges": disrupted,
        }


# ── Graph construction from Firestore ───────────────────────────────────────


def build_demo_graph() -> TransitGraph:
    """Build a demo transit graph for South Asia disaster corridors.

    In production, this would pull from Firestore `warehouses` + road network
    data + live `alerts` collection to dynamically construct the graph.
    """
    g = TransitGraph()

    # Nodes: warehouses and key waypoints.
    nodes = [
        Node("wh-dhaka", 23.8103, 90.4125, "warehouse", {"name": "Dhaka Central Warehouse"}),
        Node("hub-narayanganj", 23.6238, 90.5000, "hub", {"name": "Narayanganj Hub"}),
        Node("hub-comilla", 23.4607, 91.1809, "hub", {"name": "Comilla Transit Hub"}),
        Node("wh-chittagong", 22.3569, 91.7832, "warehouse", {"name": "Chittagong Port Warehouse"}),
        Node("del-coxbazar", 21.4272, 92.0058, "delivery", {"name": "Cox's Bazar Relief Point"}),
        Node("hub-feni", 23.0159, 91.3976, "hub", {"name": "Feni Junction"}),
        Node("wh-sylhet", 24.8949, 91.8687, "warehouse", {"name": "Sylhet Regional Warehouse"}),
        Node("hub-brahmanbaria", 23.9608, 91.1115, "hub", {"name": "Brahmanbaria Hub"}),
        Node("del-teknaf", 20.8627, 92.3014, "delivery", {"name": "Teknaf Delivery Point"}),
        Node("hub-rangamati", 22.6372, 92.1977, "hub", {"name": "Rangamati Hill Hub"}),
    ]
    for n in nodes:
        g.add_node(n)

    # Edges: road segments with distance and estimated time.
    edges = [
        ("wh-dhaka", "hub-narayanganj", 17.0, 35),
        ("hub-narayanganj", "hub-comilla", 95.0, 130),
        ("hub-comilla", "hub-feni", 65.0, 85),
        ("hub-feni", "wh-chittagong", 115.0, 155),
        ("wh-chittagong", "del-coxbazar", 152.0, 210),
        ("del-coxbazar", "del-teknaf", 85.0, 120),
        ("wh-dhaka", "hub-brahmanbaria", 112.0, 150),
        ("hub-brahmanbaria", "wh-sylhet", 133.0, 185),
        ("hub-brahmanbaria", "hub-comilla", 52.0, 70),
        ("wh-chittagong", "hub-rangamati", 77.0, 110),
    ]
    for from_id, to_id, km, time_min in edges:
        g.add_edge(from_id, to_id, km, time_min)

    return g


def apply_disruptions_from_predictions(
    graph: TransitGraph, corridors: list[dict[str, Any]]
) -> None:
    """Overlay ML disruption predictions onto the graph edges.

    Called after `disruption_predictor.predict_disruptions()` to update
    edge weights dynamically before routing.
    """
    for corridor in corridors:
        risk = corridor.get("risk_score", 0)
        if risk < 0.1:
            continue
        # Find edges near the corridor center and apply disruption weight.
        c_lat = corridor.get("center_lat", 0)
        c_lng = corridor.get("center_lng", 0)
        for node_id, edges in graph.adjacency.items():
            node = graph.nodes.get(node_id)
            if not node:
                continue
            dist = _haversine_km(node.lat, node.lng, c_lat, c_lng)
            if dist <= 20:  # 20km radius of influence.
                for edge in edges:
                    edge.disruption_weight = max(edge.disruption_weight, risk * 0.8)
                    if risk > 0.9:
                        edge.is_blocked = True


# ── Utility ─────────────────────────────────────────────────────────────────


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(a, 1.0)))


# ── Singleton graph instance ────────────────────────────────────────────────


_GRAPH: TransitGraph | None = None


def get_graph() -> TransitGraph:
    """Get or create the singleton transit graph."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_demo_graph()
    return _GRAPH
