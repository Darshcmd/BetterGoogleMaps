"""Reproducible experiments. Run: python experiments/run_experiment.py

Downloads a graph once, runs baseline + proposed for several demand levels.
Saves results/ as JSON. Works offline once a graph is cached in data/graphs/.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import sys
from pathlib import Path
# project root on path so `backend.*` imports resolve everywhere (tests, runner, CLI)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.graph.config import (BPR_ALPHA, BPR_BETA, CANDIDATE_PENALTY_FACTOR,
                          CANDIDATE_PENALTY_ROUNDS, CANDIDATE_TIME_THRESHOLD,
                          MAX_CANDIDATES, MIN_ROUTE_EDGE_OVERLAP,
                          PROPOSED_DAMPING, PROPOSED_MAX_ITER, PROPOSED_PATIENCE,
                          PROPOSED_TOL, PROPOSED_MIN_ITER, RESULTS_DIR)
from backend.graph.geocode import geocode
from backend.graph.loader import get_graph
from backend.graph.snapping import snap_point
from backend.algorithms.baseline import dijkstra
from backend.algorithms.proposed import optimize
from backend.algorithms.evaluation import evaluate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("flowtwin.experiment")

PRESETS = {
    "vit_to_central": ("VIT Chennai", "Chennai Central"),
    "vit_to_airport": ("VIT Chennai", "Chennai Airport"),
    "vit_to_tnagar": ("VIT Chennai", "T Nagar Chennai"),
    "airport_to_central": ("Chennai Airport", "Chennai Central"),
}


def run(source_name, dest_name, demands, slug=None, use_cache=True,
        alpha=BPR_ALPHA, beta=BPR_BETA):
    log.info("geocoding source=%s dest=%s", source_name, dest_name)
    try:
        s = geocode(source_name)[0]
        d = geocode(dest_name)[0]
    except Exception as exc:
        raise RuntimeError(f"geocoding failed: {exc}") from exc
    log.info("loading graph for %.4f,%.4f -> %.4f,%.4f",
             s["lat"], s["lon"], d["lat"], d["lon"])
    G, info = get_graph((s["lat"], s["lon"]), (d["lat"], d["lon"]),
                        slug=slug, use_cache=use_cache)
    src = snap_point(G, s["lat"], s["lon"])
    dst = snap_point(G, d["lat"], d["lon"])
    log.info("graph: %d nodes, %d edges; snap src=%s dst=%s",
             G.number_of_nodes(), G.number_of_edges(),
             src["road"], dst["road"])

    cfg = {
        "threshold": CANDIDATE_TIME_THRESHOLD, "max_candidates": MAX_CANDIDATES,
        "penalty_factor": CANDIDATE_PENALTY_FACTOR,
        "penalty_rounds": CANDIDATE_PENALTY_ROUNDS,
        "overlap": MIN_ROUTE_EDGE_OVERLAP, "damping": PROPOSED_DAMPING,
        "max_iter": PROPOSED_MAX_ITER, "patience": PROPOSED_PATIENCE,
        "min_iter": PROPOSED_MIN_ITER, "tol": PROPOSED_TOL,
        "alpha": alpha, "beta": beta,
    }
    baseline = dijkstra(G, src["node"], dst["node"])
    if not baseline["reachable"]:
        raise RuntimeError("destination unreachable from source")

    all_results = []
    for n in demands:
        log.info("--- demand = %d travellers ---", n)
        opt = optimize(G, src["node"], dst["node"], n, cfg)
        ev = evaluate(G, baseline, opt, n, alpha, beta)
        ev["demand"] = n
        all_results.append(ev)
        log.info("  baseline %.1f min | proposed %.1f min (%.1f%%) | %d routes",
                 ev["baseline"]["congested_time_min"],
                 ev["proposed"]["avg_time_min"],
                 ev["improvement_pct"], ev["proposed"]["routes_used"])

    return {
        "source": {"name": source_name, "lat": s["lat"], "lon": s["lon"]},
        "destination": {"name": dest_name, "lat": d["lat"], "lon": d["lon"]},
        "graph_info": info, "alpha": alpha, "beta": beta,
        "results": all_results,
    }


def main():
    p = argparse.ArgumentParser(description="FlowTwin experiments")
    p.add_argument("--preset", choices=list(PRESETS), default="vit_to_central")
    p.add_argument("--source", help="overrides preset source name")
    p.add_argument("--dest", help="overrides preset dest name")
    p.add_argument("--demands", default="2,5,10,20,50,100,500,1000")
    p.add_argument("--slug", help="graph cache slug")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--out", help="output JSON path")
    args = p.parse_args()

    src_name = args.source or PRESETS[args.preset][0]
    dst_name = args.dest or PRESETS[args.preset][1]
    demands = sorted({int(x) for x in args.demands.split(",")})

    t0 = time.perf_counter()
    out = run(src_name, dst_name, demands, slug=args.slug,
              use_cache=not args.no_cache)
    dt = time.perf_counter() - t0

    out["wall_seconds"] = round(dt, 2)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out or RESULTS_DIR / f"{args.preset}.json")
    out_path.write_text(json.dumps(out, indent=2))
    log.info("wrote %s (%.1fs total)", out_path, dt)
    print(f"\n{'demand':>8}  {'baseline_min':>12}  {'proposed_min':>12}  "
          f"{'improvement':>11}  {'routes':>6}")
    for r in out["results"]:
        print(f"{r['demand']:>8}  {r['baseline']['congested_time_min']:>12.2f}  "
              f"{r['proposed']['avg_time_min']:>12.2f}  "
              f"{r['improvement_pct']:>10.2f}%  {r['proposed']['routes_used']:>6}")


if __name__ == "__main__":
    main()
