#!/usr/bin/env python3
"""
Merge multiple test sets into a single canonical file.

Each input is either:
- canonical JSON: { "queries": { card: {graded lists...} } }
- raw JSON:       { card: {graded lists...} }

Merging strategy:
- For overlapping queries, take union of lists per relevance bucket (dedup, preserve order by first occurrence)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


BUCKETS = [
    "highly_relevant",
    "relevant",
    "somewhat_relevant",
    "marginally_relevant",
    "irrelevant",
]


def _as_queries(d: dict) -> dict:
    return d.get("queries", d)


def _merge_lists(a: List[str], b: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for lst in (a, b):
        for x in lst:
            if x not in seen:
                seen.add(x)
                out.append(x)
    return out


def merge_test_sets(inputs: List[Path]) -> dict:
    merged: Dict[str, Dict[str, List[str]]] = {}

    for p in inputs:
        with open(p) as f:
            data = json.load(f)
        qmap = _as_queries(data)

        for query, buckets in qmap.items():
            if query not in merged:
                merged[query] = {k: [] for k in BUCKETS}
            for b in BUCKETS:
                merged[query][b] = _merge_lists(merged[query][b], buckets.get(b, []))

    return {"version": "merged", "queries": merged}


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge test sets into one canonical file")
    parser.add_argument("--inputs", nargs="+", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args()

    inputs = [Path(p) for p in args.inputs]
    result = merge_test_sets(inputs)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"✓ Merged {len(inputs)} test sets → {out_path}")
    print(f"   Queries: {len(result['queries'])}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())





