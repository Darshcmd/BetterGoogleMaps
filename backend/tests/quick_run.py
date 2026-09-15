import sys; sys.path.insert(0, '/Users/darshsoni/VSC/BetterGoogleMaps')
import time, networkx as nx
from backend.graph.loader import get_graph
from backend.graph.snapping import snap_point
from backend.algorithms.baseline import dijkstra
from backend.algorithms.proposed import optimize
from backend.algorithms.evaluation import evaluate

# Use the existing cached VIT->Airport graph (32MB, verified earlier)
G, info = get_graph((12.8429,80.1554),(12.9934,80.1726),slug='vit_chennai_chennai_airport')
print('graph: %dn %de (cached=%s)' % (G.number_of_nodes(), G.number_of_edges(), info['cached']), flush=True)
src = snap_point(G,12.8429,80.1554); dst = snap_point(G,12.9934,80.1726)
print('src node=%d dst node=%d' % (src['node'], dst['node']), flush=True)
base = dijkstra(G,src['node'],dst['node'])
print('baseline: %.1fmin hops=%d reachable=%s' % (base['cost']/60, len(base['path']), base['reachable']), flush=True)
if not base['reachable']:
    # diagnose
    from backend.graph.preprocessing import preprocess
    print('Diagnosing connectivity...', flush=True)
    scc = list(nx.weakly_connected_components(G))
    print('Num SCCs: %d, sizes: %s' % (len(scc), sorted([len(c) for c in scc], reverse=True)[:5]), flush=True)
    sys.exit(0)
cfg = dict(threshold=1.3,max_candidates=6,penalty_factor=1.5,penalty_rounds=4,overlap=0.9,damping=0.35,max_iter=30,patience=6,min_iter=4,tol=1e-4,alpha=0.15,beta=4.0)
for n in [10,100,500,1000]:
    t0=time.time()
    opt=optimize(G,src['node'],dst['node'],n,cfg)
    ev=evaluate(G,base,opt,n,0.15,4.0)
    bct = ev['baseline']['congested_time_min']
    pat = ev['proposed']['avg_time_min']
    imp = ev['improvement_pct']
    ru = ev['proposed']['routes_used']
    print('n=%d: base=%.1f prop=%.1f imp=%.2f%% routes=%d iters=%d t=%.1fs' % (n,bct,pat,imp,ru,opt['iterations'],time.time()-t0), flush=True)
