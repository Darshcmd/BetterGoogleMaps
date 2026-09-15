"""Tests: baseline Dijkstra correctness + proposed optimizer invariants."""
import networkx as nx

from backend.algorithms import baseline, evaluation, proposed
from backend.algorithms.candidates import generate_candidates, yen_k_shortest
from backend.graph.congestion import edge_time_s, time_factor


def test_dijkstra_matches_bruteforce(diamond):
    import itertools
    ours = baseline.dijkstra(diamond, 1, 4)
    best = (None, float("inf"))
    for L in range(2, 5):
        for mids in itertools.permutations([2, 3], L - 2):
            path = [1, *mids, 4]
            if len(set(path)) != len(path):
                continue
            cost, ok = 0.0, True
            for a, b in zip(path, path[1:]):
                data = diamond.get_edge_data(a, b)
                if not data:
                    ok = False
                    break
                cost += min(d["free_time_s"] for d in data.values())
            if ok and cost < best[1]:
                best = (path, cost)
    assert ours["reachable"] and abs(ours["cost"] - best[1]) < 1e-6


def test_source_equals_destination(diamond):
    r = baseline.dijkstra(diamond, 2, 2)
    assert r["reachable"] and r["path"] == [2] and r["cost"] == 0.0


def test_unreachable_reported():
    G = nx.MultiDiGraph()
    G.add_node(1, x=0.0, y=0.0)
    G.add_node(2, x=1.0, y=1.0)
    r = baseline.dijkstra(G, 1, 2)
    assert r["reachable"] is False and r["path"] == []


def test_yen_paths_valid_and_loopless(diamond):
    for path, cost in yen_k_shortest(diamond, 1, 4, 4):
        assert path[0] == 1 and path[-1] == 4
        assert len(set(path)) == len(path) and cost > 0


def test_flow_invariants(diamond, cfg):
    for n in (2, 5, 10, 20, 50, 1000):
        opt = proposed.optimize(diamond, 1, 4, n, cfg)
        assert sum(opt["flows"]) == n
        assert all(f >= 0 for f in opt["flows"])
        for p in opt["routes"]:
            assert p[0] == 1 and p[-1] == 4
        assert opt["total_person_time_min"] >= 0
        ev = evaluation.evaluate(diamond, baseline.dijkstra(diamond, 1, 4),
                                 opt, n, 0.15, 4.0)
        # proposed must never be worse than all-on-shortest
        assert (ev["proposed"]["total_person_time_min"]
                <= ev["baseline"]["total_person_time_min"] + 1e-6)


def test_bpr_monotone_and_guarded():
    assert edge_time_s(100.0, 0.0, 1000.0) == 100.0
    assert edge_time_s(100.0, 2000.0, 1000.0) > edge_time_s(100.0, 500.0, 1000.0)
    assert time_factor(10.0, 0.0) >= 1.0  # capacity<=0 guarded


def test_single_person_single_route(diamond, cfg):
    opt = proposed.optimize(diamond, 1, 4, 1, cfg)
    assert sum(opt["flows"]) == 1
