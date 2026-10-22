#!/usr/bin/env python3
"""Resolution and agreement audit for annotation scores.

Stage 0 of docs/JUDGE-CALIBRATION.md: free checks that decide whether buying
human labels is worth it.

Usage:
    uv run scripts/evaluation/judge_audit.py --game magic
    uv run scripts/evaluation/judge_audit.py --all-games --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.utils.paths import PATHS


FIELDS = [
    "similarity_score",
    "functional_score",
    "synergy_score",
    "meta_relevance",
    "substitutability",
]


def load_annotations(game: str) -> list[dict]:
    path = PATHS.data / "test_sets" / f"annotated_{game}_v2.json"
    with open(path) as f:
        data = json.load(f)
    out = []
    for query, entry in data.get("queries", {}).items():
        for ann in entry.get("annotations", []):
            out.append({"query": query, **ann})
    return out


def field_stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "status": "absent"}
    bins = [0] * 10
    for v in values:
        bins[min(9, max(0, int(v * 10)))] += 1
    counts: dict[float, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    modal_share = max(counts.values()) / len(values)
    bin_share = max(bins) / len(values)
    return {
        "n": len(values),
        "status": "measured",
        "mean": round(statistics.fmean(values), 4),
        "sd": round(statistics.pstdev(values), 4) if len(values) > 1 else 0.0,
        "distinct": len(counts),
        "tie_rate": round(1 - len(counts) / len(values), 4),
        "zero_share": round(sum(1 for v in values if v == 0.0) / len(values), 4),
        # Same quantity as judge_probe.py: the largest 0.1-width bin. The share
        # of the single most common exact value is reported separately, because
        # quantised scores make that number large without meaning compression.
        "largest_bin_share": round(bin_share, 4),
        "modal_value_share": round(modal_share, 4),
        "histogram": bins,
        "verdict": resolution_verdict(values, bin_share),
    }


def resolution_verdict(values: list[float], bin_share: float) -> str:
    """Judge usability from the distribution, not from the raw tie count.

    tie_rate mostly reflects score quantization (two decimals), so it is
    reported but not decisive. Compression shows up as low spread, heavy mass
    in one bin, or a large exact-zero share, which flattens ranking.
    """
    sd = statistics.pstdev(values) if len(values) > 1 else 0.0
    zero_share = sum(1 for v in values if v == 0.0) / len(values)
    if sd < 0.05 or bin_share > 0.8:
        return "compressed: fix prompt or split into subscores before labeling"
    if zero_share > 0.7:
        return "deflated: most pairs scored zero, ranking power lost"
    if bin_share > 0.6:
        return "concentrated: most mass in one bin"
    return "usable"


def audit(game: str) -> dict:
    anns = load_annotations(game)
    result: dict = {"game": game, "annotations": len(anns), "fields": {}}
    for field in FIELDS:
        vals = [float(a[field]) for a in anns if a.get(field) is not None]
        result["fields"][field] = field_stats(vals)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Judge score resolution audit")
    parser.add_argument("--game", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game or "magic"]
    results = [audit(g) for g in games]

    if args.json:
        print(json.dumps(results, indent=2))
        return 0

    for res in results:
        print(f"\n{res['game']}: {res['annotations']:,} annotations")
        print(
            f"  {'field':18s} {'n':>6s} {'mean':>6s} {'sd':>6s} {'distinct':>8s} "
            f"{'ties':>6s} {'zero':>6s}  verdict"
        )
        for field, st in res["fields"].items():
            if st["status"] == "absent":
                print(f"  {field:18s} {'-':>6s} {'-':>6s} {'-':>6s} {'-':>8s} {'-':>6s}  absent")
                continue
            print(
                f"  {field:18s} {st['n']:>6d} {st['mean']:>6.3f} {st['sd']:>6.3f} "
                f"{st['distinct']:>8d} {st['tie_rate']:>6.2f} {st['zero_share']:>6.2f}  {st['verdict']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
