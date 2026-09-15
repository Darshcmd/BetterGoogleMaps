"""Download Chennai OSM graph with progress output."""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import osmnx as ox
import networkx as nx

# Chennai area covering all preset locations
# Smaller bbox: 12.84-13.09 lat, 80.15-80.28 lon
north, south = 13.09, 12.84
east, west = 80.28, 80.15

print(f"Downloading OSM drive network for Chennai ({south:.2f}-{north:.2f}N, {west:.2f}-{east:.2f}E)...")
print("This downloads from OpenStreetMap. First time takes ~30-90s depending on area size.")

t0 = time.time()

# Configure osmnx
ox.settings.overpass_url = "https://overpass-api.de/api/interpreter"
ox.settings.requests_timeout = 240
ox.settings.log_console = True
ox.settings.use_cache = False

# bbox: (left, bottom, right, top) = (west, south, east, north)
bbox = (west, south, east, north)

try:
    G = ox.graph_from_bbox(
        bbox=bbox, network_type="drive", simplify=True, retain_all=False, truncate_by_edge=True
    )
    print(f"\nDownloaded in {time.time()-t0:.1f}s: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
except Exception as e:
    print(f"\nDownload failed: {e}")
    sys.exit(1)

# Preprocess
print("Preprocessing graph (estimating capacities, computing free-flow times)...")
from backend.graph import preprocessing, cache
G = preprocessing.preprocess(G)

# Save to cache
slug = "chennai_metro"
cache.save(G, slug)
print(f"Cached as '{slug}'")

# Verify
G2 = cache.load(slug)
print(f"Verified: loaded {G2.number_of_nodes()} nodes, {G2.number_of_edges()} edges from cache")

print(f"\nTotal time: {time.time()-t0:.1f}s")