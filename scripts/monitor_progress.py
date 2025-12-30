#!/usr/bin/env python3
"""Monitor progress of all active tasks."""
import json
import time
from pathlib import Path

print("=" * 70)
print("ACTIVE TASKS MONITOR")
print("=" * 70)
print()

# Check test set expansion
print("📊 TEST SET EXPANSION:")
for game in ["magic", "pokemon", "yugioh"]:
    path = Path(f"experiments/test_set_expanded_{game}.json")
    if path.exists():
        mtime = path.stat().st_mtime
        age_min = (time.time() - mtime) / 60
        
        with open(path) as f:
            data = json.load(f)
        queries = data.get("queries", data) if isinstance(data, dict) else data
        size = len(queries) if isinstance(queries, dict) else len(queries)
        
        status = "🔄" if age_min < 10 else "✅"
        print(f"  {status} {game}: {size} queries ({age_min:.1f} min ago)")
    else:
        print(f"  ⏳ {game}: Not started")

print()

# Check training
print("📊 EMBEDDING TRAINING:")
for name, file in [
    ("triplet", "data/embeddings/trained_triplet_substitution.wv"),
    ("heterogeneous", "data/embeddings/trained_heterogeneous_substitution.wv"),
]:
    path = Path(file)
    if path.exists():
        mtime = path.stat().st_mtime
        age_min = (time.time() - mtime) / 60
        size_mb = path.stat().st_size / (1024 * 1024)
        status = "🔄" if age_min < 10 else "✅"
        print(f"  {status} {name}: {size_mb:.1f} MB ({age_min:.1f} min ago)")
    else:
        print(f"  ⏳ {name}: Training...")

print()
print("✅ All tasks monitored")
