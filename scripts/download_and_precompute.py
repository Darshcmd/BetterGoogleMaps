"""Download Chennai OSM graph and precompute all preset results."""
import sys
import time
from pathlib import Path

# Add project root to path so 'backend' is importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.graph import cache, preprocessing
from backend.graph.loader import get_graph

# Use endpoints that cover all Chennai preset locations
# VIT Chennai (12.8429, 80.1554) -> Chennai Central (13.0824, 80.2760)
# This corridor covers: Airport, Guindy, Tidel Park, T. Nagar
origin = (12.8429, 80.1554)
dest = (13.0824, 80.2760)

slug = "chennai_metro"
t0 = time.time()

if cache.has(slug):
    print(f"Graph '{slug}' already cached, loading...")
    G = cache.load(slug)
    sample = next(iter(G.edges(data=True)), None)
    if sample and not isinstance(sample[2].get("free_time_s"), (int, float)):
        G = preprocessing.preprocess(G)
    print(f"Loaded: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
else:
    print("Downloading Chennai road network from OSM (first time only, ~30-60s)...")
    G, info = get_graph(origin, dest, slug=slug, use_cache=False)
    print(f"Downloaded: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges in {time.time()-t0:.1f}s")

# Now run precompute for all preset pairs
print("\n" + "="*60)
print("Precomputing all Chennai preset O/D pairs...")
print("="*60)
from backend.scripts.precompute import main as precompute_main
precompute_main()

print(f"\nDone! Total session time: {time.time()-t0:.1f}s")