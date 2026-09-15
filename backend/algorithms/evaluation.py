"""Evaluation: baseline-vs-proposed metrics from actual execution.

Nothing is fabricated: every number derives from the graph + algorithm
outputs. Person-time is network-wide (shared edges counted once).
"""

from __future__ import annotations

from ..graph.congestion import edge_time_s


def _edge_flows(G, routes, flows):
    fmap: dict = {}
    for path, f in zip(routes, flows):
        if f <= 0:
            continue
        for a, b in zip(path, path[1:]):
            data = G.get_edge_data(a, b) or {}
            kk = min(data, key=lambda k: float(data[k].get("free_time_s", 1e18)))
            fmap[(a, b, kk)] = fmap.get((a, b, kk), 0.0) + f
    return fmap


def _route_stats(G, path, fmap, alpha, beta):
    dist = 0.0
    t_free = 0.0
    t_cong = 0.0
    for a, b in zip(path, path[1:]):
        data = G.get_edge_data(a, b) or {}
        kk = min(data, key=lambda k: float(data[k].get("free_time_s", 1e18)))
        d = data[kk]
        key = (a, b, kk)
        x = fmap.get(key, 0.0)
        cap = float(d.get("capacity_vph", 100.0))
        dist += float(d.get("length_m", 0.0))
        t_free += float(d["free_time_s"])
        t_cong += edge_time_s(float(d["free_time_s"]), x, cap, alpha, beta)
    return dist, t_free, t_cong


def evaluate(G, baseline, proposed, n_people, alpha, beta) -> dict:
    """Compare baseline (all-N on shortest) vs proposed allocation.

    Returns a dict with baseline/proposed/savings sections. Every value is
    computed from actual graph + algorithm output — nothing fabricated.
    """
    bpath = baseline["path"]
    bfmap = _edge_flows(G, [bpath], [n_people])
    bdist, bfree, bcong = _route_stats(G, bpath, bfmap, alpha, beta)
    b_person = n_people * bcong / 60.0  # person-minutes

    pfmap = _edge_flows(G, proposed["routes"], proposed["flows"])
    routes_out = []
    for i, (path, f) in enumerate(zip(proposed["routes"], proposed["flows"])):
        dist, free, cong = _route_stats(G, path, pfmap, alpha, beta)
        routes_out.append({
            "id": i + 1, "flow": int(f),
            "share_pct": round(100.0 * f / n_people, 2) if n_people else 0.0,
            "distance_m": round(dist, 1), "free_time_s": round(free, 2),
            "congested_time_s": round(cong, 2),
            "congested_time_min": round(cong / 60.0, 2),
        })

    p_person = proposed["total_person_time_min"]
    p_avg = (p_person / n_people) if n_people else 0.0

    # utilization stats
    utils = []
    for (u, v, kk), x in pfmap.items():
        d = G[u][v][kk]
        cap = max(float(d.get("capacity_vph", 100.0)), 1.0)
        utils.append(x / cap)
    max_u = max(utils) if utils else 0.0
    avg_u = (sum(utils) / len(utils)) if utils else 0.0
    cong_edges = sum(1 for u in utils if u > 0.8)

    time_saved = b_person - p_person
    pct = (time_saved / b_person * 100.0) if b_person > 0 else 0.0

    return {
        "nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
        "people": n_people,
        "baseline": {
            "distance_m": round(bdist, 1),
            "distance_km": round(bdist / 1000.0, 3),
            "free_time_min": round(bfree / 60.0, 2),
            "congested_time_min": round(bcong / 60.0, 2),
            "total_person_time_min": round(b_person, 2),
            "runtime_ms": round(baseline["runtime_ms"], 2),
            "nodes_explored": baseline["nodes_explored"],
            "edges_processed": baseline["edges_processed"],
        },
        "proposed": {
            "routes_used": len(proposed["routes"]),
            "routes": routes_out,
            "avg_time_min": round(p_avg, 2),
            "total_person_time_min": round(p_person, 2),
            "runtime_ms": round(proposed["runtime_ms"], 2),
            "iterations": proposed["iterations"],
            "converged": proposed["converged"],
            "convergence_reason": proposed["reason"],
            "max_utilization": round(max_u, 3),
            "avg_utilization": round(avg_u, 3),
            "congested_edges": cong_edges,
        },
        "time_saved_min": round(time_saved, 2),
        "time_saved_hours": round(time_saved / 60.0, 2),
        "improvement_pct": round(pct, 2),
        "flows_sum_ok": sum(proposed["flows"]) == n_people,
    }


def edge_utilization(G, routes, flows) -> dict:
    """Aggregate edge utilization (flow/capacity) per undirected road segment.

    Returns {(u, v): util} using the best (lowest free-time) parallel edge.
    Used for the Google-Maps-style congestion heat layer.
    """
    fmap: dict = {}
    for path, f in zip(routes, flows):
        if f <= 0:
            continue
        for a, b in zip(path, path[1:]):
            data = G.get_edge_data(a, b) or {}
            if not data:
                continue
            kk = min(data, key=lambda k: float(data[k].get("free_time_s", 1e18)))
            fmap[(a, b, kk)] = fmap.get((a, b, kk), 0.0) + f
    out: dict = {}
    for (a, b, kk), x in fmap.items():
        cap = max(float(G[a][b][kk].get("capacity_vph", 100.0)), 1.0)
        u = x / cap
        if (a, b) in out:
            out[(a, b)] = max(out[(a, b)], u)
        elif (b, a) in out:
            out[(b, a)] = max(out[(b, a)], u)
        else:
            out[(a, b)] = u
    return out


def bottlenecks(G, routes, flows, top_n=5) -> list[dict]:
    """Rank edges by utilization (flow/capacity) — the constrained links."""
    fmap = _edge_flows(G, routes, flows)
    scored = []
    for (u, v, kk), x in fmap.items():
        d = G[u][v][kk]
        cap = max(float(d.get("capacity_vph", 100.0)), 1.0)
        util = x / cap
        free = float(d["free_time_s"])
        cong = edge_time_s(free, x, cap)
        scored.append({
            "edge": f"{u}-{v}",
            "name": str(d.get("name", "")),
            "highway": str(d.get("highway", "")),
            "flow": round(x, 1),
            "capacity_vph": round(cap, 1),
            "utilization": round(util, 3),
            "free_time_s": round(free, 2),
            "congested_time_s": round(cong, 2),
            "delay_s": round(cong - free, 2),
        })
    scored.sort(key=lambda r: -r["utilization"])
    return scored[:top_n]

