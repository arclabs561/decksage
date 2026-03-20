# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "crowd-kit>=1.4.1",
#     "pandas>=2.0",
# ]
# ///
"""Dawid-Skene aggregation for multi-judge LLM annotations.

Replaces naive mean of similarity scores with probabilistic consensus
that estimates per-judge reliability via EM.

Usage:
    uv run scripts/evaluation/aggregate_dawid_skene.py [--files FILE ...]

Inputs: multi-judge annotation JSONs with per_judge similarity_score fields.
Output: per-model error matrices, consensus vs naive comparison, reliability.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from crowdkit.aggregation import DawidSkene


def score_to_ordinal(score: float) -> int:
    """Bucket continuous [0,1] similarity score to ordinal 0-5."""
    if score <= 0.05:
        return 0  # unrelated
    if score <= 0.15:
        return 1  # barely related
    if score <= 0.30:
        return 2  # weakly related
    if score <= 0.50:
        return 3  # moderately related
    if score <= 0.75:
        return 4  # related
    return 5  # highly related


ORDINAL_LABELS = {
    0: "unrelated",
    1: "barely",
    2: "weak",
    3: "moderate",
    4: "related",
    5: "highly",
}


def load_annotations(paths: list[Path]) -> list[dict]:
    """Load and merge per_judge labels from multiple annotation files."""
    labels = []
    for p in paths:
        data = json.loads(p.read_text())
        for item in data.get("labels", []):
            if "per_judge" in item:
                labels.append(item)
    return labels


def build_crowd_df(labels: list[dict]) -> pd.DataFrame:
    """Build (worker, task, label) DataFrame for crowdkit."""
    rows = []
    for item in labels:
        task = f"{item['card1']}||{item['card2']}"
        for judge, ann in item["per_judge"].items():
            score = ann.get("similarity_score")
            if score is None:
                continue
            rows.append(
                {
                    "worker": judge,
                    "task": task,
                    "label": score_to_ordinal(score),
                }
            )
    return pd.DataFrame(rows)


def naive_consensus(labels: list[dict]) -> dict[str, float]:
    """Compute naive mean score per task (baseline)."""
    task_scores: dict[str, list[float]] = {}
    for item in labels:
        task = f"{item['card1']}||{item['card2']}"
        scores = [
            ann["similarity_score"]
            for ann in item["per_judge"].values()
            if ann.get("similarity_score") is not None
        ]
        if scores:
            task_scores[task] = sum(scores) / len(scores)
    return task_scores


def main() -> None:
    parser = argparse.ArgumentParser(description="Dawid-Skene annotation aggregation")
    parser.add_argument(
        "--files",
        nargs="+",
        type=Path,
        default=[
            Path("data/annotations/magic_multi_judge_100.json"),
            Path("data/annotations/magic_smart_200.json"),
        ],
        help="Multi-judge annotation files",
    )
    args = parser.parse_args()

    # Validate inputs
    for p in args.files:
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            sys.exit(1)

    labels = load_annotations(args.files)
    print(f"Loaded {len(labels)} annotated pairs from {len(args.files)} files")

    df = build_crowd_df(labels)
    workers = sorted(df["worker"].unique())
    print(f"Workers: {workers}")
    print(f"Tasks: {df['task'].nunique()}, Total annotations: {len(df)}")

    # Label distribution per worker
    print("\n--- Per-worker label distribution ---")
    for w in workers:
        wdf = df[df["worker"] == w]
        dist = wdf["label"].value_counts().sort_index()
        dist_str = "  ".join(f"{ORDINAL_LABELS[k]}={v}" for k, v in dist.items())
        print(f"  {w}: {dist_str}")

    # Run Dawid-Skene
    ds = DawidSkene(n_iter=100)
    ds.fit(df)

    consensus = ds.labels_
    print(f"\n--- Dawid-Skene consensus ({len(consensus)} tasks) ---")

    # Consensus label distribution
    cons_dist = consensus.value_counts().sort_index()
    print("Consensus distribution:")
    for k, v in cons_dist.items():
        print(f"  {ORDINAL_LABELS.get(k, k)}: {v}")

    # Per-worker error matrices
    print("\n--- Per-worker error matrices (rows=true, cols=predicted) ---")
    errors = ds.errors_
    for w in workers:
        if w in errors.index.get_level_values(0):
            print(f"\n  {w}:")
            wmat = errors.loc[w]
            # Show as compact table
            header = "  true\\pred  " + "  ".join(f"{ORDINAL_LABELS[c]:>8}" for c in wmat.columns)
            print(header)
            for row_label in wmat.index:
                vals = "  ".join(f"{wmat.loc[row_label, c]:8.3f}" for c in wmat.columns)
                print(f"  {ORDINAL_LABELS[row_label]:>9}  {vals}")

    # Compare with naive mean
    naive = naive_consensus(labels)
    print("\n--- Consensus vs Naive comparison ---")
    agreements = 0
    disagreements = []
    for task, ds_label in consensus.items():
        naive_score = naive.get(task)
        if naive_score is None:
            continue
        naive_label = score_to_ordinal(naive_score)
        if ds_label == naive_label:
            agreements += 1
        else:
            disagreements.append((task, naive_label, ds_label, naive_score))

    total = agreements + len(disagreements)
    print(f"Agreement: {agreements}/{total} ({100 * agreements / total:.1f}%)")
    print(f"Disagreements: {len(disagreements)}")

    if disagreements:
        print("\nTop disagreements (task, naive_label, ds_label, naive_score):")
        # Sort by magnitude of difference
        disagreements.sort(key=lambda x: abs(x[1] - x[2]), reverse=True)
        for task, nl, dl, ns in disagreements[:20]:
            c1, c2 = task.split("||")
            print(
                f"  {c1[:25]:25s} <-> {c2[:25]:25s}  "
                f"naive={ORDINAL_LABELS[nl]}({ns:.2f})  ds={ORDINAL_LABELS[dl]}"
            )

    # Per-worker reliability summary
    print("\n--- Per-worker reliability (diagonal mean of error matrix) ---")
    for w in workers:
        if w in errors.index.get_level_values(0):
            wmat = errors.loc[w]
            diag = [wmat.iloc[i, i] for i in range(min(wmat.shape))]
            used_labels = [l for l in wmat.index if l in consensus.values]
            if used_labels:
                weighted_diag = [wmat.loc[l, l] for l in used_labels]
                reliability = sum(weighted_diag) / len(weighted_diag)
            else:
                reliability = sum(diag) / len(diag)
            print(f"  {w}: {reliability:.3f}")


if __name__ == "__main__":
    main()
