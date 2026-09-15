#!/usr/bin/env python3
"""Regenerate manifest from all precomputed JSON files."""
import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "results" / "precomputed"
files = sorted(p.stem for p in OUT_DIR.glob("*.json") if p.stem != "_manifest")

new_manifest = []
for f in files:
    data = json.loads((OUT_DIR / f"{f}.json").read_text())
    ev = data["evaluation"]
    key = f.replace(".json", "")
    src_dst = key.split("__")
    src = src_dst[0].replace("_", " ")
    dst = src_dst[1].replace("_", " ")
    src = src.replace("T_Nagar", "T. Nagar")
    dst = dst.replace("T_Nagar", "T. Nagar")
    new_manifest.append({
        "key": key,
        "src": src,
        "dst": dst,
        "people": ev["people"],
        "file": f"{key}.json",
        "improvement_pct": ev["improvement_pct"],
        "routes_used": ev["proposed"]["routes_used"],
        "nodes": ev["nodes"],
        "base_min": ev["baseline"]["congested_time_min"],
        "avg_min": ev["proposed"]["avg_time_min"],
    })

(OUT_DIR / "_manifest.json").write_text(json.dumps(new_manifest, indent=1))
print(f"Regenerated manifest with {len(new_manifest)} entries")
for e in sorted(new_manifest, key=lambda x: -x["improvement_pct"]):
    print(f'  {e["src"]} -> {e["dst"]}: {e["improvement_pct"]}% ({e["routes_used"]} routes)')
