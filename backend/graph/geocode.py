"""Free geocoding via Nominatim (OpenStreetMap) with disk caching + rate limit.

No Google Geocoding API. Usage policy (max ~1 req/s) is respected with a
process-wide throttle. Results are cached under data/cache/geocode/.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from pathlib import Path

import httpx

from .config import (
    GEOCODE_CACHE_DIR,
    NOMINATIM_CACHE_TTL_S,
    NOMINATIM_MIN_INTERVAL_S,
    NOMINATIM_TIMEOUT_S,
    NOMINATIM_UA,
    NOMINATIM_URL,
)

log = logging.getLogger("flowtwin.geocode")

_lock = threading.Lock()
_last_call = [0.0]


def _cache_path(query: str, limit: int) -> Path:
    key = hashlib.sha256(f"{query.strip().lower()}|{limit}".encode()).hexdigest()
    return GEOCODE_CACHE_DIR / f"{key}.json"


def _read_cache(query: str, limit: int):
    p = _cache_path(query, limit)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text())
        if time.time() - payload.get("ts", 0) > NOMINATIM_CACHE_TTL_S:
            return None
        return payload["results"]
    except Exception:  # noqa: BLE001 - corrupt cache is non-fatal
        return None


def _write_cache(query: str, limit: int, results: list) -> None:
    try:
        GEOCODE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(query, limit).write_text(
            json.dumps({"ts": time.time(), "results": results}))
    except Exception:  # noqa: BLE001
        log.warning("could not write geocode cache")


def geocode(query: str, limit: int = 5) -> list[dict]:
    """Return [{name, display_name, lat, lon, source}]. Raises on bad input."""
    query = (query or "").strip()
    if not query:
        raise ValueError("empty location query")
    limit = max(1, min(limit, 10))

    cached = _read_cache(query, limit)
    if cached is not None:
        out = list(cached)
        for r in out:
            r["source"] = r.get("source", "nominatim") + "+cache"
        return out

    with _lock:  # Nominatim usage policy: <= 1 request/second
        wait = NOMINATIM_MIN_INTERVAL_S - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()

    try:
        resp = httpx.get(
            NOMINATIM_URL,
            params={"q": query, "format": "jsonv2", "limit": limit,
                    "addressdetails": 0},
            headers={"User-Agent": NOMINATIM_UA},
            timeout=NOMINATIM_TIMEOUT_S,
        )
        resp.raise_for_status()
        items = resp.json()
    except Exception as exc:
        raise RuntimeError(
            f"Geocoding failed for {query!r}: {exc}. "
            "Check the spelling/network, or run an offline experiment.") from exc

    results = []
    for r in items:
        try:
            results.append({
                "name": r.get("name") or (r.get("display_name") or "").split(",")[0],
                "display_name": r.get("display_name", ""),
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "source": "nominatim",
            })
        except (KeyError, ValueError):
            continue
    if not results:
        raise RuntimeError(
            f"No matches found for {query!r}. Try a more specific name.")
    _write_cache(query, limit, results)
    return results
