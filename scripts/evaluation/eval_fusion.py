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

Usage:
    uv run scripts/evaluation/eval_fusion.py --game magic
    uv run scripts/evaluation/eval_fusion.py --game magic --sources cleora_1iter,text_e5
    uv run scripts/evaluation/eval_fusion.py --game magic --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors


if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

MODE_SCORE_FIELD = {
    "substitute": "functional_score",
    "synergy": "synergy_score",
    "meta": "meta_relevance",
}

DEFAULT_SOURCES = {
    "magic": ["cleora_1iter", "text_e5"],
    "pokemon": ["cleora_5iter", "text_e5"],
    "yugioh": ["cleora_3iter", "text_e5"],
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
    queries = test_data.get("queries", {})

    # Evaluate per mode
    results = {}
    for mode, score_field in MODE_SCORE_FIELD.items():
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
                score = ann.get("functional_score")
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
    results["data"] = {
        "num_queries": len(queries),
        "source_sizes": {name: len(kv) for name, kv in sources},
    }

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
