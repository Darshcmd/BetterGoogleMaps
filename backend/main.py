"""FlowTwin FastAPI app — thin HTTP layer over the graph + algorithm core.

Endpoints:
  GET  /health
  POST /api/geocode     -> Nominatim results (cached)
  POST /api/run         -> synchronous run (small graphs, <30s)
  POST /api/run-async   -> start async job (returns job_id)
  GET  /api/job/{jid}   -> poll job status (queued/running/done/error)
  GET  /api/results/{id} -> fetch a saved experiment result
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .graph.config import (
    BPR_ALPHA, BPR_BETA, CANDIDATE_PENALTY_FACTOR, CANDIDATE_PENALTY_ROUNDS,
    CANDIDATE_TIME_THRESHOLD, MAX_CANDIDATES, MIN_ROUTE_EDGE_OVERLAP,
    PROPOSED_DAMPING, PROPOSED_MAX_ITER, PROPOSED_PATIENCE, PROPOSED_TOL,
    PROPOSED_MIN_ITER, RESULTS_DIR,
)
from .graph.demo import make_demo_graph, demo_source_dest
from .graph.geocode import geocode
from .graph.loader import get_graph
from .graph.snapping import snap_point, path_coords
from .graph.export import export_geojson
from .algorithms.baseline import dijkstra
from .algorithms.proposed import optimize
from .algorithms.evaluation import evaluate, edge_utilization

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("flowtwin.api")

app = FastAPI(title="FlowTwin", version="2.0.0",
              description="Collective traffic routing on real OSM road networks")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

# Thread pool for long-running jobs
_executor = ThreadPoolExecutor(max_workers=4)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


class Loc(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class NamedLoc(BaseModel):
    name: str


class RunRequest(BaseModel):
    origin: Loc | NamedLoc | None = None
    destination: Loc | NamedLoc | None = None
    people: int = Field(10, ge=1, le=100_000)
    use_cache: bool = True
    slug: str | None = None


def _resolve(loc):
    if isinstance(loc, Loc):
        return {"lat": loc.lat, "lon": loc.lon,
                "display_name": f"{loc.lat:.5f}, {loc.lon:.5f}"}
    hits = geocode(loc.name)
    h = hits[0]
    return {"lat": h["lat"], "lon": h["lon"], "display_name": h["display_name"]}


def _cfg():
    return {
        "threshold": CANDIDATE_TIME_THRESHOLD, "max_candidates": MAX_CANDIDATES,
        "penalty_factor": CANDIDATE_PENALTY_FACTOR,
        "penalty_rounds": CANDIDATE_PENALTY_ROUNDS,
        "overlap": MIN_ROUTE_EDGE_OVERLAP, "damping": PROPOSED_DAMPING,
        "max_iter": PROPOSED_MAX_ITER, "patience": PROPOSED_PATIENCE,
        "min_iter": PROPOSED_MIN_ITER, "tol": PROPOSED_TOL,
        "alpha": BPR_ALPHA, "beta": BPR_BETA,
    }


def _update_job(jid: str, **kwargs):
    with _jobs_lock:
        if jid in _jobs:
            _jobs[jid].update(kwargs)


def _execute_job(jid: str, req: RunRequest):
    """Background job: geocode + graph + algorithm + eval."""
    t0 = time.perf_counter()
    try:
        _update_job(jid, status="running", progress=5, message="Geocoding locations...")
        o = _resolve(req.origin)
        d = _resolve(req.destination)
        _update_job(jid, status="running", progress=15, message="Loading road network...")
        G, info = get_graph((o["lat"], o["lon"]), (d["lat"], d["lon"]),
                            slug=req.slug, use_cache=req.use_cache)
        _update_job(jid, status="running", progress=30,
                     message=f"Graph: {info['nodes']} nodes. Computing routes...")
        src = snap_point(G, o["lat"], o["lon"])
        dst = snap_point(G, d["lat"], d["lon"])
        _update_job(jid, status="running", progress=40, message="Finding shortest paths...")
        baseline = dijkstra(G, src["node"], dst["node"])
        _update_job(jid, status="running", progress=55, message="Generating candidate routes...")
        opt = optimize(G, src["node"], dst["node"], req.people, _cfg())
        _update_job(jid, status="running", progress=80, message="Evaluating results...")
        ev = evaluate(G, baseline, opt, req.people, BPR_ALPHA, BPR_BETA)
        paths = {"baseline": baseline["path"]}
        for i, r in enumerate(opt["routes"]):
            paths[f"route_{i + 1}"] = r
        result = {
            "id": jid, "origin": {**o, **src}, "destination": {**d, **dst},
            "graph_info": info, "evaluation": ev,
            "geojson": export_geojson(G, paths, edge_util=edge_utilization(G, opt["routes"], opt["flows"])),
            "route_coords": {k: path_coords(G, v) for k, v in paths.items()},
            "wall_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
        try:
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            (RESULTS_DIR / f"{jid}.json").write_text(json.dumps(result))
        except Exception:
            pass
        _update_job(jid, status="done", progress=100, message="Complete!", result=result)
    except Exception as exc:
        log.error("job %s failed: %s", jid, exc)
        _update_job(jid, status="error", message=str(exc))


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/diagnostics")
def diagnostics():
    import importlib
    out = {}
    for m in ["osmnx", "networkx", "fastapi", "httpx", "shapely"]:
        try:
            out[m] = importlib.import_module(m).__version__  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            out[m] = f"missing: {exc}"
    return out


@app.post("/api/geocode")
def api_geocode(req: NamedLoc):
    try:
        return {"results": geocode(req.name)}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/run")
def api_run(req: RunRequest):
    t0 = time.perf_counter()
    rid = uuid.uuid4().hex[:10]
    try:
        o = _resolve(req.origin)
        d = _resolve(req.destination)
    except Exception as exc:
        raise HTTPException(400, f"geocoding failed: {exc}") from exc
    try:
        G, info = get_graph((o["lat"], o["lon"]), (d["lat"], d["lon"]),
                            slug=req.slug, use_cache=req.use_cache)
    except Exception as exc:
        raise HTTPException(502, f"graph failed: {exc}") from exc
    src = snap_point(G, o["lat"], o["lon"])
    dst = snap_point(G, d["lat"], d["lon"])
    try:
        baseline = dijkstra(G, src["node"], dst["node"])
        opt = optimize(G, src["node"], dst["node"], req.people, _cfg())
        ev = evaluate(G, baseline, opt, req.people, BPR_ALPHA, BPR_BETA)
    except Exception as exc:
        raise HTTPException(500, f"algorithm failed: {exc}") from exc
    paths = {"baseline": baseline["path"]}
    for i, r in enumerate(opt["routes"]):
        paths[f"route_{i + 1}"] = r
    result = {
        "id": rid, "origin": {**o, **src}, "destination": {**d, **dst},
        "graph_info": info, "evaluation": ev,
        "geojson": export_geojson(G, paths, edge_util=edge_utilization(G, opt["routes"], opt["flows"])),
        "route_coords": {k: path_coords(G, v) for k, v in paths.items()},
        "wall_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        (RESULTS_DIR / f"{rid}.json").write_text(json.dumps(result))
    except Exception:  # noqa: BLE001
        pass
    return result


@app.post("/api/demo")
def api_demo(req: RunRequest):
    """Run on the synthetic demo graph (instant, no OSM download)."""
    t0 = time.perf_counter()
    rid = uuid.uuid4().hex[:10]
    G = make_demo_graph()
    src, dst = demo_source_dest()
    try:
        baseline = dijkstra(G, src["node"], dst["node"])
        opt = optimize(G, src["node"], dst["node"], req.people, _cfg())
        ev = evaluate(G, baseline, opt, req.people, BPR_ALPHA, BPR_BETA)
    except Exception as exc:
        raise HTTPException(500, f"algorithm failed: {exc}") from exc
    paths = {"baseline": baseline["path"]}
    for i, r in enumerate(opt["routes"]):
        paths[f"route_{i + 1}"] = r
    result = {
        "id": rid,
        "origin": {**src, "name": src.get("display_name", "Demo Start")},
        "destination": {**dst, "name": dst.get("display_name", "Demo End")},
        "graph_info": {"nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
                       "cached": False, "network_type": "demo"},
        "evaluation": ev,
        "geojson": export_geojson(G, paths, edge_util=edge_utilization(G, opt["routes"], opt["flows"])),
        "route_coords": {k: path_coords(G, v) for k, v in paths.items()},
        "wall_ms": round((time.perf_counter() - t0) * 1000, 2),
        "demo": True,
    }
    return result


@app.post("/api/run-async")
def api_run_async(req: RunRequest):
    """Start an async job. Returns {job_id, status: 'queued'}. Poll /api/job/{jid}."""
    jid = uuid.uuid4().hex[:10]
    with _jobs_lock:
        _jobs[jid] = {"status": "queued", "progress": 0, "message": "Queued...",
                       "result": None, "error": None}
    _executor.submit(_execute_job, jid, req)
    return {"job_id": jid, "status": "queued"}


@app.get("/api/job/{jid}")
def api_job_status(jid: str):
    """Poll job status. Returns {status, progress, message, result?, error?}."""
    with _jobs_lock:
        job = _jobs.get(jid)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.get("/api/precomputed")
def api_precomputed_list():
    """List all precomputed preset results (instant loading)."""
    manifest_path = RESULTS_DIR / "precomputed" / "_manifest.json"
    if not manifest_path.exists():
        return {"precomputed": []}
    try:
        return {"precomputed": json.loads(manifest_path.read_text())}
    except Exception:
        return {"precomputed": []}


@app.get("/api/precomputed/{key}")
def api_precomputed_get(key: str):
    """Get a specific precomputed result by key."""
    # Security: only allow alphanumeric, underscore, hyphen
    if not re.match(r'^[a-zA-Z0-9_\-]+$', key):
        raise HTTPException(400, "invalid key")
    path = RESULTS_DIR / "precomputed" / f"{key}.json"
    if not path.exists():
        raise HTTPException(404, "not found")
    return json.loads(path.read_text())


@app.get("/api/results/{rid}")
def api_results(rid: str):
    p = RESULTS_DIR / f"{rid}.json"
    if not p.exists():
        raise HTTPException(404, "not found")
    return json.loads(p.read_text())
