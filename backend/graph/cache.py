"""GraphML disk cache for downloaded road networks.

data/graphs/<slug>.graphml — OSMnx MultiDiGraph round-tripped through
ox.save_graphml / ox.load_graphml so repeated experiments on the same
region never re-hit Overpass.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import networkx as nx
import osmnx as ox

from .config import GRAPH_DIR

log = logging.getLogger("flowtwin.cache")


def slugify(*parts: str) -> str:
    raw = "_".join(parts).lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    return raw[:120] or "graph"


def graph_path(slug: str) -> Path:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    return GRAPH_DIR / f"{slug}.graphml"


def has(slug: str) -> bool:
    return graph_path(slug).exists()


def save(G: nx.MultiDiGraph, slug: str) -> Path:
    p = graph_path(slug)
    ox.save_graphml(G, filepath=p)
    log.info("saved graph %s (%d nodes) -> %s", slug, G.number_of_nodes(), p)
    return p


def load(slug: str) -> nx.MultiDiGraph:
    p = graph_path(slug)
    if not p.exists():
        raise FileNotFoundError(f"no cached graph {slug!r} at {p}")
    return ox.load_graphml(filepath=p)
