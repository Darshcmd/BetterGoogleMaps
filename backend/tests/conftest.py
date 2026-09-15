"""Shared pytest fixtures: tiny directed road graphs (no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import networkx as nx
import pytest



def _add(G, u, v, L, s, cap=1800.0):
    G.add_edge(u, v, length=L, length_m=L, free_time_s=L / (s / 3.6),
               speed_kmh=s, speed_estimated=False, lanes=1,
               capacity_vph=cap, capacity_estimated=True,
               highway="residential", name="")
    if "x" not in G.nodes[u]:
        G.add_node(u, x=80.0, y=13.0)


@pytest.fixture()
def diamond():
    G = nx.MultiDiGraph()
    for u, v, L, s in [(1, 2, 1000, 50), (2, 4, 1000, 50), (1, 3, 1200, 50),
                       (3, 4, 1200, 50), (2, 3, 200, 30)]:
        _add(G, u, v, L, s)
    for n in list(G.nodes):
        G.nodes[n].update(x=80.0 + n * 0.001, y=13.0 + n * 0.001)
    return G


@pytest.fixture()
def cfg():
    return {"threshold": 1.3, "max_candidates": 4, "penalty_factor": 1.5,
            "penalty_rounds": 4, "overlap": 0.9, "damping": 0.35,
            "max_iter": 40, "patience": 6, "min_iter": 4, "tol": 1e-4,
            "alpha": 0.15, "beta": 4.0}
