"""Proposed algorithm: collective flow assignment under BPR congestion.

Problem formulation (multi-person collective routing):
  Given directed road graph G=(V,E) with per-edge free-flow time t_e^0 and
  capacity c_e, and demand of N travellers from s to t, choose route flows
  f_1..f_k over k candidate paths (sum f_i = N) minimizing network-wide
  person-time  sum_e x_e * t_e(x_e), where x_e is the total flow on edge e
  and t_e follows the BPR congestion function.

Method (system-optimal assignment, projected gradient on the simplex):
  C(f) = sum_e x_e t_e(x_e) is convex in route flows (BPR beta >= 1, edge
  flows linear in f). Its gradient wrt route i is the route's marginal-cost
  sum  g_i = sum_{e in r_i} t0_e (1 + alpha (beta+1) (x_e/c_e)^beta).
  1. Seed a corridor set via Yen k-shortest + penalty diversification.
  2. Each iteration: compute edge flows x and marginal sums g; take a
     projected-gradient step  f <- P(f - s g)  onto {f >= 0, sum f = N}
     with Armijo backtracking on C (sufficient decrease).
  3. Dynamic discovery: probe the *marginal-cost* network for a new path;
     admit it iff its marginal sum beats the worst used route (the exact
     Frank-Wolfe admission test) and it is sufficiently distinct.
  4. Stop on tolerance/patience/max-iterations; track best-so-far.
  At the optimum every used route has equal marginal cost — flows spread
  across as many corridors as capacity requires (not a fixed split).

Complexity per iteration: O(k * L + E) for gradients plus one Dijkstra
probe; Armijo line search costs O(k * L) per trial step.
"""

from __future__ import annotations

import math
import time

from ..graph.congestion import edge_time_s
from ..graph.snapping import path_edges
from .baseline import dijkstra
from .candidates import free_time, generate_candidates, too_similar


def _edge_flow_map(G, routes, flows):
    flow = {}
    for path, f in zip(routes, flows):
        if f <= 0:
            continue
        for a, b in zip(path, path[1:]):
            data = G.get_edge_data(a, b) or {}
            key = min(data, key=lambda kk: float(data[kk].get("free_time_s", 1e18)))
            flow[(a, b, key)] = flow.get((a, b, key), 0.0) + f
    return flow


def _route_time(G, path, flow, alpha, beta):
    total = 0.0
    for a, b in zip(path, path[1:]):
        data = G.get_edge_data(a, b) or {}
        kk = min(data, key=lambda k: float(data[k].get("free_time_s", 1e18)))
        d = data[kk]
        total += edge_time_s(float(d["free_time_s"]),
                             flow.get((a, b, kk), 0.0),
                             float(d.get("capacity_vph", 100.0)), alpha, beta)
    return total


def _person_time(G, routes, flows, alpha, beta):
    flow = _edge_flow_map(G, routes, flows)
    total = 0.0
    seen = set()
    for path in routes:
        for a, b in zip(path, path[1:]):
            data = G.get_edge_data(a, b) or {}
            kk = min(data, key=lambda k: float(data[k].get("free_time_s", 1e18)))
            if (a, b, kk) in seen:
                continue
            seen.add((a, b, kk))
            d = data[kk]
            x = flow.get((a, b, kk), 0.0)
            total += x * edge_time_s(float(d["free_time_s"]), x,
                                     float(d.get("capacity_vph", 100.0)),
                                     alpha, beta)
    return total / 60.0  # person-minutes


def _integerize(flows, n):
    out = [max(0, int(math.floor(f))) for f in flows]
    rem = n - sum(out)
    if rem > 0:
        order = sorted(range(len(flows)),
                       key=lambda i: flows[i] - out[i], reverse=True)
        for i in order[:rem]:
            out[i] += 1
    return out


def _marginal_cost(free_s, flow, cap, alpha, beta):
    """Marginal-cost weight t_e(x_e) + x_e t_e'(x_e) for a BPR edge."""
    return free_s * (1.0 + alpha * (beta + 1.0)
                     * (flow / max(cap, 1.0)) ** beta)


def _route_marginal_sums(G, routes, fmap, alpha, beta):
    """Gradient of person-time wrt each route flow (shared edges per-route)."""
    sums = []
    for path in routes:
        total = 0.0
        for a, b in zip(path, path[1:]):
            data = G.get_edge_data(a, b) or {}
            kk = min(data, key=lambda k: float(data[k].get("free_time_s", 1e18)))
            d = data[kk]
            total += _marginal_cost(
                float(d["free_time_s"]), fmap.get((a, b, kk), 0.0),
                float(d.get("capacity_vph", 100.0)), alpha, beta)
        sums.append(total)
    return sums


def _project_simplex(v, z):
    """Project v onto {x >= 0, sum(x) = z} (Held/Wang simplex projection)."""
    n = len(v)
    u = sorted(v, reverse=True)
    css = 0.0
    rho = 1
    for j in range(1, n + 1):
        css += u[j - 1]
        if u[j - 1] + (z - css) / j > 0.0:
            rho = j
    theta = (sum(u[:rho]) - z) / rho
    return [max(x - theta, 0.0) for x in v]


def optimize(G, source, target, n_people, cfg) -> dict:
    """Run the collective optimizer. Returns routes/flows/times/iterations.

    `cfg` carries threshold/max_candidates/penalties/overlap/damping/
    max_iter/patience/min_iter/tol/alpha/beta (see experiments/runner).
    """
    t0 = time.perf_counter()
    base = dijkstra(G, source, target)
    if not base["reachable"]:
        raise RuntimeError("destination unreachable from source")
    routes, _free = generate_candidates(
        G, source, target, cfg["threshold"], cfg["max_candidates"],
        cfg["penalty_factor"], cfg["penalty_rounds"], cfg["overlap"])
    flows = [float(n_people)] + [0.0] * (len(routes) - 1)
    total = _person_time(G, routes, flows, cfg["alpha"], cfg["beta"])
    best = (list(routes), list(flows), total)
    history = [{"iteration": 0, "person_time_min": total,
                "routes": len(routes)}]
    prev, non_improving = total, 0
    converged, reason, it = False, "max_iterations", 0

    for it in range(1, cfg["max_iter"] + 1):
        fmap = _edge_flow_map(G, routes, flows)
        margs = _route_marginal_sums(G, routes, fmap,
                                     cfg["alpha"], cfg["beta"])
        # dynamic discovery: shortest path on the *marginal-cost* network.
        # A new corridor is useful iff it undercuts the worst used route
        # (Frank-Wolfe admission test) — this is what lets the solution
        # open more routes as demand grows.
        saved = []
        for u, v, kk, d in list(G.edges(keys=True, data=True)):
            x = fmap.get((u, v, kk), 0.0)
            f = 1.0 + cfg["alpha"] * (cfg["beta"] + 1.0) * (
                (x / max(float(d.get("capacity_vph", 100.0)), 1.0))
                ** cfg["beta"])
            saved.append(((u, v, kk), d["free_time_s"]))
            d["free_time_s"] = d["free_time_s"] * f
        try:
            probe = dijkstra(G, source, target)
        finally:
            for (u, v, kk), val in saved:
                if G.has_edge(u, v, kk):
                    G[u][v][kk]["free_time_s"] = val
        new_route = False
        if probe["reachable"] and len(routes) < cfg["max_candidates"]:
            fc = free_time(G, probe["path"])
            if (probe["cost"] < max(margs) - 1e-9
                    and fc <= (1.0 + cfg["threshold"]) * _free[0]
                    and not too_similar(probe["path"], routes,
                                        cfg["overlap"])):
                routes.append(probe["path"])
                flows.append(0.0)
                margs.append(probe["cost"])
                new_route = True
        # projected-gradient step: f <- P(f - s*g) onto the simplex
        # {f >= 0, sum f = N}, Armijo backtracking on person-time
        gmax = max(abs(m) for m in margs) or 1.0
        step0 = float(n_people) / gmax
        gamma, accepted = 1.0, False
        for _ in range(12):
            cand = _project_simplex(
                [f - gamma * step0 * m for f, m in zip(flows, margs)],
                float(n_people))
            cand_t = _person_time(G, routes, cand, cfg["alpha"], cfg["beta"])
            if cand_t < total - 1e-9 * (1.0 + abs(total)):
                flows, total, accepted = cand, cand_t, True
                break
            gamma *= 0.5
        if total < best[2] - 1e-9:
            best = (list(routes), list(flows), total)
            non_improving = 0
        else:
            non_improving += 1
        history.append({"iteration": it, "person_time_min": total,
                        "routes": len(routes), "new_route": new_route})
        if it >= cfg["min_iter"] and non_improving >= cfg["patience"]:
            converged, reason = True, "no_improvement"
            break
        rel = abs(prev - total) / max(prev, 1.0)
        if it >= cfg["min_iter"] and rel < cfg["tol"]:
            converged, reason = True, "tolerance"
            break
        prev = total

    routes, flows, _ = best
    int_flows = _integerize(flows, n_people)
    kept = sorted([(r, f) for r, f in zip(routes, int_flows) if f > 0],
                  key=lambda rf: -rf[1])[:cfg["max_candidates"]]
    routes = [k[0] for k in kept] or [routes[0]]
    flows = [k[1] for k in kept] or [n_people]
    if sum(flows) != n_people:  # keep exact after truncation
        flows[0] += n_people - sum(flows)
    fmap = _edge_flow_map(G, routes, flows)
    route_times = [_route_time(G, r, fmap, cfg["alpha"], cfg["beta"])
                   for r in routes]
    total = _person_time(G, routes, flows, cfg["alpha"], cfg["beta"])
    ms = (time.perf_counter() - t0) * 1000.0
    return {"routes": routes, "flows": flows, "route_times_s": route_times,
            "total_person_time_min": total, "iterations": it,
            "converged": converged, "reason": reason, "history": history,
            "candidates_found": len(routes), "runtime_ms": ms,
            "baseline_path": base["path"], "baseline": base}


