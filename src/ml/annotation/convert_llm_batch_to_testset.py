#!/usr/bin/env python3
"""
Convert LLM-bootstrapped YAML (batch_002_expansion.yaml) into a test set JSON.

Uses llm_relevance_draft (0-4) to populate graded buckets.

Output format:
{
  "queries": {
    "Card Name": {
      "highly_relevant": [...],
      "relevant": [...],
      "somewhat_relevant": [...],
      "marginally_relevant": [...],
      "irrelevant": [...]
    }
  }
}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def convert(input_path: Path) -> dict:
    import yaml

    with open(input_path) as f:
        data = yaml.safe_load(f)

    annotations = data.get("annotations", [])
    queries: dict[str, dict[str, list[str]]] = {}

    for entry in annotations:
        query = entry.get("query_card") or entry.get("query")
        if not query:
            continue
        buckets = {
            "highly_relevant": [],
            "relevant": [],
            "somewhat_relevant": [],
            "marginally_relevant": [],
            "irrelevant": [],
        }
        for cand in entry.get("candidates", []):
            name = cand.get("card")
            if not name:
                continue
            draft = cand.get("llm_relevance_draft")
            # If human relevance present, prefer it
            rel = cand.get("relevance", draft)
            try:
                rel = int(rel) if rel is not None else None
            except Exception:
                rel = None
            if rel is None:
                continue
            if rel == 4:
                buckets["highly_relevant"].append(name)
            elif rel == 3:
                buckets["relevant"].append(name)
            elif rel == 2:
                buckets["somewhat_relevant"].append(name)
            elif rel == 1:
                buckets["marginally_relevant"].append(name)
            elif rel == 0:
                buckets["irrelevant"].append(name)
        queries[query] = buckets

    return {"version": "llm_batch_002_draft", "queries": queries}


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert LLM batch YAML to test set JSON")
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args()

    result = convert(Path(args.input))
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"✓ Converted {args.input} → {out_path}")
    print(f"   Queries: {len(result['queries'])}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
