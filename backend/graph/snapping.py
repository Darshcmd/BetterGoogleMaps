"""Snapping: coordinates -> nearest graph node (pipeline step 5).

Uses OSMnx nearest-node search on real graphs (no fake nodes), with a
pure-NetworkX fallback so unit tests on tiny synthetic graphs work too.
"""

from __future__ import annotations

import logging
import math

import networkx as nx

log = logging.getLogger("flowtwin.snap")

# Memoize the dominant strongly-connected component per graph instance.
_scc_cache: dict = {}


def _dominant_scc(G):
    """Nodes of the largest strongly-connected component (directed).

    Snapping into this set guarantees any two OD points are mutually
    reachable, sidestepping one-way / airport dead-end nodes that break
    directed shortest-path search.
    """
    key = (id(G), G.number_of_nodes())
    if key in _scc_cache:
        return _scc_cache[key]
    try:
        comps = list(nx.strongly_connected_components(G))
        dom = max(comps, key=len) if comps else set(G.nodes())
    except Exception:  # noqa: BLE001
        dom = set(G.nodes())
    _scc_cache[key] = dom
    return dom


def _nearest_bruteforce(G, lat: float, lon: float, subset=None):
    best, best_d = None, float("inf")
    nodes = G.nodes(data=True) if subset is None else ((n, G.nodes[n]) for n in subset)
    for n, d in nodes:
        if "x" not in d or "y" not in d:
            continue
        dist = math.hypot((d["y"] - lat) * 111320.0,
                          (d["x"] - lon) * 111320.0 * math.cos(math.radians(lat)))
        if dist < best_d:
            best, best_d = n, dist
    if best is None:
        raise RuntimeError("graph has no georeferenced nodes")
    return best, best_d


def snap_point(G, lat: float, lon: float) -> dict:
    """Snap (lat, lon) to the nearest graph node within the dominant SCC.

    Returns {node, lat, lon, snap_distance_m, road}.
    """
    try:
        import osmnx as ox
        node, dist = ox.distance.nearest_nodes(G, X=lon, Y=lat, return_dist=True)
        node = int(node)
    except Exception:  # noqa: BLE001
        node, dist = _nearest_bruteforce(G, lat, lon)
    # Re-home to the mutually-reachable core when needed.
    if G.number_of_nodes() > 1:
        dom = _dominant_scc(G)
        if node not in dom:
            log.info("snap node %s outside dominant SCC; re-homing", node)
            node, dist = _nearest_bruteforce(G, lat, lon, subset=dom)
    data = G.nodes[node]
    road = ""
    for _, _, _, d in G.out_edges(node, keys=True, data=True):
        if d.get("name"):
            road = str(d["name"])
            break
    if not road:
        for _, _, _, d in G.in_edges(node, keys=True, data=True):
            if d.get("name"):
                road = str(d["name"])
                break
    return {"node": node, "lat": float(data["y"]), "lon": float(data["x"]),
            "snap_distance_m": round(float(dist), 1),
            "road": road or "nearest mapped road"}


def path_edges(G, path: list) -> list[dict]:
    """Cheapest parallel edge per node hop (by free_time_s)."""
    out = []
    for a, b in zip(path, path[1:]):
        data = G.get_edge_data(a, b)
        if not data:
            raise RuntimeError(f"no edge {a} -> {b} (graph changed?)")
        out.append(min(data.values(),
                       key=lambda d: float(d.get("free_time_s", 1e18))))
    return out


def path_length_m(G, path: list) -> float:
    return sum(float(e.get("length_m", 0.0)) for e in path_edges(G, path))


def path_free_time_s(G, path: list) -> float:
    return sum(float(e.get("free_time_s", 0.0)) for e in path_edges(G, path))


def path_coords(G, path: list) -> list[list[float]]:
    """Lon/lat coordinate list following edge geometry (for Leaflet)."""
    coords: list[list[float]] = []
    for a, b in zip(path, path[1:]):
        data = G.get_edge_data(a, b)
        best = min(data.values(), key=lambda d: float(d.get("free_time_s", 1e18)))
        geom = best.get("geometry")
        seg = ([[x, y] for x, y in geom.coords] if geom is not None
               else [[G.nodes[a]["x"], G.nodes[a]["y"]],
                     [G.nodes[b]["x"], G.nodes[b]["y"]]])
        coords.extend(seg if not coords else seg[1:])
    return coords
