#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#     "numpy>=1.26.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Evaluate rank fusion of multiple embedding sources.

Combines Cleora (graph structure) + Text E5 (card text semantics) via
CombMNZ rank fusion. Each source provides a ranked list per query,
and the fused ranking uses reciprocal rank weighting.

Query selection is explicit. `--split all` (default) scores every query, which
includes the queries `calibrate_fusion_weights.py` fit on, so the number is
in-sample and not a generalization estimate. `--split train` and
`--split holdout` use the same seed-13 query partition as the calibrator, so
`--split holdout` is the out-of-sample number for those weights.

Usage:
    uv run scripts/evaluation/eval_fusion.py --game magic
    uv run scripts/evaluation/eval_fusion.py --game magic --sources cleora_1iter,text_e5
    uv run scripts/evaluation/eval_fusion.py --game magic --json
    uv run scripts/evaluation/eval_fusion.py --game magic --split holdout --json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Iterable
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors


if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Task -> score field is shared with eval_per_mode.py (ADR-0001); see task_labels.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_labels import TASK_SCORE_FIELD


DEFAULT_SOURCES = {
    "magic": ["cleora_1iter", "text_e5"],
    "pokemon": ["cleora_5iter", "text_e5"],
    "yugioh": ["cleora_3iter", "text_e5"],
}

# Shared with scripts/training/calibrate_fusion_weights.py: the calibrator
# shuffles the sorted query names with a seed-13 RNG, fits on the first 80% and
# reports the remaining 20%. Reusing both constants keeps this script's
# train/holdout partition aligned with the one that produced the weights.
SPLIT_SEED = 13
TRAIN_FRACTION = 0.8
SPLIT_CHOICES = ("all", "train", "holdout")


def split_query_names(names: Iterable[str], split: str, seed: int = SPLIT_SEED) -> list[str]:
    """Return the query names that belong to `split`.

    Deterministic and exhaustive for a fixed seed: `train` and `holdout`
    partition the query names with no overlap and no gaps, and `all` returns
    every name.
    """
    if split not in SPLIT_CHOICES:
        raise ValueError(f"unknown split {split!r}; expected one of {SPLIT_CHOICES}")

    ordered = sorted(names)
    if split == "all":
        return ordered
    random.Random(seed).shuffle(ordered)
    n_train = int(len(ordered) * TRAIN_FRACTION)
    return ordered[:n_train] if split == "train" else ordered[n_train:]


def split_note(split: str, seed: int, n_queries: int, n_total: int) -> dict:
    """Describe what a nDCG number from `split` does and does not measure."""
    if split == "all":
        return {
            "partial": False,
            "in_sample": True,
            "note": (
                f"In-sample result over all {n_total} queries, including the queries "
                f"calibrate_fusion_weights.py fit fusion weights on. Not a "
                f"generalization estimate; use --split holdout for that."
            ),
        }
    if split == "train":
        return {
            "partial": True,
            "in_sample": True,
            "note": (
                f"Partial result: the {n_queries} fit queries of the seed-{seed} 80% "
                f"split, the same queries calibrate_fusion_weights.py optimizes on. "
                f"In-sample, covers {n_queries}/{n_total} queries, and not a "
                f"generalization estimate."
            ),
        }
    return {
        "partial": True,
        "in_sample": False,
        "note": (
            f"Partial result: the {n_queries} held-out queries of the seed-{seed} 20% "
            f"split, out-of-sample for weights fit on the complementary 80%. Covers "
            f"only {n_queries}/{n_total} queries, so it is not comparable to a "
            f"full-test-set number."
        ),
    }


def ndcg(relevances: list[float], ideal: list[float], k: int) -> float:
    def dcg(rels: list[float], k: int) -> float:
        return sum(r / np.log2(i + 2) for i, r in enumerate(rels[:k]))

    ideal_dcg = dcg(sorted(ideal, reverse=True), k)
    if ideal_dcg == 0:
        return 0.0
    return dcg(relevances, k) / ideal_dcg


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Fuse multiple ranked lists via Reciprocal Rank Fusion (RRF)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            scores[item] = scores.get(item, 0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate rank fusion of embeddings")
    parser.add_argument("--game", default="magic")
    parser.add_argument(
        "--sources",
        type=str,
        default="",
        help="Comma-separated embedding names (default: game-specific best)",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument(
        "--candidates", type=int, default=100, help="Candidates per source before fusion"
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--split",
        choices=SPLIT_CHOICES,
        default="all",
        help=(
            "Query subset to evaluate: 'all' (in-sample, default), 'train' "
            "(the 80% fit split), or 'holdout' (the 20% out-of-sample split)"
        ),
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=SPLIT_SEED,
        help=f"Seed for the train/holdout partition (default: {SPLIT_SEED})",
    )
    args = parser.parse_args()

    # Determine sources
    if args.sources:
        source_names = [s.strip() for s in args.sources.split(",")]
    else:
        source_names = DEFAULT_SOURCES.get(args.game, ["cleora_5iter", "text_e5"])

    print(f"Fusion eval [{args.game}]: {source_names}")

    # Load embeddings
    sources: list[tuple[str, KeyedVectors]] = []
    for name in source_names:
        path = DATA_DIR / "embeddings" / f"{args.game}_{name}.wv"
        if not path.exists():
            print(f"  WARNING: {path} not found, skipping")
            continue
        kv = KeyedVectors.load(str(path))
        sources.append((name, kv))
        print(f"  Loaded {name}: {len(kv)} cards")

    if len(sources) < 2:
        print("Need at least 2 sources for fusion")
        return 1

    # Load test set
    test_path = DATA_DIR / "test_sets" / f"annotated_{args.game}_v2.json"
    if not test_path.exists():
        print(f"Test set not found: {test_path}")
        return 1

    with open(test_path) as f:
        test_data = json.load(f)
    all_queries = test_data.get("queries", {})

    # Restrict scoring to the requested query split (both the fused and the
    # per-source loops below read from `queries`).
    selected_names = split_query_names(all_queries, args.split, args.split_seed)
    queries = {name: all_queries[name] for name in selected_names}
    if args.split != "all" and not args.json:
        print(
            f"  Split: {args.split} "
            f"({len(queries)}/{len(all_queries)} queries, seed {args.split_seed})"
        )

    # Evaluate per mode
    results = {}
    for mode, score_field in TASK_SCORE_FIELD.items():
        ndcg_scores = []
        n_evaluated = 0
        n_skipped = 0

        for qname, qdata in queries.items():
            annotations = qdata.get("annotations", [])
            if not annotations:
                n_skipped += 1
                continue

            # Build ground truth
            gt = {}
            for ann in annotations:
                candidate = ann.get("candidate", "")
                score = ann.get(score_field)
                if score is not None and candidate:
                    gt[candidate] = float(score)

            if not gt or max(gt.values()) == 0:
                n_skipped += 1
                continue

            # Get candidates from each source
            rankings = []
            can_query = True
            for name, kv in sources:
                if qname not in kv:
                    can_query = False
                    break
                try:
                    neighbors = kv.most_similar(qname, topn=args.candidates)
                    rankings.append([card for card, _ in neighbors])
                except KeyError:
                    can_query = False
                    break

            if not can_query or not rankings:
                n_skipped += 1
                continue

            # Fuse rankings
            fused = reciprocal_rank_fusion(rankings)[: args.top_k]

            # Score
            relevances = [gt.get(card, 0.0) for card in fused]
            ideal = sorted(gt.values(), reverse=True)
            score = ndcg(relevances, ideal, args.top_k)
            ndcg_scores.append(score)
            n_evaluated += 1

        avg_ndcg = float(np.mean(ndcg_scores)) if ndcg_scores else 0.0
        results[f"{mode}_ndcg"] = round(avg_ndcg, 4)
        results[f"{mode}_n"] = n_evaluated
        if not args.json:
            print(f"  {mode}: nDCG@{args.top_k} = {avg_ndcg:.4f} (n={n_evaluated})")

    # Also evaluate individual sources for comparison
    individual = {}
    for name, kv in sources:
        src_ndcg = []
        for qname, qdata in queries.items():
            annotations = qdata.get("annotations", [])
            if not annotations or qname not in kv:
                continue
            gt = {}
            for ann in annotations:
                candidate = ann.get("candidate", "")
                score = ann.get(TASK_SCORE_FIELD["substitute"])
                if score is not None and candidate:
                    gt[candidate] = float(score)
            if not gt or max(gt.values()) == 0:
                continue
            try:
                neighbors = kv.most_similar(qname, topn=args.top_k)
                relevances = [gt.get(card, 0.0) for card, _ in neighbors]
                ideal = sorted(gt.values(), reverse=True)
                src_ndcg.append(ndcg(relevances, ideal, args.top_k))
            except KeyError:
                continue
        avg = float(np.mean(src_ndcg)) if src_ndcg else 0.0
        individual[name] = round(avg, 4)
        if not args.json:
            print(f"  [{name} alone]: sub nDCG = {avg:.4f}")

    results["individual_sub_ndcg"] = individual
    results["sources"] = source_names
    results["game"] = args.game

    # Split provenance: a reader must be able to tell in-sample from out-of-sample.
    split_info = split_note(args.split, args.split_seed, len(queries), len(all_queries))
    results["split"] = args.split
    results["split_seed"] = args.split_seed
    results["n_queries"] = len(queries)
    results["partial"] = split_info["partial"]
    results["in_sample"] = split_info["in_sample"]
    results["note"] = split_info["note"]

    results["data"] = {
        "num_queries": len(all_queries),
        "split_queries": len(queries),
        "source_sizes": {name: len(kv) for name, kv in sources},
    }

    if not args.json and args.split != "all":
        print(f"  {split_info['note']}")

    if args.json:
        print(json.dumps(results, indent=2))

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback

        traceback.print_exc()
        sys.exit(1)
