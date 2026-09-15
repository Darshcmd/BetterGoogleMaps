"""GeoJSON export for the Leaflet map: context roads + named route overlays."""

from __future__ import annotations


def _best(G, u, v):
    data = G.get_edge_data(u, v)
    if not data:
        return None
    return min(data.values(), key=lambda d: float(d.get("free_time_s", 1e18)))


def export_geojson(G, paths=None, max_context_edges=1500, max_nodes=400,
                   edge_util=None) -> dict:
    feats: list[dict] = []
    prio = {"motorway": 0, "trunk": 1, "primary": 2, "secondary": 3,
            "tertiary": 4, "unclassified": 5, "residential": 6}
    edges = sorted(G.edges(keys=True, data=True),
                   key=lambda e: (prio.get(str(e[3].get("highway", "")), 9),
                                  -float(e[3].get("length_m", 0))))
    edge_util = edge_util or {}
    for u, v, _k, d in edges[:max_context_edges]:
        geom = d.get("geometry")
        if geom is not None:
            coords = [[x, y] for x, y in geom.coords]
        else:
            coords = [[G.nodes[u]["x"], G.nodes[u]["y"]],
                      [G.nodes[v]["x"], G.nodes[v]["y"]]]
        util = edge_util.get((u, v), edge_util.get((v, u), 0.0))
        feats.append({"type": "Feature",
                      "geometry": {"type": "LineString", "coordinates": coords},
                      "properties": {"kind": "context",
                                     "highway": str(d.get("highway", "")),
                                     "name": str(d.get("name", "")),
                                     "util": util}})
    # Sampled node markers so the map shows the actual network junctions.
    nodes = list(G.nodes(data=True))
    if len(nodes) > max_nodes:
        step = len(nodes) / max_nodes
        nodes = [nodes[int(i * step)] for i in range(max_nodes)]
    for n, d in nodes:
        if "x" in d and "y" in d:
            feats.append({"type": "Feature",
                          "geometry": {"type": "Point", "coordinates": [d["x"], d["y"]]},
                          "properties": {"kind": "node", "id": str(n)}})
    for name, nodes_p in (paths or {}).items():
        coords: list = []
        for a, b in zip(nodes_p, nodes_p[1:]):
            best = _best(G, a, b)
            if best is None:
                continue
            g = best.get("geometry")
            seg = ([[x, y] for x, y in g.coords] if g is not None else [
                [G.nodes[a]["x"], G.nodes[a]["y"]],
                [G.nodes[b]["x"], G.nodes[b]["y"]]])
            coords.extend(seg if not coords else seg[1:])
        if coords:
            feats.append({"type": "Feature",
                          "geometry": {"type": "LineString",
                                       "coordinates": coords},
                          "properties": {"kind": "route", "name": name}})
    return {"type": "FeatureCollection", "features": feats}
