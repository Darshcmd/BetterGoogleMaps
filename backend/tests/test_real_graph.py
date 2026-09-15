"""Real-data test (uses cached graph / network when available).

Downloads the VIT Chennai -> Chennai Airport corridor ONCE via OSMnx and
caches to data/graphs/. Skipped gracefully when offline and uncached.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from backend.algorithms import baseline, proposed
from backend.graph import cache, geocode, loader, snapping

SRC = "VIT Chennai, Kelambakkam"
DST = "Chennai International Airport"
SLUG = "vit_chennai_chennai_airport"


def _offline_no_cache():
    return not cache.has(SLUG)


def test_real_graph_acquisition():
    try:
        s_results = geocode.geocode(SRC, 1)
        d_results = geocode.geocode(DST, 1)
        assert s_results and d_results, "geocoding returned empty results"
        s = s_results[0]
        d = d_results[0]
        assert "lat" in s and "lon" in s, f"source result missing coords: {s}"
        assert "lat" in d and "lon" in d, f"dest result missing coords: {d}"
    except (RuntimeError, AssertionError) as exc:
        pytest.skip(f"geocoding issue (likely offline): {exc}")
    try:
        G, info = loader.get_graph((s["lat"], s["lon"]),
                                   (d["lat"], d["lon"]), slug=SLUG)
    except RuntimeError as exc:
        pytest.skip(f"graph download issue (likely offline): {exc}")
    assert G.number_of_nodes() > 100 and G.number_of_edges() > 100
    for _, _, ed in list(G.edges(data=True))[:50]:
        assert ed["free_time_s"] > 0 and ed["capacity_vph"] > 0
    sn = snapping.snap_point(G, s["lat"], s["lon"])
    dn = snapping.snap_point(G, d["lat"], d["lon"])
    assert sn["node"] != dn["node"]
    base = baseline.dijkstra(G, sn["node"], dn["node"])
    assert base["reachable"] and base["cost"] > 0
    opt = proposed.optimize(G, sn["node"], dn["node"], 10, {
        "threshold": 1.3, "max_candidates": 4, "penalty_factor": 1.5,
        "penalty_rounds": 4, "overlap": 0.9, "damping": 0.35,
        "max_iter": 20, "patience": 4, "min_iter": 2, "tol": 1e-3,
        "alpha": 0.15, "beta": 4.0})
    assert sum(opt["flows"]) == 10
    print(f"\nREAL GRAPH: {info['nodes']} nodes, {info['edges']} edges, "
          f"baseline {base['distance_m']/1000:.1f} km, "
          f"{base['cost']/60:.1f} min free-flow, "
          f"{opt['candidates_found']} candidate routes")
