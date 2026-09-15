"""Real-world road graph acquisition with OSMnx (part 1: region + download).

Canonical graph object: NetworkX MultiDiGraph, network_type="drive".
Part 2 (preprocess + get_graph + export) is appended below.
"""

from __future__ import annotations

import logging
import math

import networkx as nx
import osmnx as ox

from . import cache
from .config import (
    BBOX_MARGIN_FRACTION,
    BBOX_MARGIN_MAX_DEG,
    BBOX_MARGIN_MIN_DEG,
    NETWORK_TYPE,
    OVERPASS_MEMORY_MB,
    OVERPASS_REQUESTS_TIMEOUT_S,
    OVERPASS_URLS,
)

log = logging.getLogger("flowtwin.osm")


def region_for(source, dest):
    """OSMnx bbox (left, bottom, right, top) covering source+dest + margin."""
    (s_lat, s_lon), (d_lat, d_lon) = source, dest
    dist_deg = math.hypot(s_lat - d_lat, s_lon - d_lon)
    pad = dist_deg * BBOX_MARGIN_FRACTION
    pad = min(max(pad, BBOX_MARGIN_MIN_DEG), BBOX_MARGIN_MAX_DEG)
    return (min(s_lon, d_lon) - pad, min(s_lat, d_lat) - pad,
            max(s_lon, d_lon) + pad, max(s_lat, d_lat) + pad)


def _configure_osmnx(overpass_url: str) -> None:
    ox.settings.overpass_url = overpass_url
    ox.settings.requests_timeout = OVERPASS_REQUESTS_TIMEOUT_S
    ox.settings.overpass_memory = OVERPASS_MEMORY_MB * 1024 * 1024
    ox.settings.log_console = False
    ox.settings.use_cache = False


def download_graph(bbox) -> nx.MultiDiGraph:
    """Fetch the drive network in bbox via OSMnx, trying mirrors in order."""
    last_err: Exception | None = None
    for url in OVERPASS_URLS:
        try:
            _configure_osmnx(url)
            log.info("requesting OSM drive network via %s", url)
            G = ox.graph_from_bbox(
                bbox, network_type=NETWORK_TYPE, simplify=True,
                retain_all=False, truncate_by_edge=True)
            log.info("downloaded: %d nodes, %d edges",
                     G.number_of_nodes(), G.number_of_edges())
            G.graph["flowtwin_overpass"] = url
            return G
        except Exception as exc:  # noqa: BLE001 - try next mirror
            last_err = exc
            log.warning("Overpass mirror failed (%s): %s", url, exc)
    raise RuntimeError(
        "Unable to retrieve the road network from any Overpass endpoint "
        f"({last_err}). Try again later, or run an offline experiment on a "
        "cached graph in data/graphs/.") from last_err
