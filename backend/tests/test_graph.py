"""Tests: graph acquisition/validity helpers, snapping, edge cases."""
import networkx as nx

from backend.graph import preprocessing, snapping
from backend.graph.config import MAX_PEOPLE, MIN_PEOPLE


def _road_graph():
    G = nx.MultiDiGraph()
    G.add_node(1, x=80.10, y=12.99, street_count=2)
    G.add_node(2, x=80.11, y=12.99, street_count=2)
    G.add_node(3, x=80.11, y=13.00, street_count=2)
    G.add_edge(1, 2, length=500.0, highway="primary", maxspeed="50",
               lanes="2", oneway=False, name="Test Rd")
    G.add_edge(2, 1, length=500.0, highway="primary", oneway=False)
    G.add_edge(2, 3, length=0.2, highway="residential")  # artifact
    G.add_edge(2, 3, length=800.0, highway="residential", oneway=True)
    return G


def test_preprocess_weights_and_lcc():
    G = preprocessing.preprocess(_road_graph())
    assert G.number_of_nodes() >= 2
    for _, _, d in G.edges(data=True):
        assert d["length_m"] >= 1.0
        assert d["free_time_s"] > 0
        assert d["capacity_vph"] >= 100.0
        assert d["capacity_estimated"] is True


def test_preprocess_speed_table():
    G = preprocessing.preprocess(_road_graph())
    tagged = [d for _, _, d in G.edges(data=True)
              if d.get("maxspeed") == "50"]
    assert tagged and all(p["speed_kmh"] == 50.0 for p in tagged)


def test_snap_returns_nearest_node():
    G = preprocessing.preprocess(_road_graph())
    s = snapping.snap_point(G, 12.9901, 80.1001)
    assert s["node"] == 1 and s["snap_distance_m"] >= 0


def test_people_bounds_sane():
    assert MIN_PEOPLE == 1 and MAX_PEOPLE == 100_000


def test_disconnected_keeps_largest_component():
    G = nx.MultiDiGraph()
    for i in (1, 2, 3):
        G.add_node(i, x=80.0 + i * 0.01, y=13.0)
    G.add_edge(1, 2, length=100.0, highway="residential")
    G.add_edge(2, 1, length=100.0, highway="residential")
    G.add_node(99, x=81.0, y=14.0)
    G2 = preprocessing.preprocess(G)
    assert 99 not in G2.nodes and G2.number_of_nodes() == 2
