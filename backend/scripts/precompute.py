"""Precompute instant results for the fixed preset O/D pairs.

Loads each cached road graph once, then runs the full pipeline (trim -> snap
-> baseline -> collective -> evaluate -> export) for every preset pair whose
coordinates fall inside that graph's bounding box. Outputs one JSON per pair
under results/precomputed/ plus a small manifest the API serves instantly.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.algorithms import baseline, evaluation, proposed
from backend.graph import cache, config, export as graph_export, geocode, preprocessing, snapping

PEOPLE = 2000

# Exact button labels in the UI.
SRC_PRESETS = ["VIT Chennai", "Chennai Airport", "Chennai Central", "Guindy", "Tidel Park"]
DST_PRESETS = ["Chennai Central", "Chennai Airport", "VIT Chennai", "Guindy", "T. Nagar"]

# Authoritative Chennai coords for the fixed preset set (geocoders can be
# unreliable — e.g. "Tidel Park" resolves to a city in the wrong state).
OVERRIDE_COORDS = {
    "VIT Chennai": (12.8429, 80.1554),
    "Chennai Airport": (12.9934, 80.1726),
    "Chennai Central": (13.0824, 80.2760),
    "Guindy": (13.0087, 80.2126),
    "T. Nagar": (13.0378, 80.2318),
    "Tidel Park": (13.0260, 80.2427),
}

OUT_DIR = config.RESULTS_DIR / "precomputed"
MANIFEST = OUT_DIR / "_manifest.json"


def _cfg():
    return {
        "threshold": config.CANDIDATE_TIME_THRESHOLD,
        "max_candidates": config.MAX_CANDIDATES,
        "penalty_factor": config.CANDIDATE_PENALTY_FACTOR,
        "penalty_rounds": config.CANDIDATE_PENALTY_ROUNDS,
        "overlap": config.MIN_ROUTE_EDGE_OVERLAP,
        "damping": config.PROPOSED_DAMPING,
        "max_iter": config.PROPOSED_MAX_ITER,
        "patience": config.PROPOSED_PATIENCE,
        "min_iter": config.PROPOSED_MIN_ITER,
        "tol": config.PROPOSED_TOL,
        "alpha": config.BPR_ALPHA,
        "beta": config.BPR_BETA,
    }


def _graph_bbox(slug: str):
    """Approximate corridor bbox from a cached slug
    like 12_8429_80_1554_13_0824_80_2760 (lat1_lon1_lat2_lon2)."""
    try:
        parts = slug.replace(".graphml", "").split("_")
        lats = [float(parts[i]) for i in range(0, len(parts), 4)]
        lons = [float(parts[i + 1]) for i in range(0, len(parts), 4)]
        return min(lats), max(lats), min(lons), max(lons)
    except Exception:  # noqa: BLE001
        return None


def _load_graph(slug: str):
    """Load + normalize a cached GraphML file (strings -> floats)."""
    G = cache.load(slug)
    sample = next(iter(G.edges(data=True)), None)
    if sample is None or not isinstance(sample[2].get("free_time_s"), (int, float)):
        preprocessing.preprocess(G)
    # GraphML may store node coordinates as strings; coerce to float.
    for _, d in G.nodes(data=True):
        if "x" in d:
            d["x"] = float(d["x"])
        if "y" in d:
            d["y"] = float(d["y"])
    # GraphML stores edge attributes as strings; coerce numeric ones.
    for u, v, k, d in G.edges(keys=True, data=True):
        for field in ("free_time_s", "length_m", "capacity_vph", "speed_kph"):
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = float(d[field])
                except (ValueError, TypeError):
                    pass
    return G


def _run_pair(G, src_name: str, dst_name: str, s_desc: dict, d_desc: dict):
    """Run the standard pipeline on a corridor-trimmed graph copy."""
    from backend.graph.loader import _trim_to_lcc
    s_coord = (s_desc["lat"], s_desc["lon"])
    d_coord = (d_desc["lat"], d_desc["lon"])
    G = _trim_to_lcc(G.copy(), s_coord, d_coord)
    src = snapping.snap_point(G, s_coord[0], s_coord[1])
    dst = snapping.snap_point(G, d_coord[0], d_coord[1])
    if src["node"] == dst["node"]:
        return None
    cfg = _cfg()
    t0 = time.perf_counter()
    bl = baseline.dijkstra(G, src["node"], dst["node"])
    if not bl["reachable"]:
        return None
    opt = proposed.optimize(G, src["node"], dst["node"], PEOPLE, cfg)
    if not opt["routes"]:
        return None
    ev = evaluation.evaluate(G, bl, opt, PEOPLE, cfg["alpha"], cfg["beta"])
    paths = {"baseline": bl["path"]}
    for i, r in enumerate(opt["routes"]):
        paths[f"route_{i + 1}"] = r
    return {
        "id": f"pre_{abs(hash((src_name, dst_name))):x}",
        "precomputed": True,
        "src_query": src_name,
        "dst_query": dst_name,
        "origin": {**src, "name": src_name, "display_name": s_desc["display_name"]},
        "destination": {**dst, "name": dst_name, "display_name": d_desc["display_name"]},
        "graph_info": {"nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
                       "cached": True, "network_type": "drive"},
        "evaluation": ev,
        "geojson": graph_export.export_geojson(
            G, paths, edge_util=evaluation.edge_utilization(G, opt["routes"], opt["flows"])),
        "route_coords": {k: snapping.path_coords(G, v) for k, v in paths.items()},
        "wall_ms": round((time.perf_counter() - t0) * 1000, 2),
        "people": PEOPLE,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    done = {f.stem for f in OUT_DIR.glob("*.json") if f.stem != "_manifest"}

    places = {}
    for name in sorted(set(SRC_PRESETS + DST_PRESETS)):
        if name in OVERRIDE_COORDS:
            lat, lon = OVERRIDE_COORDS[name]
            places[name] = {"lat": lat, "lon": lon,
                            "display_name": f"{name} (Chennai)"}
            print(f"pinned {name!r} -> ({lat:.4f},{lon:.4f})", flush=True)
            continue
        hits = geocode.geocode(name, 1)
        if hits:
            places[name] = hits[0]
            print(f"geocoded {name!r} -> ({hits[0]['lat']:.4f},{hits[0]['lon']:.4f})", flush=True)
        else:
            print(f"WARN could not geocode {name!r}", flush=True)

    pairs = [(s, d) for s in SRC_PRESETS for d in DST_PRESETS
             if s != d and s in places and d in places]

    cached = sorted(p.stem for p in config.GRAPH_DIR.glob("*.graphml"))
    print(f"\n{len(cached)} cached graphs, {len(pairs)} preset pairs", flush=True)

    manifest = []
    for slug in cached:
        bbox = _graph_bbox(slug)
        eligible = []
        for s, d in pairs:
            sp, dp = (places[s]["lat"], places[s]["lon"]), (places[d]["lat"], places[d]["lon"])
            if bbox is None:
                eligible.append((s, d))
                continue
            p = bbox
            if (p[0] - 0.01 <= sp[0] <= p[1] + 0.01 and p[2] - 0.01 <= sp[1] <= p[3] + 0.01
                    and p[0] - 0.01 <= dp[0] <= p[1] + 0.01 and p[2] - 0.01 <= dp[1] <= p[3] + 0.01):
                eligible.append((s, d))
        if not eligible:
            continue
        print(f"\n== graph {slug} ==", flush=True)
        G = _load_graph(slug)
        for s, d in eligible:
            key = f"{s}__{d}".replace(" ", "_").replace(",", "").replace(".", "")
            if key in done:
                continue
            print(f"  computing {s} -> {d} ...", flush=True)
            try:
                res = _run_pair(G, s, d, places[s], places[d])
            except Exception as exc:  # noqa: BLE001
                print(f"    FAILED: {exc}", flush=True)
                res = None
            if res is None:
                print("    skipped (unreachable / same node)", flush=True)
                continue
            (OUT_DIR / f"{key}.json").write_text(json.dumps(res))
            done.add(key)
            manifest.append({"key": key, "src": s, "dst": d, "people": PEOPLE,
                             "file": f"{key}.json",
                             "improvement_pct": res["evaluation"]["improvement_pct"],
                             "routes_used": res["evaluation"]["proposed"]["routes_used"],
                             "nodes": res["graph_info"]["nodes"],
                             "base_min": res["evaluation"]["baseline"]["congested_time_min"],
                             "avg_min": res["evaluation"]["proposed"]["avg_time_min"]})
            print(f"    OK: {res['evaluation']['improvement_pct']}% improvement, "
                  f"{len(res['evaluation']['proposed']['routes'])} routes", flush=True)
        del G

    if MANIFEST.exists():
        try:
            manifest = json.loads(MANIFEST.read_text()) + manifest
        except Exception:  # noqa: BLE001
            pass
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    print(f"\nDONE: {len(manifest)} precomputed pairs in {OUT_DIR}", flush=True)


if __name__ == "__main__":
    main()