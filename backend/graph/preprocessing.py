"""Graph preprocessing: normalize weights, drop artifacts, keep LCC.

Steps:
  1. Drop edges shorter than MIN_EDGE_LENGTH_M (geometry artifacts).
  2. Fill missing speed from the highway-class table (flag speed_estimated).
  3. Fill lanes; estimate capacity = lanes x per-lane rate (always estimated:
     OpenStreetMap never ships capacities).
  4. Edge weights: length_m, free_time_s = length / speed.
  5. Keep the largest weakly connected component so any snapped OD pair in
     the region routes (undirected connectivity; one-way structure kept).
"""

from __future__ import annotations

import logging
import re

import networkx as nx

from .config import (
    DEFAULT_SPEED_KMH,
    LANE_CAPACITY_VPH,
    MIN_CAPACITY_VPH,
    MIN_EDGE_LENGTH_M,
    NETWORK_TYPE,
    SPEED_BY_HIGHWAY,
)

log = logging.getLogger("flowtwin.preprocess")


def primary_highway(value) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else "unclassified"
    return str(value or "unclassified").split(";")[0].strip() or "unclassified"


def parse_speed(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for v in value:
            s = parse_speed(v)
            if s:
                return s
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", str(value))
    if not m:
        return None
    v = float(m.group(1))
    if "mph" in str(value):
        v *= 1.60934
    return v if v > 0 else None


def lane_count(value, oneway: bool) -> int:
    v = value[0] if isinstance(value, (list, tuple)) and value else value
    try:
        lanes = int(float(str(v))) if v is not None else None
    except (ValueError, TypeError):
        lanes = None
    if lanes and not oneway and lanes >= 2:
        lanes = max(1, lanes // 2)  # OSM lanes tag counts both directions
    return lanes if lanes and lanes > 0 else 1


def capacity_vph(highway: str, lanes: int) -> float:
    return max(lanes * LANE_CAPACITY_VPH.get(highway, 900.0), MIN_CAPACITY_VPH)


def preprocess(G: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Apply the full normalization pipeline; see module docstring."""
    G = G.copy()
    dropped = 0
    for u, v, k, d in list(G.edges(keys=True, data=True)):
        length = float(d.get("length", 0.0) or 0.0)
        if length < MIN_EDGE_LENGTH_M:
            G.remove_edge(u, v, k)
            dropped += 1
            continue
        hw = primary_highway(d.get("highway"))
        speed = parse_speed(d.get("maxspeed")) or parse_speed(d.get("speed"))
        estimated = speed is None
        if speed is None:
            speed = SPEED_BY_HIGHWAY.get(hw, DEFAULT_SPEED_KMH)
        lanes = lane_count(d.get("lanes"), bool(d.get("oneway", False)))
        d["highway"] = hw
        d["oneway"] = bool(d.get("oneway", False))
        d["speed_kmh"] = float(speed)
        d["speed_estimated"] = bool(estimated)
        d["lanes"] = int(lanes)
        d["capacity_vph"] = float(capacity_vph(hw, lanes))
        d["capacity_estimated"] = True
        d["length"] = float(length)
        d["length_m"] = float(length)
        d["free_time_s"] = float(length) / max(float(speed) / 3.6, 0.5)
        name = d.get("name", "")
        d["name"] = name if isinstance(name, str) else "; ".join(map(str, name or []))
        # Keep geometry as a Shapely object — it's needed for coordinate extraction
        # in path_coords() and export_geojson(). Only convert truly non-serializable
        # junk fields to strings.
        for junk in ("reversed",):
            if junk in d and not isinstance(d[junk], (int, float, str, bool)):
                try:
                    d[junk] = str(d[junk])
                except Exception:  # noqa: BLE001
                    d.pop(junk, None)
    if dropped:
        log.info("preprocess: dropped %d artifact edges", dropped)
    if G.number_of_nodes() and not nx.is_weakly_connected(G):
        largest = max(nx.weakly_connected_components(G), key=len)
        G = G.subgraph(largest).copy()
        log.info("preprocess: kept largest WCC (%d nodes)", G.number_of_nodes())
    for _, d in G.nodes(data=True):
        if "x" in d:
            d["x"] = float(d["x"])
        if "y" in d:
            d["y"] = float(d["y"])
    G.graph["flowtwin"] = {
        "network_type": NETWORK_TYPE,
        "weights": "length_m/free_time_s",
        "capacity": "estimated (lanes x highway rate)",
    }
    return G

