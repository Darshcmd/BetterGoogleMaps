# Changelog

All notable changes to BetterGoogleMaps are documented here.

## [2.1.0] — Documentation & configuration

- Rewrote `README.md` in research-paper style: abstract, problem formulation,
  system architecture and optimizer flowcharts (Mermaid), methodology tables,
  experimental results from the executed Chennai presets, run guide, API
  reference, limitations and references.
- Added `.env.example` documenting all `FLOWTWIN_*` environment variables.
- Added a dependency-free `.env` loader in `backend/graph/config.py` so a
  repo-root `.env` is picked up automatically (real environment wins).
- Recreated `CHANGELOG.md`.

## [2.0.0] — FlowTwin rebuild

- OSMnx + NetworkX architecture: real OSM downloads, GraphML region cache.
- Own implementations: bidirectional Dijkstra, Yen k-shortest candidates,
  damped MSA collective flow optimizer with dynamic candidate discovery.
- BPR congestion model shared by optimizer and evaluation.
- Execution-derived evaluation: person-time, utilization, bottlenecks.
- FastAPI service layer with sync + async jobs; precomputed presets.
- Leaflet frontend with traffic heat layer, route cards, animated travellers.

## Fixes

- Fixed `'str' object has no attribute 'coords'`: preprocessing no longer
  stringifies Shapely LineString geometry, which broke `path_coords()` and
  `export_geojson()` (blank map after running the algorithm).
