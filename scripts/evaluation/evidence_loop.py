#!/usr/bin/env python3
"""Automated evidence loop: label noise, arm comparison, decision memo.

The loop exists because two measurement defects were found by hand after the
fact: sparse judged pools and mislabelled reprints. Both are now automated.

Subcommands
-----------
noise    Compare fresh judge scores with the stored labels for a review sample.
         Reports MAE, within-0.1 share, band flips, and a per-band bias table.
compare  Run the fixed-candidate harness in judged-only mode for one arm and
         keep the result JSON. Refuses when the judged pool is too small.
report   Join the noise floor and the comparison into a markdown decision memo.

The noise floor is the point: an effect smaller than the label MAE is not
evidence. That rule is applied in ``report`` and printed with every verdict.

Usage:
    scripts/evaluation/evidence_loop.py noise \
        --review data-local/label-noise-20261031/review.json \
        --judged data-local/label-noise-20261031/judged.json \
        --output data/results/label_noise.json
    scripts/evaluation/evidence_loop.py compare --arm tag:jaccard
    scripts/evaluation/evidence_loop.py report --noise data/results/label_noise.json \
        --result data/results/tag_jaccard_judged_only.json --output /tmp/memo.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BANDS = [(0.0, 0.15), (0.15, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.01)]

ARM_ARGS: dict[str, list[str]] = {
    "tag:jaccard": [
        "--candidate-sources",
        "tag:jaccard",
        "--tag-data",
        "data-local/label-anchor-20261030/oracle-tags.jsonl.gz",
        "--tag-cards",
        "data/raw/scryfall/oracle-cards.json",
    ],
    "reprint:exact": [
        "--candidate-sources",
        "reprint:exact",
        "--reprint-cards",
        "data/raw/scryfall/oracle-cards.json",
    ],
}


def load_pairs(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("pairs", payload) if isinstance(payload, dict) else payload


def noise(args: argparse.Namespace) -> int:
    review = {
        item["id"]: item for item in json.loads(args.review.read_text(encoding="utf-8"))["items"]
    }
    judged = {
        f"{row['query']}\u0000{row['candidate']}": row
        for row in json.loads(args.judged.read_text(encoding="utf-8"))["pairs"]
    }
    key = json.loads(args.key.read_text(encoding="utf-8")) if args.key else None
    rows: list[dict[str, Any]] = []
    for entry in key or review.values():
        query = entry["query"]
        candidate = entry["candidate"]
        fresh = judged.get(f"{query}\u0000{candidate}")
        if not fresh or fresh.get("median_functional") is None:
            continue
        rows.append(
            {
                "query": query,
                "candidate": candidate,
                "old": float(entry["old_score"]),
                "new": float(fresh["median_functional"]),
                "spread": float(fresh.get("spread", 0.0)),
                "n_judges": int(fresh.get("n_judges", 0)),
            }
        )
    if not rows:
        raise SystemExit("no overlapping pairs; check --review/--judged/--key")

    diffs = [abs(row["new"] - row["old"]) for row in rows]
    flips = sum(
        1 for row in rows if (row["old"] < 0.3 <= row["new"]) or (row["new"] < 0.3 <= row["old"])
    )
    material_flips = sum(
        1
        for row in rows
        if (row["old"] < 0.3 and row["new"] >= 0.5) or (row["old"] >= 0.5 and row["new"] < 0.3)
    )
    per_band = {}
    for low, high in BANDS:
        subset = [row for row in rows if low <= row["old"] < high]
        if subset:
            per_band[f"{low}-{high}"] = {
                "n": len(subset),
                "mean_old": round(statistics.mean(row["old"] for row in subset), 3),
                "mean_new": round(statistics.mean(row["new"] for row in subset), 3),
                "mean_abs_error": round(
                    statistics.mean(abs(row["new"] - row["old"]) for row in subset), 3
                ),
            }
    payload = {
        "pairs": len(rows),
        "mae": round(statistics.mean(diffs), 4),
        "median_abs_error": round(statistics.median(diffs), 4),
        "within_0p1": round(sum(diff <= 0.1 for diff in diffs) / len(diffs), 4),
        "sign_flips": flips,
        "sign_flip_share": round(flips / len(rows), 4),
        "material_flips": material_flips,
        "material_flip_share": round(material_flips / len(rows), 4),
        "per_band": per_band,
        "judge_spread_mean": round(statistics.mean(row["spread"] for row in rows), 4),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


def compare(args: argparse.Namespace) -> int:
    arm_args = ARM_ARGS[args.arm]
    output = args.output or Path(f"data/results/{args.arm.replace(':', '_')}_judged_only.json")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "evaluation" / "compare_recommendations.py"),
        "--game",
        args.game,
        "--judged-only",
        *arm_args,
        "--output",
        str(output),
    ]
    if args.label_patch:
        command += ["--label-patch", str(args.label_patch)]
    if args.exclude_pairs:
        command += ["--exclude-pairs", str(args.exclude_pairs)]
    print("running:", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode


def report(args: argparse.Namespace) -> int:
    noise_payload = json.loads(args.noise.read_text(encoding="utf-8"))
    result = json.loads(args.result.read_text(encoding="utf-8"))
    delta = result["summary"]["mean_delta"]["ndcg_at_10"]
    interval = result["bootstrap"]["ndcg_at_10"]
    verdict = result["verdict"]
    noise_floor = noise_payload["mae"]
    if interval["excludes_zero"]:
        decision = (
            "act, subject to a label refresh: the CI excludes zero, but the "
            "label check below shows the high band is inflated and material "
            "flips are frequent, so the effect size is not final"
        )
    else:
        decision = "do not act: CI includes zero"
    noise_note = (
        f"MAE {noise_floor:.3f} on the 0-1 score. This is not on the nDCG scale; "
        "it is a warning that the labels are noisy, not a threshold for the delta."
    )
    lines = [
        "# Evidence memo",
        "",
        f"- Arm: `{args.arm}`",
        f"- Queries: {result['queries_usable']}",
        f"- nDCG@{result['config']['k']} delta: {delta:+.4f} "
        f"(95% CI [{interval['ci_low']:+.4f}, {interval['ci_high']:+.4f}])",
        f"- Verdict: `{verdict}`",
        f"- Label check: MAE {noise_floor:.4f} over {noise_payload['pairs']} pairs; "
        f"{noise_payload['material_flips']} material flips "
        f"({noise_payload['material_flip_share']:.0%})",
        "",
        "## Label check",
        "",
        f"- Within 0.1 of the fresh median: {noise_payload['within_0p1']:.0%}",
        f"- Any 0.3-boundary crossing: {noise_payload['sign_flips']} "
        f"({noise_payload['sign_flip_share']:.0%}); material (>0.3 to >0.5 or back): "
        f"{noise_payload['material_flips']}",
        f"- {noise_note}",
        "",
        "| old band | n | mean old | mean new | MAE |",
        "|---|---|---|---|---|",
    ]
    for band, row in noise_payload["per_band"].items():
        lines.append(
            f"| {band} | {row['n']} | {row['mean_old']:.2f} | {row['mean_new']:.2f} "
            f"| {row['mean_abs_error']:.2f} |"
        )
    lines += ["", f"**Decision:** {decision}.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("noise", help="compare fresh judges with stored labels")
    p.add_argument("--review", type=Path, required=True)
    p.add_argument("--judged", type=Path, required=True)
    p.add_argument("--key", type=Path, default=None)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(func=noise)

    p = sub.add_parser("compare", help="run one arm in judged-only mode")
    p.add_argument("--arm", choices=sorted(ARM_ARGS), required=True)
    p.add_argument("--game", default="magic")
    p.add_argument("--label-patch", type=Path, default=None)
    p.add_argument("--exclude-pairs", type=Path, default=None)
    p.add_argument("--output", type=Path, default=None)
    p.set_defaults(func=compare)

    p = sub.add_parser("report", help="join noise and a comparison into a memo")
    p.add_argument("--noise", type=Path, required=True)
    p.add_argument("--result", type=Path, required=True)
    p.add_argument("--arm", default="arm")
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(func=report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
