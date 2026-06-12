#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""
Generate experiment YAML from a training run summary JSON.

Reads the JSON produced by train_metapath2vec.py (or any training script that
writes the same format) and produces a properly structured experiment YAML.

Usage:
    uv run scripts/evaluation/log_experiment.py data/logs/magic_metapath2vec_run.json
    uv run scripts/evaluation/log_experiment.py data/logs/magic_metapath2vec_run.json --hypothesis "Testing 320 epochs"
    uv run scripts/evaluation/log_experiment.py data/logs/magic_metapath2vec_run.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def next_experiment_id(experiments_dir: Path) -> str:
    existing = sorted(experiments_dir.glob("*.yaml"))
    if not existing:
        return "0001"
    last = existing[-1].stem.split("_")[0]
    return f"{int(last) + 1:04d}"


def build_experiment(run: dict, exp_id: str, hypothesis: str | None = None) -> dict:
    game = run["game"]
    params = run["params"]
    ev = run.get("eval") or {}

    sub = ev.get("sub_ndcg")
    title_metric = f"sub nDCG {sub:.4f}" if sub else "results pending"
    # Handle different param keys (epochs for MetaPath2Vec, iterations for Cleora)
    epoch_str = str(params.get("epochs", params.get("iterations", "?")))
    title = f"{run['model']} {epoch_str}ep: {title_metric}"

    exp = {
        "id": exp_id,
        "date": run["timestamp"][:10],
        "title": title,
        "game": game,
        "hypothesis": hypothesis or "TODO: fill in before committing",
        "method": {
            "type": "embedding",
            "script": f"scripts/training/train_{run['model']}.py",
            "args": " ".join(f"--{k.replace('_', '-')} {v}" for k, v in params.items()),
            "commit": run.get("git_sha", "unknown"),
        },
        "data": dict(run.get("data", {}).items()),
        "results": {},
        "conclusion": "TODO: fill in after reviewing results",
        "artifacts": list(run.get("artifacts", {}).values())
        if isinstance(run.get("artifacts"), dict)
        else run.get("artifacts", []),
    }

    if ev:
        for key in [
            "sub_ndcg",
            "syn_ndcg",
            "meta_ndcg",
            "substitutability_ndcg",
            "catalog_coverage",
            "novelty",
            "bias_ratio",
        ]:
            if key in ev:
                exp["results"][key] = ev[key]

    tr = run.get("training", {})
    if tr.get("final_loss") is not None:
        exp["results"]["final_loss"] = tr["final_loss"]
    if tr.get("duration_s") is not None:
        exp["results"]["duration_s"] = tr["duration_s"]

    if run.get("quality_pairs"):
        exp["results"]["quality_pairs"] = run["quality_pairs"]

    return exp


def append_to_summary(experiments_dir: Path, exp_id: str, exp: dict, filename: str) -> None:
    summary_path = experiments_dir / "SUMMARY.md"
    if not summary_path.exists():
        return

    game = exp["game"]
    sub = exp["results"].get("sub_ndcg", "--")
    title_short = exp["title"][:45]

    row = f"| {exp_id} | {exp['date']} | {title_short} | {game} | sub nDCG | {sub} | [{exp_id}]({filename}) |"

    content = summary_path.read_text()
    marker = "## Key Insights"
    if marker in content:
        content = content.replace(marker, f"{row}\n\n{marker}")
    else:
        content += f"\n{row}\n"
    summary_path.write_text(content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate experiment YAML from run summary")
    parser.add_argument("run_json", type=Path, help="Path to run summary JSON")
    parser.add_argument("--hypothesis", type=str, help="Experiment hypothesis")
    parser.add_argument("--dry-run", action="store_true", help="Print YAML without writing")
    parser.add_argument("--no-summary", action="store_true", help="Don't update SUMMARY.md")
    args = parser.parse_args()

    if not args.run_json.exists():
        print(f"Run summary not found: {args.run_json}", file=sys.stderr)
        return 1

    with open(args.run_json) as f:
        run = json.load(f)

    experiments_dir = Path(__file__).resolve().parent.parent.parent / "data" / "experiments"
    exp_id = next_experiment_id(experiments_dir)
    exp = build_experiment(run, exp_id, args.hypothesis)

    yaml_str = yaml.dump(exp, default_flow_style=False, sort_keys=False, allow_unicode=True)

    if args.dry_run:
        print(yaml_str)
        return 0

    slug = run["model"] + "_" + str(run["params"]["epochs"]) + "ep"
    filename = f"{exp_id}_{slug}.yaml"
    out_path = experiments_dir / filename
    with open(out_path, "w") as f:
        f.write(yaml_str)
    print(f"Wrote {out_path}")

    if not args.no_summary:
        append_to_summary(experiments_dir, exp_id, exp, filename)
        print(f"Updated {experiments_dir / 'SUMMARY.md'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
