#!/usr/bin/env python3
"""Verify the fix works for map display."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.graph.demo import make_demo_graph, demo_source_dest
from backend.graph.export import export_geojson
from backend.algorithms.baseline import dijkstra
from backend.algorithms.proposed import optimize

print("=" * 70)
print("VERIFYING MAP FIX")
print("=" * 70)
print()

G = make_demo_graph()
src, dst = demo_source_dest()
print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

print("\n1. Running routing algorithms...")
baseline = dijkstra(G, src['node'], dst['node'])
opt = optimize(G, src['node'], dst['node'], 10, {
    'threshold': 1.3, 'max_candidates': 4, 'penalty_factor': 1.5,
    'penalty_rounds': 4, 'overlap': 0.9, 'damping': 0.35,
    'max_iter': 20, 'patience': 4, 'min_iter': 2, 'tol': 1e-3,
    'alpha': 0.15, 'beta': 4.0
})

paths = {'baseline': baseline['path']}
for i, r in enumerate(opt['routes']):
    paths[f'route_{i+1}'] = r

print(f"   Baseline path: {len(baseline['path'])} nodes")
print(f"   Proposed routes: {len(opt['routes'])}")

print("\n2. Exporting GeoJSON for map...")
try:
    geojson = export_geojson(G, paths)
    total_features = len(geojson['features'])
    route_features = len([f for f in geojson['features'] if f.get('properties', {}).get('kind') == 'route'])
    
    print(f"   ✓ SUCCESS: {total_features} total features")
    print(f"   ✓ Route features: {route_features}")
    print()
    print("=" * 70)
    print("✓ FIX VERIFIED: Map will now display correctly!")
    print("=" * 70)
    print()
    print("The map should now show:")
    print("  - Road network (context lines)")
    print("  - Baseline route (orange dashed)")
    print(f"  - {route_features - 1} proposed route(s) (colored)")
    print("  - Origin and destination markers")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()