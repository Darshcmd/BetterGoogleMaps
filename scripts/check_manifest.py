#!/usr/bin/env python3
"""Check which precomputed files are missing from the manifest."""
import json
from pathlib import Path

cd = Path("/Users/darshsoni/VSC/BetterGoogleMaps")
OUT_DIR = cd / "results" / "precomputed"
files = sorted(p.stem for p in OUT_DIR.glob("*.json") if p.stem != "_manifest")
print("Files:", len(files))
manifest = json.loads((OUT_DIR / "_manifest.json").read_text())
print("Manifest entries:", len(manifest))
for f in files:
    if f not in {e["key"] for e in manifest}:
        print("  Missing:", f)
