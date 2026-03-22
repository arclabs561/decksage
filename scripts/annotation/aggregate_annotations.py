# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "crowd-kit>=1.4.0",
#     "pandas>=2.0.0",
# ]
# ///
"""Aggregate multi-model LLM annotations using crowd-kit.

Loads diverse pair checkpoint files, converts continuous similarity scores
to categorical bins for Dawid-Skene / MajorityVote / GLAD, then produces
consensus labels and per-model reliability estimates.

For EVALUATION quality measurement only -- consensus labels help understand
annotation quality but do NOT feed into training.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ANNOTATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "annotations"

# Discretize continuous [0, 1] scores into 5 ordinal bins.
BIN_EDGES = [0.0, 0.2, 0.4, 0.6, 0.8, 1.01]
BIN_LABELS = ["0.0-0.2", "0.2-0.4", "0.4-0.6", "0.6-0.8", "0.8-1.0"]


def load_checkpoint(game: str) -> pd.DataFrame:
    """Load JSONL checkpoint into a DataFrame."""
    path = ANNOTATIONS_DIR / f"diverse_checkpoint_{game}.jsonl"
    if not path.exists():
        print(f"ERROR: checkpoint not found: {path}", file=sys.stderr)
        sys.exit(1)

    records = []
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            records.append(row)

    df = pd.DataFrame(records)
    print(f"Loaded {len(df)} annotations from {path.name}")
    return df


def prepare_crowd_df(df: pd.DataFrame) -> pd.DataFrame:
    """Convert to crowd-kit format: columns [task, worker, label].

    task = (query, candidate) tuple serialized as string.
    worker = llm_model.
    label = discretized similarity bin.
    """
    crowd = pd.DataFrame()
    crowd["task"] = df.apply(lambda r: f"{r['query']}||{r['candidate']}", axis=1)
    crowd["worker"] = df["llm_model"]
    crowd["label"] = pd.cut(
        df["similarity_score"].clip(0.0, 1.0),
        bins=BIN_EDGES,
        labels=BIN_LABELS,
        include_lowest=True,
        right=False,
    ).astype(str)
    return crowd


def print_data_summary(df: pd.DataFrame, crowd: pd.DataFrame) -> None:
    """Print summary statistics for dry-run inspection."""
    pairs = df.groupby(["query", "candidate"]).size()
    models = df["llm_model"].value_counts()

    print(f"\n--- Data Summary ---")
    print(f"Total annotations:  {len(df)}")
    print(f"Unique pairs:       {len(pairs)}")
    print(f"Models:             {len(models)}")
    for model, count in models.items():
        print(f"  {model}: {count}")

    print(f"\nPairs with N annotators:")
    annotator_counts = pairs.value_counts().sort_index()
    for n, count in annotator_counts.items():
        print(f"  {n} annotators: {count} pairs")

    print(f"\nLabel distribution (discretized bins):")
    label_dist = crowd["label"].value_counts().sort_index()
    for label, count in label_dist.items():
        print(f"  {label}: {count} ({100 * count / len(crowd):.1f}%)")

    print(f"\nSimilarity score stats:")
    scores = df["similarity_score"]
    print(f"  mean={scores.mean():.3f}  median={scores.median():.3f}  "
          f"std={scores.std():.3f}  min={scores.min():.3f}  max={scores.max():.3f}")


def run_aggregation(crowd: pd.DataFrame, df_raw: pd.DataFrame) -> dict:
    """Run DawidSkene, MajorityVote, and GLAD. Return results dict."""
    from crowdkit.aggregation import GLAD, DawidSkene, MajorityVote

    results: dict = {}

    # --- Dawid-Skene ---
    print("\nRunning Dawid-Skene (n_iter=20)...")
    ds = DawidSkene(n_iter=20)
    ds_labels = ds.fit_predict(crowd)
    results["dawid_skene"] = {
        "labels": ds_labels.to_dict(),
    }

    # Extract per-worker error matrices (confusion matrices).
    # ds.errors_ is a DataFrame indexed by worker with columns (true_label, given_label).
    if hasattr(ds, "errors_") and ds.errors_ is not None:
        error_rates = {}
        for worker in ds.errors_.index.get_level_values(0).unique():
            worker_err = ds.errors_.loc[worker]
            # Diagonal = correct rate per true label.
            if hasattr(worker_err, "values"):
                diag = worker_err.values.diagonal() if hasattr(worker_err.values, "diagonal") else None
                error_rates[worker] = {
                    "mean_accuracy": float(diag.mean()) if diag is not None else None,
                }
        results["dawid_skene"]["worker_reliability"] = error_rates
        print("\nPer-model reliability (Dawid-Skene diagonal accuracy):")
        for worker, info in sorted(error_rates.items(), key=lambda x: x[1].get("mean_accuracy", 0) or 0, reverse=True):
            acc = info.get("mean_accuracy")
            print(f"  {worker}: {acc:.3f}" if acc is not None else f"  {worker}: N/A")

    # --- MajorityVote ---
    print("\nRunning MajorityVote...")
    mv = MajorityVote()
    mv_labels = mv.fit_predict(crowd)
    results["majority_vote"] = {
        "labels": mv_labels.to_dict(),
    }

    # --- GLAD ---
    print("\nRunning GLAD...")
    try:
        glad = GLAD(n_iter=20)
        glad_labels = glad.fit_predict(crowd)
        results["glad"] = {
            "labels": glad_labels.to_dict(),
        }
    except Exception as e:
        print(f"  GLAD failed: {e}")
        results["glad"] = {"error": str(e)}

    # --- Agreement stats ---
    common_tasks = set(ds_labels.index) & set(mv_labels.index)
    if common_tasks:
        agree = sum(1 for t in common_tasks if ds_labels[t] == mv_labels[t])
        print(f"\nDS vs MV agreement: {agree}/{len(common_tasks)} "
              f"({100 * agree / len(common_tasks):.1f}%)")

    if "labels" in results.get("glad", {}):
        glad_labels = pd.Series(results["glad"]["labels"])
        common_ds_glad = set(ds_labels.index) & set(glad_labels.index)
        if common_ds_glad:
            agree = sum(1 for t in common_ds_glad if ds_labels[t] == glad_labels[t])
            print(f"DS vs GLAD agreement: {agree}/{len(common_ds_glad)} "
                  f"({100 * agree / len(common_ds_glad):.1f}%)")

    # --- Weighted continuous consensus ---
    # Use DS worker reliability to compute reliability-weighted mean of raw scores.
    print("\nComputing reliability-weighted continuous consensus...")
    worker_weights = {}
    if "worker_reliability" in results.get("dawid_skene", {}):
        for w, info in results["dawid_skene"]["worker_reliability"].items():
            acc = info.get("mean_accuracy")
            worker_weights[w] = acc if acc is not None else 1.0
    else:
        # Uniform weights fallback.
        for w in crowd["worker"].unique():
            worker_weights[w] = 1.0

    # Build per-task weighted mean from raw continuous scores.
    df_with_task = df_raw.copy()
    df_with_task["task"] = df_with_task.apply(
        lambda r: f"{r['query']}||{r['candidate']}", axis=1
    )
    df_with_task["weight"] = df_with_task["llm_model"].map(worker_weights).fillna(1.0)
    df_with_task["weighted_score"] = df_with_task["similarity_score"] * df_with_task["weight"]

    grouped = df_with_task.groupby("task").agg(
        weighted_sum=("weighted_score", "sum"),
        weight_sum=("weight", "sum"),
        raw_mean=("similarity_score", "mean"),
        raw_std=("similarity_score", "std"),
        n_annotators=("llm_model", "nunique"),
    )
    grouped["consensus_score"] = grouped["weighted_sum"] / grouped["weight_sum"]
    results["continuous_consensus"] = grouped[
        ["consensus_score", "raw_mean", "raw_std", "n_annotators"]
    ].to_dict(orient="index")

    print(f"  Computed consensus for {len(grouped)} pairs")
    print(f"  Mean consensus score: {grouped['consensus_score'].mean():.3f}")
    print(f"  Mean raw std across annotators: {grouped['raw_std'].mean():.3f}")

    return results


def save_results(results: dict, game: str) -> Path:
    """Save aggregated results to JSON."""
    out_path = ANNOTATIONS_DIR / f"consensus_{game}.json"

    # Convert any remaining non-serializable types.
    def clean(obj: object) -> object:
        if isinstance(obj, float) and (obj != obj):  # NaN
            return None
        return obj

    serializable = json.loads(json.dumps(results, default=str))
    with open(out_path, "w") as f:
        json.dump(serializable, f, indent=2, default=clean)
    print(f"\nSaved results to {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate multi-model annotations")
    parser.add_argument("--game", required=True, choices=["magic", "pokemon", "yugioh"])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load and summarize data without running aggregation",
    )
    parser.add_argument(
        "--min-annotators",
        type=int,
        default=2,
        help="Minimum annotators per pair to include (default: 2)",
    )
    args = parser.parse_args()

    df = load_checkpoint(args.game)
    crowd = prepare_crowd_df(df)

    # Filter to pairs with enough annotators.
    task_counts = crowd.groupby("task")["worker"].nunique()
    valid_tasks = task_counts[task_counts >= args.min_annotators].index
    crowd_filtered = crowd[crowd["task"].isin(valid_tasks)].copy()
    df_filtered = df[
        df.apply(lambda r: f"{r['query']}||{r['candidate']}", axis=1).isin(valid_tasks)
    ].copy()

    dropped = len(crowd) - len(crowd_filtered)
    if dropped > 0:
        print(f"Filtered to pairs with >= {args.min_annotators} annotators: "
              f"dropped {dropped} annotations "
              f"({len(task_counts) - len(valid_tasks)} pairs)")

    print_data_summary(df_filtered, crowd_filtered)

    if args.dry_run:
        print("\n[dry-run] Skipping aggregation. Data loaded successfully.")
        return

    results = run_aggregation(crowd_filtered, df_filtered)
    results["meta"] = {
        "game": args.game,
        "total_annotations": len(df_filtered),
        "unique_pairs": int(crowd_filtered["task"].nunique()),
        "models": sorted(df_filtered["llm_model"].unique().tolist()),
        "min_annotators": args.min_annotators,
        "bin_edges": BIN_EDGES,
        "bin_labels": BIN_LABELS,
    }
    save_results(results, args.game)


if __name__ == "__main__":
    main()
