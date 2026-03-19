#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Per-mode nDCG evaluation using annotated test sets.

Computes nDCG@K for each similarity mode (substitute, synergy, meta) by
filtering annotated pairs to mode-relevant ground truth and scoring
the embedding's ranking against it.

Uses the per-pair annotations already in annotated_*_v2.json:
- functional_score (0-1): ground truth for substitute mode
- synergy_score (0-1): ground truth for synergy mode
- meta_relevance (0-1): ground truth for meta mode
- mode (substitution/synergy/meta): primary mode classification

Requires: annotated test sets with per-pair annotations (not just buckets).

Usage:
    uv run scripts/evaluation/eval_per_mode.py --game magic
    uv run scripts/evaluation/eval_per_mode.py --game magic --embedding magic_v5_fused
    uv run scripts/evaluation/eval_per_mode.py --all-games
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

try:
    from gensim.models import KeyedVectors
except ImportError:
    print("Install gensim: pip install gensim")
    sys.exit(1)

DEFAULT_EMBEDDINGS = {
    "magic": "magic_cleaned_v4",
    "pokemon": "pokemon_cleaned_v4",
    "yugioh": "yugioh_cleaned_v5",
}

V5_EMBEDDINGS = {
    "magic": "magic_v5_fused",
    "pokemon": "pokemon_v5_fused",
    "yugioh": "yugioh_enriched_v6",
}

# Mode -> which annotation score field to use as ground truth
MODE_SCORE_FIELD = {
    "substitute": "functional_score",
    "synergy": "synergy_score",
    "meta": "meta_relevance",
}


def dcg(relevances: list[float], k: int) -> float:
    """Discounted cumulative gain at k."""
    r = np.array(relevances[:k], dtype=float)
    if r.size == 0:
        return 0.0
    discounts = np.log2(np.arange(2, r.size + 2))
    return float(np.sum(r / discounts))


def ndcg(relevances: list[float], ideal: list[float], k: int) -> float:
    """Normalized DCG at k."""
    idcg = dcg(sorted(ideal, reverse=True), k)
    if idcg == 0:
        return 0.0
    return dcg(relevances, k) / idcg


def load_test_set(game: str) -> dict:
    """Load annotated test set."""
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not path.exists():
        print(f"Test set not found: {path}")
        return {}
    with open(path) as f:
        return json.load(f)


def load_embeddings(game: str, name: str | None = None) -> KeyedVectors | None:
    """Load embedding file."""
    if name is None:
        name = DEFAULT_EMBEDDINGS.get(game, f"{game}_cleaned_v4")
    path = DATA_DIR / "embeddings" / f"{name}.wv"
    if not path.exists():
        print(f"Embedding not found: {path}")
        return None
    return KeyedVectors.load(str(path))


def eval_mode(
    wv: KeyedVectors,
    queries: dict,
    mode: str,
    k: int = 10,
) -> dict:
    """Evaluate a single mode's nDCG using per-pair annotation scores.

    For each query that has per-pair annotations:
    1. Extract the mode-specific ground truth score for each annotated pair
    2. Get the embedding's top-K ranking for that query
    3. Compute nDCG using the ground truth scores at the embedding's ranking positions
    """
    score_field = MODE_SCORE_FIELD[mode]
    ndcg_scores = []
    n_skipped = 0
    n_evaluated = 0

    for qname, qdata in queries.items():
        annotations = qdata.get("annotations", [])
        if not annotations:
            n_skipped += 1
            continue

        # Build ground truth: candidate -> mode-specific score
        gt = {}
        for ann in annotations:
            candidate = ann.get("candidate", "")
            score = ann.get(score_field)
            if score is not None and candidate:
                gt[candidate] = float(score)

        if not gt:
            n_skipped += 1
            continue

        # Get embedding ranking
        if qname not in wv:
            n_skipped += 1
            continue

        try:
            neighbors = wv.most_similar(qname, topn=k)
        except KeyError:
            n_skipped += 1
            continue

        # Score the embedding's ranking using ground truth
        relevances = []
        for card, _ in neighbors:
            relevances.append(gt.get(card, 0.0))

        # Ideal ranking: sort all ground truth scores descending
        ideal = sorted(gt.values(), reverse=True)

        if max(ideal[:k]) == 0:
            # No relevant docs for this mode -- skip to avoid 0/0
            n_skipped += 1
            continue

        score = ndcg(relevances, ideal, k)
        ndcg_scores.append(score)
        n_evaluated += 1

    if not ndcg_scores:
        return {
            "mode": mode,
            "score_field": score_field,
            "ndcg_at_k": 0.0,
            "n_evaluated": 0,
            "n_skipped": n_skipped,
            "k": k,
        }

    return {
        "mode": mode,
        "score_field": score_field,
        "ndcg_at_k": float(np.mean(ndcg_scores)),
        "ndcg_std": float(np.std(ndcg_scores)),
        "ndcg_median": float(np.median(ndcg_scores)),
        "n_evaluated": n_evaluated,
        "n_skipped": n_skipped,
        "k": k,
    }


def eval_upgrade_direction(queries: dict) -> dict:
    """Evaluate coverage and distribution of upgrade_direction annotations.

    Returns stats on how many pairs have upgrade labels (for contextual eval).
    """
    total = 0
    has_upgrade = 0
    directions = {}
    for qdata in queries.values():
        for ann in qdata.get("annotations", []):
            total += 1
            ud = ann.get("upgrade_direction", "")
            if ud and ud != "neither":
                has_upgrade += 1
            if ud:
                directions[ud] = directions.get(ud, 0) + 1

    return {
        "total_pairs": total,
        "with_upgrade_label": has_upgrade,
        "coverage_pct": round(100 * has_upgrade / total, 1) if total else 0,
        "distribution": directions,
    }


def eval_game(game: str, embedding_name: str | None = None, k: int = 10) -> dict:
    """Run full per-mode eval for one game."""
    test_set = load_test_set(game)
    if not test_set:
        return {"game": game, "error": "no test set"}

    queries = test_set.get("queries", {})
    wv = load_embeddings(game, embedding_name)
    if wv is None:
        return {"game": game, "error": "no embeddings"}

    emb_name = embedding_name or DEFAULT_EMBEDDINGS.get(game, "?")

    results = {
        "game": game,
        "embedding": emb_name,
        "vocab_size": len(wv),
        "total_queries": len(queries),
        "queries_with_annotations": sum(1 for q in queries.values() if q.get("annotations")),
        "k": k,
    }

    # Per-mode nDCG
    for mode in ["substitute", "synergy", "meta"]:
        results[f"mode_{mode}"] = eval_mode(wv, queries, mode, k)

    # Substitutability-weighted nDCG (uses continuous substitutability scores)
    sub_ndcg_scores = []
    for qname, qdata in queries.items():
        annotations = qdata.get("annotations", [])
        if not annotations or qname not in wv:
            continue
        gt = {}
        for ann in annotations:
            c = ann.get("candidate", "")
            s = ann.get("substitutability")
            if s is not None and c and float(s) > 0:
                gt[c] = float(s)
        if not gt:
            continue
        try:
            neighbors = wv.most_similar(qname, topn=k)
        except KeyError:
            continue
        relevances = [gt.get(card, 0.0) for card, _ in neighbors]
        ideal = sorted(gt.values(), reverse=True)
        if max(ideal[:k]) > 0:
            sub_ndcg_scores.append(ndcg(relevances, ideal, k))

    results["substitutability_ndcg"] = {
        "ndcg_at_k": float(np.mean(sub_ndcg_scores)) if sub_ndcg_scores else 0.0,
        "n_evaluated": len(sub_ndcg_scores),
        "k": k,
    }

    # Upgrade direction coverage
    results["upgrade_direction"] = eval_upgrade_direction(queries)

    # Overall nDCG (using similarity_score as ground truth)
    ndcg_scores = []
    for qname, qdata in queries.items():
        annotations = qdata.get("annotations", [])
        if not annotations or qname not in wv:
            continue
        gt = {}
        for ann in annotations:
            c = ann.get("candidate", "")
            s = ann.get("similarity_score")
            if s is not None and c:
                gt[c] = float(s)
        if not gt:
            continue
        try:
            neighbors = wv.most_similar(qname, topn=k)
        except KeyError:
            continue
        relevances = [gt.get(card, 0.0) for card, _ in neighbors]
        ideal = sorted(gt.values(), reverse=True)
        if max(ideal[:k]) > 0:
            ndcg_scores.append(ndcg(relevances, ideal, k))

    results["overall_ndcg"] = {
        "ndcg_at_k": float(np.mean(ndcg_scores)) if ndcg_scores else 0.0,
        "n_evaluated": len(ndcg_scores),
        "k": k,
    }

    return results


def main():
    parser = argparse.ArgumentParser(description="Per-mode nDCG evaluation")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--embedding", default=None, help="Embedding file name (without .wv)")
    parser.add_argument("--compare-v5", action="store_true", help="Also eval v5 embeddings")
    parser.add_argument("-k", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    all_results = []

    for game in games:
        result = eval_game(game, args.embedding, args.k)
        all_results.append(result)

        if args.compare_v5 and not args.embedding:
            v5_name = V5_EMBEDDINGS.get(game)
            if v5_name:
                v5_path = DATA_DIR / "embeddings" / f"{v5_name}.wv"
                if v5_path.exists():
                    v5_result = eval_game(game, v5_name, args.k)
                    all_results.append(v5_result)

    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        for r in all_results:
            if "error" in r:
                print(f"\n{r['game']}: {r['error']}")
                continue

            print(f"\n{'=' * 60}")
            print(f"{r['game'].upper()} ({r['embedding']}, vocab={r['vocab_size']})")
            print(
                f"  Queries: {r['total_queries']} total, {r['queries_with_annotations']} with annotations"
            )
            print(
                f"  Overall nDCG@{r['k']}: {r['overall_ndcg']['ndcg_at_k']:.4f} (n={r['overall_ndcg']['n_evaluated']})"
            )

            print(f"\n  Per-mode nDCG@{r['k']}:")
            for mode in ["substitute", "synergy", "meta"]:
                m = r[f"mode_{mode}"]
                if m["n_evaluated"] > 0:
                    print(
                        f"    {mode:12s}: {m['ndcg_at_k']:.4f} (std={m.get('ndcg_std', 0):.3f}, n={m['n_evaluated']}, skipped={m['n_skipped']})"
                    )
                else:
                    print(f"    {mode:12s}: -- (no evaluable queries)")

            sn = r.get("substitutability_ndcg", {})
            if sn.get("n_evaluated", 0) > 0:
                print(
                    f"\n  Substitutability nDCG@{r['k']}: {sn['ndcg_at_k']:.4f} (n={sn['n_evaluated']})"
                )

            ud = r["upgrade_direction"]
            print(
                f"\n  Upgrade direction: {ud['with_upgrade_label']}/{ud['total_pairs']} pairs ({ud['coverage_pct']}%)"
            )
            if ud["distribution"]:
                for d, c in sorted(ud["distribution"].items(), key=lambda x: -x[1]):
                    print(f"    {d}: {c}")


if __name__ == "__main__":
    main()
