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


def normalize_scores_per_model(queries: dict) -> dict:
    """Normalize annotation scores per LLM model to fix calibration drift.

    Different models give different score ranges (GPT-4o-mini avg 0.52 vs
    Gemini 0.25). This normalizes each model's scores to mean=0.5
    using z-score normalization, so multi-model annotations are comparable.
    """
    # Collect scores per model
    model_scores: dict[str, list[float]] = {}
    for qdata in queries.values():
        for ann in qdata.get("annotations", []):
            model = ann.get("llm_model", "unknown")
            sim = ann.get("similarity_score")
            if sim is not None:
                model_scores.setdefault(model, []).append(float(sim))

    # Compute per-model mean/std
    model_stats = {}
    for model, scores in model_scores.items():
        arr = np.array(scores)
        model_stats[model] = {"mean": float(arr.mean()), "std": float(arr.std())}

    # Only normalize if we have multiple models with different means
    means = [s["mean"] for s in model_stats.values()]
    if len(means) < 2 or max(means) - min(means) < 0.1:
        return queries  # No significant drift

    # Normalize: z-score -> rescale to [0, 1] range centered at 0.5
    for qdata in queries.values():
        for ann in qdata.get("annotations", []):
            model = ann.get("llm_model", "unknown")
            stats = model_stats.get(model)
            if not stats or stats["std"] < 0.01:
                continue
            for field in [
                "similarity_score",
                "functional_score",
                "synergy_score",
                "meta_relevance",
            ]:
                val = ann.get(field)
                if val is not None:
                    z = (float(val) - stats["mean"]) / stats["std"]
                    # Rescale z-score to 0-1 (clip to avoid negatives)
                    normalized = max(0.0, min(1.0, 0.5 + z * 0.2))
                    ann[f"{field}_normalized"] = round(normalized, 4)

    return queries


def eval_mode(
    wv: KeyedVectors,
    queries: dict,
    mode: str,
    k: int = 10,
    use_normalized: bool = False,
) -> dict:
    """Evaluate a single mode's nDCG using per-pair annotation scores.

    For each query that has per-pair annotations:
    1. Extract the mode-specific ground truth score for each annotated pair
    2. Get the embedding's top-K ranking for that query
    3. Compute nDCG using the ground truth scores at the embedding's ranking positions
    """
    base_field = MODE_SCORE_FIELD[mode]
    score_field = f"{base_field}_normalized" if use_normalized else base_field
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

    # Normalize scores across models for fair comparison
    queries = normalize_scores_per_model(queries)

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

    # Stratified nDCG by card popularity (experiment 0019 recommendation)
    # Use embedding neighbor count as popularity proxy: popular cards appear
    # as top-10 neighbors of many other cards. Computed efficiently by sampling.
    neighbor_count: dict[str, int] = {}
    sample_keys = list(wv.key_to_index.keys())
    rng = np.random.default_rng(42)
    sample_size = min(2000, len(sample_keys))
    sampled = rng.choice(sample_keys, size=sample_size, replace=False)
    for card in sampled:
        try:
            neighbors = wv.most_similar(card, topn=10)
            for n, _ in neighbors:
                neighbor_count[n] = neighbor_count.get(n, 0) + 1
        except KeyError:
            continue

    query_popularity: dict[str, int] = {}
    for qname in queries:
        if qname in neighbor_count:
            query_popularity[qname] = neighbor_count[qname]
        else:
            query_popularity[qname] = 0

    if query_popularity:
        median_pop = float(np.median(list(query_popularity.values())))
        pop_ndcg = []
        niche_ndcg = []
        for qname, qdata in queries.items():
            if qname not in wv or qname not in query_popularity:
                continue
            annotations = qdata.get("annotations", [])
            if not annotations:
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
                score = ndcg(relevances, ideal, k)
                if query_popularity[qname] > median_pop:
                    pop_ndcg.append(score)
                else:
                    niche_ndcg.append(score)

        results["stratified_ndcg"] = {
            "popular_ndcg": float(np.mean(pop_ndcg)) if pop_ndcg else 0.0,
            "popular_n": len(pop_ndcg),
            "niche_ndcg": float(np.mean(niche_ndcg)) if niche_ndcg else 0.0,
            "niche_n": len(niche_ndcg),
            "median_popularity": median_pop,
            "bias_ratio": (float(np.mean(pop_ndcg)) / float(np.mean(niche_ndcg)))
            if niche_ndcg and pop_ndcg and np.mean(niche_ndcg) > 0
            else 0.0,
        }

    # Beyond-accuracy metrics (from experiment 0019 metrics audit)

    # Catalog Coverage: fraction of vocabulary ever recommended across all queries
    all_recommended: set[str] = set()
    for qname in queries:
        if qname not in wv:
            continue
        try:
            neighbors = wv.most_similar(qname, topn=k)
            all_recommended.update(card for card, _ in neighbors)
        except KeyError:
            continue
    catalog_size = len(wv)
    results["catalog_coverage"] = {
        "recommended_cards": len(all_recommended),
        "catalog_size": catalog_size,
        "coverage": len(all_recommended) / catalog_size if catalog_size > 0 else 0.0,
    }

    # Novelty: mean self-information of recommended cards
    # Uses embedding vocabulary frequency as proxy for popularity
    # (cards that appear as neighbors of many queries are "popular")
    neighbor_freq: dict[str, int] = {}
    n_queries_with_neighbors = 0
    for qname in queries:
        if qname not in wv:
            continue
        try:
            neighbors = wv.most_similar(qname, topn=k)
            n_queries_with_neighbors += 1
            for card, _ in neighbors:
                neighbor_freq[card] = neighbor_freq.get(card, 0) + 1
        except KeyError:
            continue

    if n_queries_with_neighbors > 0 and neighbor_freq:
        novelty_scores = []
        for qname in queries:
            if qname not in wv:
                continue
            try:
                neighbors = wv.most_similar(qname, topn=k)
            except KeyError:
                continue
            q_novelty = []
            for card, _ in neighbors:
                pop = neighbor_freq.get(card, 1) / n_queries_with_neighbors
                q_novelty.append(-np.log2(max(pop, 1e-10)))
            if q_novelty:
                novelty_scores.append(float(np.mean(q_novelty)))
        results["novelty"] = {
            "mean_self_info": float(np.mean(novelty_scores)) if novelty_scores else 0.0,
            "n_evaluated": len(novelty_scores),
        }
    else:
        results["novelty"] = {"mean_self_info": 0.0, "n_evaluated": 0}

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

            strat = r.get("stratified_ndcg", {})
            if strat:
                bias = strat.get("bias_ratio", 0)
                print(
                    f"\n  Stratified nDCG (popularity bias check):"
                    f"\n    Popular cards:  {strat['popular_ndcg']:.4f} (n={strat['popular_n']})"
                    f"\n    Niche cards:    {strat['niche_ndcg']:.4f} (n={strat['niche_n']})"
                    f"\n    Bias ratio:     {bias:.2f}x"
                    f" {'(OK)' if bias < 2.0 else '(BIASED - popular cards get disproportionate nDCG)'}"
                )

            cc = r.get("catalog_coverage", {})
            if cc:
                print(
                    f"\n  Catalog coverage: {cc['recommended_cards']}/{cc['catalog_size']} "
                    f"({cc['coverage']:.1%})"
                )

            nov = r.get("novelty", {})
            if nov.get("n_evaluated", 0) > 0:
                print(f"  Novelty (mean self-info): {nov['mean_self_info']:.2f} bits")


if __name__ == "__main__":
    main()
