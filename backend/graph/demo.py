"""Demo graph: synthetic road network with genuinely distinct corridors."""

from __future__ import annotations
import math
import networkx as nx


def make_demo_graph(seed=42) -> nx.MultiDiGraph:
    """Create a graph with 3 distinct highway corridors between NW and SE."""
    G = nx.MultiDiGraph()
    rows, cols = 10, 10
    nodes = {}
    for i in range(rows):
        for j in range(cols):
            lat = 12.95 - i * (0.10 / (rows - 1))
            lon = 80.05 + j * (0.20 / (cols - 1))
            node_id = i * cols + j
            nodes[(i, j)] = node_id
            G.add_node(node_id, y=round(lat, 6), x=round(lon, 6), street=f"n_{i}_{j}")

    def _add(u, v, cls, speed, cap):
        u_data = G.nodes[u]
        v_data = G.nodes[v]
        dist = math.hypot(
            (v_data["y"] - u_data["y"]) * 111320,
            (v_data["x"] - u_data["x"]) * 111320 * math.cos(math.radians((u_data["y"] + v_data["y"]) / 2))
        )
        free_time = dist / (speed / 3.6) if speed > 0 else 1.0
        G.add_edge(u, v, length_m=round(dist, 1), free_time_s=round(free_time, 2),
                   capacity_vph=cap, highway=cls, name=f"{cls}_{u}_{v}")

    # Grid roads (slow, residential)
    for i in range(rows):
        for j in range(cols):
            if j < cols - 1:
                _add(nodes[(i, j)], nodes[(i, j + 1)], "residential", 25, 600)
                _add(nodes[(i, j + 1)], nodes[(i, j)], "residential", 25, 600)
            if i < rows - 1:
                _add(nodes[(i, j)], nodes[(i + 1, j)], "residential", 25, 600)
                _add(nodes[(i + 1, j)], nodes[(i, j)], "residential", 25, 600)

    # Highway 1: North (row 0) - fast but LOW capacity (bottleneck corridor)
    for j in range(cols - 1):
        _add(nodes[(0, j)], nodes[(0, j + 1)], "highway_north", 80, 1200)
        _add(nodes[(0, j + 1)], nodes[(0, j)], "highway_north", 80, 1200)

    # Highway 2: South (row 9) - slower but HIGH capacity (absorbs overflow)
    for j in range(cols - 1):
        _add(nodes[(9, j)], nodes[(9, j + 1)], "highway_south", 55, 2500)
        _add(nodes[(9, j + 1)], nodes[(9, j)], "highway_south", 55, 2500)

    # Highway 3: Central (row 4) - medium speed, medium capacity
    for j in range(cols - 1):
        _add(nodes[(4, j)], nodes[(4, j + 1)], "highway_central", 50, 1800)
        _add(nodes[(4, j + 1)], nodes[(4, j)], "highway_central", 50, 1800)

    # Connector roads between highways and grid (high capacity - not the bottleneck)
    for i in range(rows - 1):
        _add(nodes[(i, 0)], nodes[(i + 1, 0)], "connector", 35, 3000)
        _add(nodes[(i + 1, 0)], nodes[(i, 0)], "connector", 35, 3000)
        _add(nodes[(i, cols - 1)], nodes[(i + 1, cols - 1)], "connector", 35, 3000)
        _add(nodes[(i + 1, cols - 1)], nodes[(i, cols - 1)], "connector", 35, 3000)

    return G


def demo_source_dest():
    """Return source (NW) and destination (SE) for demo graph."""
    rows, cols = 10, 10
    source_id = 0 * cols + 0  # (0, 0) - NW
    dest_id = 9 * cols + 9    # (9, 9) - SE
    src_lat, src_lon = 12.95, 80.05
    dst_lat, dst_lon = 12.85, 80.25
    return (
        {"node": source_id, "lat": src_lat, "lon": src_lon, "snap_distance_m": 0, "road": "start"},
        {"node": dest_id, "lat": dst_lat, "lon": dst_lon, "snap_distance_m": 0, "road": "end"}
    )
