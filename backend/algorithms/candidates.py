"""Candidate helpers: edge keys, similarity, Yen k-shortest (own code)."""

from __future__ import annotations

import heapq

from ..graph.snapping import path_edges
from .baseline import dijkstra


def edge_key(path: list) -> frozenset:
    return frozenset(zip(path, path[1:]))


def too_similar(path: list, accepted: list[list], limit: float) -> bool:
    ek = edge_key(path)
    if not ek:
        return True
    for other in accepted:
        ok = edge_key(other)
        if len(ek & ok) / min(len(ek), len(ok)) > limit:
            return True
    return False


def free_time(G, path: list) -> float:
    return sum(float(e.get("free_time_s", 0.0)) for e in path_edges(G, path))


def yen_k_shortest(G, source, target, k: int, max_spurs: int = 40):
    """Own Yen's algorithm over our Dijkstra (loopless k-shortest paths).

    `max_spurs` caps spur Dijkstras per accepted path (even sampling along the
    path) — cuts runtime ~4x on big graphs with negligible diversity loss.
    """
    first = dijkstra(G, source, target)
    if not first["reachable"]:
        raise RuntimeError("destination unreachable")
    A = [(first["path"], first["cost"])]
    cands: list = []
    seen = {tuple(first["path"])}
    for it in range(1, k):
        prev_path = A[it - 1][0]
        spur_idx = list(range(len(prev_path) - 1))
        if len(spur_idx) > max_spurs:
            step = len(spur_idx) / max_spurs
            spur_idx = [spur_idx[int(i * step)] for i in range(max_spurs)]
        for i in spur_idx:
            spur, root = prev_path[i], prev_path[:i + 1]
            banned = set()
            for p, _ in A:
                if len(p) > i + 1 and p[:i + 1] == root:
                    for kk in (G.get_edge_data(p[i], p[i + 1]) or {}):
                        banned.add((p[i], p[i + 1], kk))
            saved = []
            for key in banned:
                if G.has_edge(*key):
                    saved.append((key, dict(G.get_edge_data(*key))))
                    G.remove_edge(*key)
            try:
                res = dijkstra(G, spur, target)
            finally:
                for (u, v, kk), dd in saved:
                    G.add_edge(u, v, key=kk, **dd)
            if not res["reachable"]:
                continue
            full = root[:-1] + res["path"]
            key = tuple(full)
            if key in seen or len(set(full)) != len(full):
                continue
            seen.add(key)
            rc = free_time(G, root) if len(root) > 1 else 0.0
            heapq.heappush(cands, (rc + res["cost"], full))
        if not cands:
            break
        c, p = heapq.heappop(cands)
        A.append((p, c))
    return A


def generate_candidates(G, source, target, threshold, max_candidates,
                        penalty_factor, penalty_rounds, overlap):
    """Yen micro-alternatives + penalty-based distinct corridors.

    Returns (paths, free_times); paths[0] is the free-flow shortest.
    """
    import math

    best = dijkstra(G, source, target)
    if not best["reachable"]:
        raise RuntimeError("destination unreachable from source")
    accepted = [best["path"]]
    for path, cost in yen_k_shortest(G, source, target, max_candidates * 2):
        if len(accepted) >= max_candidates:
            break
        if cost > (1.0 + threshold) * best["cost"] or cost <= 0:
            continue
        if too_similar(path, accepted, overlap):
            continue
        accepted.append(path)
    penalties: dict = {}
    step = math.log(max(penalty_factor, 1.01))
    for _ in range(penalty_rounds):
        if len(accepted) >= max_candidates:
            break
        saved = []
        for u, v, kk, d in list(G.edges(keys=True, data=True)):
            pen = penalties.get((u, v, kk), 0.0)
            if pen:
                saved.append(((u, v, kk), d["free_time_s"]))
                d["free_time_s"] = d["free_time_s"] * (1.0 + pen)
        try:
            res = dijkstra(G, source, target)
        finally:
            for (u, v, kk), val in saved:
                if G.has_edge(u, v, kk):
                    G[u][v][kk]["free_time_s"] = val
        if not res["reachable"]:
            break
        fc = free_time(G, res["path"])
        if fc > (1.0 + threshold) * best["cost"]:
            break
        if not too_similar(res["path"], accepted, overlap):
            accepted.append(res["path"])
        for a, b in zip(res["path"], res["path"][1:]):
            for kk in (G.get_edge_data(a, b) or {}):
                key = (a, b, kk)
                penalties[key] = penalties.get(key, 0.0) + step
    return accepted, [free_time(G, p) for p in accepted]


