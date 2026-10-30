#!/usr/bin/env python3
"""Remove conflicting duplicate bucket memberships into a new dataset file.

Only remove an inconsistent membership when the same candidate already occurs
in the bucket implied by its annotation score. Scored annotations, bucket-only
labels and disagreements without a matching membership are left untouched.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path


BANDS = (
    ("highly_relevant", 0.70),
    ("relevant", 0.50),
    ("somewhat_relevant", 0.30),
    ("marginally_relevant", 0.15),
    ("irrelevant", 0.0),
)


def repair(data: dict) -> tuple[dict, int]:
    """Return a repaired copy and the number of memberships removed."""
    result = copy.deepcopy(data)
    removed = 0
    for entry in result.get("queries", {}).values():
        annotations = entry.get("annotations", [])
        names = [ann.get("candidate") for ann in annotations]
        if len(names) != len(set(names)):
            raise ValueError("duplicate annotation candidates; resolve before repair")
        for ann in annotations:
            name, value = ann.get("candidate"), ann.get("similarity_score")
            if not isinstance(name, str) or not isinstance(value, (int, float)):
                continue
            if not math.isfinite(value) or not 0 <= value <= 1:
                continue
            correct = next(bucket for bucket, threshold in BANDS if value >= threshold)
            if name not in entry.get(correct, []):
                continue
            for bucket, _ in BANDS:
                if bucket == correct or bucket not in entry:
                    continue
                old = entry[bucket]
                new = [candidate for candidate in old if candidate != name]
                removed += len(old) - len(new)
                entry[bucket] = new
    return result, removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, help="new file; never overwrites source or output")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("source and output must differ")
    raw = args.source.read_bytes()
    repaired, removed = repair(json.loads(raw))
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(repaired, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"source_sha256={hashlib.sha256(raw).hexdigest()} removed={removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
