"""FlowTwin rebuild — configuration (OSMnx + NetworkX architecture).

All tuning knobs live here. Everything is free/open: OpenStreetMap via OSMnx,
Nominatim geocoding, Leaflet visualization. No API keys anywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"


def _load_dotenv() -> None:
    """Minimal .env loader (dependency-free).

    Reads PROJECT_ROOT/.env and sets any not-yet-set variables so the
    FLOWTWIN_* knobs below can be configured without shell exports.
    Existing environment variables always win.
    """
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    except OSError:
        pass


_load_dotenv()


DATA_DIR = Path(os.environ.get("FLOWTWIN_DATA_DIR", PROJECT_ROOT / "data"))
GRAPH_DIR = DATA_DIR / "graphs"
GEOCODE_CACHE_DIR = DATA_DIR / "cache" / "geocode"
RESULTS_DIR = PROJECT_ROOT / "results"

# --- OSMnx / Overpass -------------------------------------------------------
# OSMnx talks to an Overpass-compatible instance. The canonical endpoint has
# TLS issues from some networks, so we probe a list of free mirrors in order.
# Override with FLOWTWIN_OVERPASS_URL if desired.
OVERPASS_URLS = [
    u.strip()
    for u in os.environ.get(
        "FLOWTWIN_OVERPASS_URL",
        "https://overpass-api.de/api/interpreter,"
        "https://overpass.kumi.systems/api/interpreter,"
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter,"
        "https://overpass.osm.jp/api/interpreter",
    ).split(",")
    if u.strip()
]
OVERPASS_REQUESTS_TIMEOUT_S = int(os.environ.get("FLOWTWIN_OSMNX_TIMEOUT", "240"))
OVERPASS_MEMORY_MB = int(os.environ.get("FLOWTWIN_OSMNX_MEMORY", "3000"))
NETWORK_TYPE = "drive"  # realistic driving movement

# --- Graph region strategy --------------------------------------------------
# Region = bbox of (source, destination), padded by a fraction of the OD
# distance, clamped to a min/max so we never download an entire city.
# Smaller margin = faster algorithm (Yen k-shortest is O(k*n*log(n))).
BBOX_MARGIN_FRACTION = 0.005
BBOX_MARGIN_MIN_DEG = 0.001
BBOX_MARGIN_MAX_DEG = 0.008
MAX_GRAPH_NODES = 8000  # hard cap — if bbox yields more, trim to LCC

# --- Preprocessing ----------------------------------------------------------
MIN_EDGE_LENGTH_M = 1.0   # shorter edges are artifacts -> drop
DEFAULT_SPEED_KMH = 45.0
SPEED_BY_HIGHWAY = {
    "motorway": 90.0, "trunk": 70.0, "primary": 55.0, "secondary": 45.0,
    "tertiary": 35.0, "residential": 25.0, "service": 15.0,
    "living_street": 15.0, "unclassified": 30.0,
}
# Vehicle-per-hour capacity per lane by highway class (ESTIMATED, labelled so).
LANE_CAPACITY_VPH = {
    "motorway": 2200.0, "trunk": 1900.0, "primary": 1700.0,
    "secondary": 1500.0, "tertiary": 1200.0, "residential": 900.0,
    "service": 600.0, "living_street": 500.0, "unclassified": 900.0,
}
DEFAULT_LANES = {
    "motorway": 2, "trunk": 2, "primary": 2, "secondary": 1,
    "tertiary": 1, "residential": 1, "service": 1,
    "living_street": 1, "unclassified": 1,
}
MIN_CAPACITY_VPH = 100.0  # defensive floor so v/c can never divide by zero

# --- Geocoding (Nominatim, free) --------------------------------------------
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_UA = "FlowTwin/2.0 (DAA collective-routing research demo)"
NOMINATIM_TIMEOUT_S = 20.0
NOMINATIM_MIN_INTERVAL_S = 1.1  # usage-policy rate limit
NOMINATIM_CACHE_TTL_S = 7 * 24 * 3600

# --- Algorithms --------------------------------------------------------------
BPR_ALPHA = float(os.environ.get("FLOWTWIN_BPR_ALPHA", "0.15"))
BPR_BETA = float(os.environ.get("FLOWTWIN_BPR_BETA", "4.0"))
BPR_MAX_TIME_FACTOR = 3.0
CANDIDATE_TIME_THRESHOLD = 2.00  # free-flow time <= (1+2)x shortest
MAX_CANDIDATES = 8
CANDIDATE_PENALTY_FACTOR = 1.5
CANDIDATE_PENALTY_ROUNDS = 3
MIN_ROUTE_EDGE_OVERLAP = 0.65
PROPOSED_DAMPING = 0.4  # legacy knob, unused by the projected-gradient solver
PROPOSED_MAX_ITER = 60
PROPOSED_PATIENCE = 5
PROPOSED_MIN_ITER = 3
PROPOSED_TOL = 1e-4

# --- Multi-person demand ------------------------------------------------------
MIN_PEOPLE = 1
MAX_PEOPLE = 100_000
