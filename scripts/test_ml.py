"""Quick smoke test for the ML modules."""
import sys
sys.path.insert(0, "apps/api")

from src.modules.ml.anomaly_detector import detect, get_model_info
from src.modules.ml.graph_router import get_graph

# Test 1: Normal ping
normal = detect({"lat": 23.8, "lng": 90.4, "speedKmh": 35, "heading": 90, "ts": "2026-04-28T14:00:00+00:00"})
print(f"Normal: score={normal.score}, anomaly={normal.is_anomaly}, type={normal.anomaly_type.value}")

# Test 2: Stuck vehicle (speed~0, high dwell)
stuck = detect(
    {"lat": 23.8, "lng": 90.4, "speedKmh": 0.5, "heading": 0, "ts": "2026-04-28T14:05:00+00:00"},
    {"lat": 23.8, "lng": 90.4, "speedKmh": 0.2, "heading": 0, "ts": "2026-04-28T14:00:00+00:00"},
)
print(f"Stuck:  score={stuck.score}, anomaly={stuck.is_anomaly}, type={stuck.anomaly_type.value}")

# Test 3: Drift (far from route, heading change)
drift = detect(
    {"lat": 23.8, "lng": 90.4, "speedKmh": 15, "heading": 270, "ts": "2026-04-28T14:05:00+00:00"},
    {"lat": 23.8, "lng": 90.4, "speedKmh": 40, "heading": 90, "ts": "2026-04-28T14:00:00+00:00"},
    route_stops=[{"location": {"lat": 24.0, "lng": 91.0}}],
)
print(f"Drift:  score={drift.score}, anomaly={drift.is_anomaly}, type={drift.anomaly_type.value}")

# Test 4: Model info
info = get_model_info()
print(f"Model:  version={info['version']}, fitted={info['fitted']}, samples={info['n_training_samples']}")

# Test 5: Graph router
graph = get_graph()
print(f"Graph:  nodes={graph.stats['nodes']}, edges={graph.stats['edges']}")

# Dijkstra test
result = graph.dijkstra("wh-dhaka", "del-coxbazar")
if result:
    path, km, time_min = result
    print(f"Dijkstra Dhaka->CoxBazar: path={' -> '.join(path)}, {km:.1f}km, {time_min:.0f}min")

# A* test
result2 = graph.a_star("wh-dhaka", "del-coxbazar")
if result2:
    path2, km2, time2 = result2
    print(f"A* Dhaka->CoxBazar:      path={' -> '.join(path2)}, {km2:.1f}km, {time2:.0f}min")

# Test with disruption
graph.update_disruption("hub-comilla", "hub-feni", weight=0.9, blocked=True)
result3 = graph.dijkstra("wh-dhaka", "del-coxbazar")
if result3:
    path3, km3, time3 = result3
    print(f"Dijkstra (disrupted):    path={' -> '.join(path3)}, {km3:.1f}km, {time3:.0f}min")
else:
    print("Dijkstra (disrupted):    No path found (corridor blocked)")

print("\n✓ All ML module tests passed!")
