#!/usr/bin/env python3
"""Create a curated evaluation copy and a quarantine ledger; never overwrite input."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ml.contracts.annotations import curate_evaluation_data, is_evaluation_record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    paths = {p.resolve() for p in (args.source, args.output, args.ledger)}
    if len(paths) != 3 or args.output.exists() or args.ledger.exists():
        parser.error("source, output, and ledger must be distinct; output and ledger must be new")
    raw = args.source.read_bytes()
    data = json.loads(raw)
    curated, removed = curate_evaluation_data(data)
    quarantined = [
        {"query": query, "record": ann}
        for query, entry in data.get("queries", {}).items()
        for ann in entry.get("annotations", [])
        if not is_evaluation_record(ann)
    ]
    assert len(quarantined) == removed
    output_bytes = (json.dumps(curated, indent=2, ensure_ascii=False) + "\n").encode()
    ledger = {
        "source": str(args.source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "removed": removed,
        "criteria": "synthetic, augmented, failed, cosine fallback, or malformed provenance",
        "records": quarantined,
    }
    with args.output.open("xb") as handle:
        handle.write(output_bytes)
    with args.ledger.open("x", encoding="utf-8") as handle:
        json.dump(ledger, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(f"removed={removed} output_sha256={ledger['output_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
