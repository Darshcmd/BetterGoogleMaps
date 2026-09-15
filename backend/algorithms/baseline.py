"""Baseline algorithm: classic Dijkstra shortest path (own implementation).

This is the conventional solution: every traveller independently takes the
free-flow shortest route. It ignores congestion entirely, which is exactly
why the proposed collective algorithm can beat it under demand.

Own binary-heap implementation with explored-node/edge counters (needed for
evaluation). NetworkX is used only for graph storage, NOT for the search.
"""

from __future__ import annotations

import heapq
import time


def _neighbors(G, u):
    for _, v, k, d in G.out_edges(u, keys=True, data=True):
        yield v, float(d.get("free_time_s", 0.0)), (u, v, k)


def dijkstra(G, source, target, weight="free_time_s", bidirectional=True) -> dict:
    """Shortest path via our own implementation.

    Bidirectional search (alternating frontiers, meeting-point check) by
    default — roughly 2x fewer explored nodes, as used in cppRouting/OSRM.
    Falls back to unidirectional when bidirectional=False.
    """
    t0 = time.perf_counter()
    if source == target:
        return {"path": [source], "cost": 0.0, "distance_m": 0.0,
                "nodes_explored": 1, "edges_processed": 0,
                "runtime_ms": 0.0, "reachable": True}
    if source not in G or target not in G:
        return {"path": [], "cost": float("inf"), "distance_m": 0.0,
                "nodes_explored": 0, "edges_processed": 0,
                "runtime_ms": (time.perf_counter() - t0) * 1000.0,
                "reachable": False}
    if not bidirectional:
        return _dijkstra_forward(G, source, target)
    return _dijkstra_bidirectional(G, source, target)


def _dijkstra_forward(G, source, target) -> dict:
    t0 = time.perf_counter()
    dist = {source: 0.0}
    prev: dict = {}
    visited: set = set()
    edges_processed = 0
    pq = [(0.0, source)]
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == target:
            break
        for v, w, _key in _neighbors(G, u):
            edges_processed += 1
            if v in visited:
                continue
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    ms = (time.perf_counter() - t0) * 1000.0
    return _finalize(G, source, target, dist, prev, visited, edges_processed)


def _dijkstra_bidirectional(G, source, target) -> dict:
    """Alternate frontier expansion; stop when the frontiers meet."""
    t0 = time.perf_counter()
    INF = float("inf")
    dist_f = {source: 0.0}
    dist_b = {target: 0.0}
    prev_f: dict = {}
    prev_b: dict = {}
    done_f: set = set()
    done_b: set = set()
    pq_f = [(0.0, source)]
    pq_b = [(0.0, target)]
    edges_processed = 0
    best = INF
    meet = None
    forward = True
    while pq_f and pq_b:
        if forward:
            d, u = heapq.heappop(pq_f)
            if u in done_f:
                forward = False
                continue
            done_f.add(u)
            if dist_f.get(u, INF) + dist_b.get(u, INF) < best:
                best = dist_f.get(u, INF) + dist_b.get(u, INF)
                meet = u
            if best < INF and (not pq_f or not pq_b or
                               pq_f[0][0] + pq_b[0][0] >= best):
                break
            for v, w, _k in _neighbors(G, u):
                edges_processed += 1
                if v in done_f:
                    continue
                nd = d + w
                if nd < dist_f.get(v, INF):
                    dist_f[v] = nd
                    prev_f[v] = u
                    heapq.heappush(pq_f, (nd, v))
        else:
            d, u = heapq.heappop(pq_b)
            if u in done_b:
                forward = True
                continue
            done_b.add(u)
            if dist_f.get(u, INF) + dist_b.get(u, INF) < best:
                best = dist_f.get(u, INF) + dist_b.get(u, INF)
                meet = u
            if best < INF and (not pq_f or not pq_b or
                               pq_f[0][0] + pq_b[0][0] >= best):
                break
            for v, w, _k in _in_neighbors(G, u):
                edges_processed += 1
                if v in done_b:
                    continue
                nd = d + w
                if nd < dist_b.get(v, INF):
                    dist_b[v] = nd
                    prev_b[v] = u
                    heapq.heappush(pq_b, (nd, v))
        forward = not forward
    ms = (time.perf_counter() - t0) * 1000.0
    if meet is None or best == INF:
        return {"path": [], "cost": INF, "distance_m": 0.0,
                "nodes_explored": len(done_f) + len(done_b),
                "edges_processed": edges_processed,
                "runtime_ms": ms, "reachable": False}
    # Reconstruct: source .. meet (via prev_f) + meet .. target (via prev_b)
    fwd = [meet]
    while fwd[-1] != source:
        fwd.append(prev_f[fwd[-1]])
    fwd.reverse()
    bwd = []
    cur = meet
    while cur != target:
        cur = prev_b[cur]
        bwd.append(cur)
    path = fwd + bwd
    dist_m = 0.0
    for a, b in zip(path, path[1:]):
        data = G.get_edge_data(a, b)
        best_e = min(data.values(), key=lambda d: float(d.get("free_time_s", 1e18)))
        dist_m += float(best_e.get("length_m", 0.0))
    return {"path": path, "cost": best, "distance_m": dist_m,
            "nodes_explored": len(done_f) + len(done_b),
            "edges_processed": edges_processed,
            "runtime_ms": ms, "reachable": True}


def _in_neighbors(G, u):
    for v, _w, k, d in G.in_edges(u, keys=True, data=True):
        yield v, float(d.get("free_time_s", 0.0)), (v, u, k)


def _finalize(G, source, target, dist, prev, visited, edges_processed) -> dict:
    ms = 0.0
    if target not in dist:
        return {"path": [], "cost": float("inf"), "distance_m": 0.0,
                "nodes_explored": len(visited),
                "edges_processed": edges_processed,
                "runtime_ms": ms, "reachable": False}
    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    path.reverse()
    dist_m = 0.0
    for a, b in zip(path, path[1:]):
        data = G.get_edge_data(a, b)
        best = min(data.values(), key=lambda d: float(d.get("free_time_s", 1e18)))
        dist_m += float(best.get("length_m", 0.0))
    return {"path": path, "cost": dist[target], "distance_m": dist_m,
            "nodes_explored": len(visited),
            "edges_processed": edges_processed,
            "runtime_ms": ms, "reachable": True}
