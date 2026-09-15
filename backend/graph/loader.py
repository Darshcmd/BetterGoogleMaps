"""Graph loader: cache-first get_graph() + GeoJSON export for Leaflet."""

from __future__ import annotations

import logging

import networkx as nx

from . import cache
from .config import MAX_GRAPH_NODES, NETWORK_TYPE
from .osm import download_graph, region_for
from .preprocessing import preprocess

log = logging.getLogger("flowtwin.loader")


def _trim_to_lcc(G, source, dest):
    """Keep the graph manageable: bbox pass, then corridor bands of growing
    width; pick the widest band whose largest connected component fits
    MAX_GRAPH_NODES. Prefers the component containing both OD endpoints.
    """
    if G.number_of_nodes() <= MAX_GRAPH_NODES:
        return G
    log.info("graph too large (%d nodes), trimming to corridor", G.number_of_nodes())
    import math

    src_lat, src_lon = source
    dst_lat, dst_lon = dest
    min_lat, max_lat = min(src_lat, dst_lat), max(src_lat, dst_lat)
    min_lon, max_lon = min(src_lon, dst_lon), max(src_lon, dst_lon)

    def bbox_filter(plat, plon):
        keep = set()
        for node, d in G.nodes(data=True):
            lat, lon = d.get("y"), d.get("x")
            if lat is None or lon is None:
                continue
            if (min_lat - plat) <= lat <= (max_lat + plat) and \
               (min_lon - plon) <= lon <= (max_lon + plon):
                keep.add(node)
        return keep

    keep = bbox_filter(0.30 * (max_lat - min_lat) + 0.005,
                       0.30 * (max_lon - min_lon) + 0.005)
    if len(keep) < 10:
        keep = bbox_filter(0.010, 0.010)

    if len(keep) > MAX_GRAPH_NODES:
        # Corridor band: perpendicular distance to the straight OD line.
        kx = 111320.0 * math.cos(math.radians((src_lat + dst_lat) / 2))
        ax, ay = src_lon * kx, src_lat * 111320.0
        bx, by = dst_lon * kx, dst_lat * 111320.0
        abx, aby = bx - ax, by - ay
        ab_len = math.hypot(abx, aby) or 1.0
        od_len_m = ab_len

        def band_filter(width_m):
            out = set()
            for node, d in G.nodes(data=True):
                lat, lon = d.get("y"), d.get("x")
                if lat is None or lon is None:
                    continue
                px, py = lon * kx, lat * 111320.0
                t = ((px - ax) * abx + (py - ay) * aby) / (ab_len * ab_len)
                t = max(0.0, min(1.0, t))
                dist = math.hypot(px - (ax + t * abx), py - (ay + t * aby))
                if dist <= width_m:
                    out.add(node)
            return out

        def node_near(coord, nodes):
            lat0, lon0 = coord
            best_n, best_d = None, float("inf")
            for n in nodes:
                d = G.nodes[n]
                dd = (d.get("y", 0) - lat0) ** 2 + (d.get("x", 0) - lon0) ** 2
                if dd < best_d:
                    best_d, best_n = dd, n
            return best_n

        best = None
        for frac, extra in ((0.05, 500.0), (0.10, 1000.0), (0.15, 1500.0),
                            (0.25, 2500.0), (0.40, 4000.0), (0.60, 6000.0),
                            (1.00, 10000.0), (2.00, 15000.0)):
            band = band_filter(frac * od_len_m + extra)
            if len(band) < 50:
                continue
            und = G.subgraph(band).to_undirected()
            comps = sorted(nx.connected_components(und), key=len, reverse=True)
            near_s = node_near((src_lat, src_lon), band)
            near_d = node_near((dst_lat, dst_lon), band)
            pick = None
            for comp in comps:
                if near_s in comp and near_d in comp:
                    pick = set(comp)
                    break
            if pick is None:
                pick = set(comps[0]) if comps else band
            if len(pick) <= MAX_GRAPH_NODES:
                best = pick        # widest band so far that fits
            else:
                if best is None:
                    best = pick    # too big but better than nothing
                break              # wider only grows it further
        if best is not None:
            keep = best

    G.remove_nodes_from(set(G.nodes()) - keep)
    log.info("trimmed to %d nodes", G.number_of_nodes())
    return G


def get_graph(source, dest, slug=None, use_cache=True):
    """Download (or load cached) + preprocess the OD region graph.

    Returns (G, info); info has slug, cached flag, bbox, node/edge counts.
    """
    # Accept both dicts {"lat":, "lon":} and tuples (lat, lon)
    if isinstance(source, dict):
        source = (source["lat"], source["lon"])
    if isinstance(dest, dict):
        dest = (dest["lat"], dest["lon"])
    bbox = region_for(source, dest)
    slug = slug or cache.slugify(f"{source[0]:.4f}_{source[1]:.4f}",
                                 f"{dest[0]:.4f}_{dest[1]:.4f}")
    if use_cache and cache.has(slug):
        log.info("loading cached graph %s", slug)
        G = cache.load(slug)
        # GraphML stores everything as strings; re-normalize if needed.
        sample = next(iter(G.edges(data=True)), None)
        needs_reprocess = sample is None or not isinstance(
            sample[2].get("free_time_s"), (int, float))
        if needs_reprocess:
            log.info("cached graph needs re-normalizing (string values)")
            G = preprocess(G)
        info = {"slug": slug, "cached": True, "bbox": bbox}
    else:
        raw = download_graph(bbox)
        G = preprocess(raw)
        cache.save(G, slug)
        info = {"slug": slug, "cached": False, "bbox": bbox,
                "overpass": raw.graph.get("flowtwin_overpass")}
    # Trim if too large
    G = _trim_to_lcc(G, source, dest)
    info.update({"nodes": G.number_of_nodes(),
                 "edges": G.number_of_edges(), "network_type": NETWORK_TYPE})
    return G, info
