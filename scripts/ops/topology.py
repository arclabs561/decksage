#!/usr/bin/env python3
"""Check the data-plane DAG: what is missing, what is stale, what is orphaned.

See config/topology.toml and src/ml/utils/topology.py.

Exit codes: 0 clean, 1 findings.

Usage:
    scripts/ops/topology.py check
    scripts/ops/topology.py check --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from ml.utils.topology import SPEC, assess, load_spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "json"), nargs="?", default="check")
    parser.add_argument("--spec", type=Path, default=SPEC)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = assess(load_spec(args.spec), args.root)
    if args.command == "json" or args.json:
        print(json.dumps(report, indent=2))
    else:
        findings = report["findings"]
        print(f"nodes {len(report['nodes'])}  edges {len(report['edges'])}")
        for key, label in (
            ("missing", "missing"),
            ("stale", "stale"),
            ("unknown_inputs", "unknown input"),
            ("cycles", "cycle"),
        ):
            for item in findings[key]:
                print(f"  {label}: {item}")
        if report["ok"]:
            print("topology ok")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
