# BetterGoogleMaps — Collective Traffic Routing

**BetterGoogleMaps** (running on the **FlowTwin** engine) is a geographic,
interactive implementation and *extension* of the
[collective-routing concept](https://devpost.com/software/gigglemaps-ebnzh0)
and the traffic-assignment literature (MSA — cf.
[maslab-ufrgs/MSA](https://github.com/maslab-ufrgs/MSA), Frank-Wolfe variants —
cf. [cppRouting](https://github.com/vlarmet/cppRouting)).

Normal navigation: *What is the fastest route for one traveller?*

BetterGoogleMaps: **What allocation minimizes network-wide travel time?**

Given origin, destination, and number of travellers:

1. **geocodes** locations (Nominatim - free, no API key)
2. **obtains the real road network** from OpenStreetMap via OSMnx
3. **converts to a directed graph** with real lengths, estimated speeds/capacities
4. **snaps** origin/destination to nearest graph nodes
5. finds the **baseline** shortest route (Dijkstra, own implementation)
6. **generates candidate routes** (Yen k-shortest + penalty corridors)
7. **simulates congestion** with nonlinear BPR flow model
8. **distributes travellers** with damped MSA-style flow assignment
9. **compares** collective vs baseline with execution-derived metrics

> Data integrity: numbers from actual execution. Capacities/speeds estimated. Demand simulated.

---

## Architecture

```
OpenStreetMap -> OSMnx -> NetworkX MultiDiGraph -> Snap OD -> Baseline + Proposed -> Evaluation
```

## Algorithm layer

Decoupled from HTTP/UI: baseline.py, candidates.py, proposed.py, evaluation.py

## Installation

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
```

## Running

```bash
# backend:  cd backend && .venv/bin/python -m uvicorn main:app --port 8000
# frontend: open frontend/index.html
# experiments: cd backend && .venv/bin/python experiments/run_experiment.py
```

Endpoints: /health, /api/geocode, /api/demo, /api/run-async, /api/job/{id}, /api/results/{id}

## Enhancements

- **Bidirectional Dijkstra** (own, alternating frontiers, meeting-point check) —
  ~2x fewer explored nodes (OSRM/cppRouting-style).
- **Google-Maps-style traffic heat layer** — every road is colored by
  flow/capacity (blue=free … red=over capacity) from the actual assignment.
- **Animated travellers** — "Play simulation" animates dots along each
  collective route, scaled to the number of people assigned.
- **Click a route card** to highlight that corridor and dim the others.

## Complexity

| Component | Time | Space |
|-----------|------|-------|
| Bidirectional Dijkstra | O(E log V) | O(V) |
| Yen k-shortest | O(k·S·(E log V)), S=spur cap | O(k·V) |
| Optimizer/iter | O(k·(E log V)) | O(E) |

## Testing

```bash
cd backend && .venv/bin/python -m pytest tests/ -v
```

## Limitations

- Capacities/speeds estimated (flagged *_estimated)
- Demand is simulated, not live traffic
- Alternatives within 2.0x free-flow threshold
- BPR params are literature defaults

## Attribution

Map: OSM (ODbL). Geocoding: Nominatim. Built with FastAPI, OSMnx, NetworkX, Leaflet.

Independent implementation inspired by GiggleMaps.
# BetterGoogleMaps
# BetterGoogleMaps
