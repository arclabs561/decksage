#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy<2.0.0"]
# ///
"""
Evaluate multi-signal fusion ranking on annotation-derived test sets.

Combines:
1. Embedding similarity (cosine, from .wv files)
2. Jaccard co-occurrence (from edgelist, shared neighbor overlap)
3. Card set membership (from card_sets JSONL, package co-membership)

Uses Reciprocal Rank Fusion (RRF) to merge ranked lists from each signal.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/evaluation/eval_fusion.py \
        --test-set data/test_set_from_annotations_yugioh.json \
        --embeddings data/embeddings/yugioh_enriched.wv \
        --edgelist data/graphs/yugioh.edg \
        --card-sets data/processed/card_sets_yugioh_top.jsonl
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors


# ── Evaluation metrics ──

RELEVANCE_GRADES = {
    "highly_relevant": 3,
    "relevant": 2,
    "somewhat_relevant": 1,
    "marginally_relevant": 0.5,
    "irrelevant": 0,
}


def dcg_at_k(scores: list[float], k: int) -> float:
    """Discounted Cumulative Gain at k."""
    return sum(s / math.log2(i + 2) for i, s in enumerate(scores[:k]))


def ndcg_at_k(relevances: list[float], k: int) -> float:
    """Normalized DCG at k."""
    dcg = dcg_at_k(relevances, k)
    ideal = dcg_at_k(sorted(relevances, reverse=True), k)
    return dcg / ideal if ideal > 0 else 0.0


def precision_at_k(relevances: list[float], k: int, threshold: float = 0.5) -> float:
    """Precision at k (binary: relevant if score >= threshold)."""
    top_k = relevances[:k]
    if not top_k:
        return 0.0
    return sum(1 for r in top_k if r >= threshold) / k


def mrr(relevances: list[float], threshold: float = 0.5) -> float:
    """Mean Reciprocal Rank."""
    for i, r in enumerate(relevances):
        if r >= threshold:
            return 1.0 / (i + 1)
    return 0.0


# ── Signal generators ──

def embedding_ranking(wv: KeyedVectors, query: str, candidates: list[str], top_k: int) -> list[tuple[str, float]]:
    """Rank candidates by cosine similarity to query in embedding space."""
    if query not in wv:
        return []
    scores = []
    for c in candidates:
        if c in wv:
            scores.append((c, float(wv.similarity(query, c))))
    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]


def jaccard_ranking(adj: dict[str, set[str]], query: str, candidates: list[str], top_k: int) -> list[tuple[str, float]]:
    """Rank candidates by Jaccard similarity of their neighbor sets."""
    q_neighbors = adj.get(query, set())
    if not q_neighbors:
        return []
    scores = []
    for c in candidates:
        c_neighbors = adj.get(c, set())
        if not c_neighbors:
            continue
        inter = len(q_neighbors & c_neighbors)
        union = len(q_neighbors | c_neighbors)
        jac = inter / union if union > 0 else 0.0
        if jac > 0:
            scores.append((c, jac))
    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]


def cardset_ranking(cs_index: dict[str, list[frozenset[str]]], query: str, candidates: list[str], top_k: int) -> list[tuple[str, float]]:
    """Rank candidates by card set co-membership with query."""
    q_sets = cs_index.get(query, [])
    if not q_sets:
        return []
    candidate_set = set(candidates)
    scores: dict[str, float] = defaultdict(float)
    for card_set in q_sets:
        for card in card_set:
            if card != query and card in candidate_set:
                # Each shared set adds weight
                scores[card] += 1.0
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return ranked[:top_k]


# ── RRF fusion ──

def rrf_fuse(ranked_lists: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion across multiple ranked lists."""
    fused: dict[str, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, (card, _) in enumerate(ranked):
            fused[card] += 1.0 / (k + rank + 1)
    return sorted(fused.items(), key=lambda x: -x[1])


# ── Data loading ──

def load_adj_sets(edgelist_path: Path) -> dict[str, set[str]]:
    """Load edgelist as adjacency sets (for Jaccard)."""
    adj: dict[str, set[str]] = defaultdict(set)
    with open(edgelist_path) as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                a, b = parts[0], parts[1]
                adj[a].add(b)
                adj[b].add(a)
    return dict(adj)


def load_card_set_index(card_set_path: Path) -> dict[str, list[frozenset[str]]]:
    """Load card sets and build reverse index: card -> list of sets containing it."""
    index: dict[str, list[frozenset[str]]] = defaultdict(list)
    with open(card_set_path) as f:
        for line in f:
            data = json.loads(line)
            if data.get("_meta"):
                continue
            cards = frozenset(data["cards"])
            for card in cards:
                index[card].append(cards)
    return dict(index)


def load_test_set(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def evaluate_ranker(
    test_set: dict,
    rank_fn,
    all_cards: list[str],
    ks: list[int] = [5, 10, 20],
) -> dict[str, float]:
    """Evaluate a ranking function on the test set."""
    queries = test_set["queries"]
    metrics: dict[str, list[float]] = {f"P@{k}": [] for k in ks}
    metrics.update({f"nDCG@{k}": [] for k in ks})
    metrics["MRR"] = []

    for query_card, grade_dict in queries.items():
        # Build relevance map
        rel_map: dict[str, float] = {}
        for grade_name, cards in grade_dict.items():
            if grade_name in RELEVANCE_GRADES:
                for card in cards:
                    rel_map[card] = max(rel_map.get(card, 0), RELEVANCE_GRADES[grade_name])

        # Get ranking
        ranked = rank_fn(query_card, all_cards, max(ks))
        if not ranked:
            continue

        # Compute relevances in ranked order
        relevances = [rel_map.get(card, 0.0) for card, _ in ranked]

        for k in ks:
            metrics[f"P@{k}"].append(precision_at_k(relevances, k))
            metrics[f"nDCG@{k}"].append(ndcg_at_k(relevances, k))
        metrics["MRR"].append(mrr(relevances))

    # Average
    return {k: np.mean(v) if v else 0.0 for k, v in metrics.items()}


def main():
    parser = argparse.ArgumentParser(description="Evaluate multi-signal fusion ranking")
    parser.add_argument("--test-set", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, nargs="+", required=True,
                        help="One or more .wv embedding files")
    parser.add_argument("--edgelist", type=Path, help="Co-occurrence edgelist for Jaccard")
    parser.add_argument("--card-sets", type=Path, help="Card sets JSONL for package co-membership")
    args = parser.parse_args()

    # Load test set
    test_set = load_test_set(args.test_set)
    queries = test_set["queries"]
    print(f"Test set: {len(queries)} queries")

    # Load embeddings
    wv_models = {}
    for p in args.embeddings:
        name = p.stem
        print(f"Loading embeddings: {name}...")
        wv_models[name] = KeyedVectors.load(str(p))

    # All cards (union of all embedding vocabs)
    all_cards = set()
    for wv in wv_models.values():
        all_cards.update(wv.key_to_index.keys())

    # Load optional signals
    adj_sets = None
    if args.edgelist and args.edgelist.exists():
        print(f"Loading co-occurrence graph: {args.edgelist}...")
        adj_sets = load_adj_sets(args.edgelist)
        for card in adj_sets:
            all_cards.add(card)
        print(f"  {len(adj_sets)} nodes")

    cs_index = None
    if args.card_sets and args.card_sets.exists():
        print(f"Loading card sets: {args.card_sets}...")
        cs_index = load_card_set_index(args.card_sets)
        print(f"  {len(cs_index)} cards indexed")

    all_cards_list = sorted(all_cards)
    print(f"Total card universe: {len(all_cards_list)}")

    # ── Evaluate individual signals ──
    # NOTE: following compare_models.py methodology -- rank only within test set
    # ground truth cards (not the full card universe). This makes results comparable.
    print("\n" + "=" * 70)
    print("SIGNAL COMPARISON (ranking within test-set candidates)")
    print("=" * 70)

    results = {}

    def eval_signal(name, rank_fn):
        """Evaluate a ranking function on test set (candidate-pool = test set cards only)."""
        ks = [5, 10, 20]
        metrics_agg: dict[str, list[float]] = {f"P@{k}": [] for k in ks}
        metrics_agg.update({f"nDCG@{k}": [] for k in ks})
        metrics_agg["MRR"] = []

        for query_card, grade_dict in queries.items():
            # Candidate pool: all cards in this query's ground truth
            candidates = []
            rel_map: dict[str, float] = {}
            for grade_name, cards in grade_dict.items():
                if grade_name in RELEVANCE_GRADES:
                    for card in cards:
                        candidates.append(card)
                        rel_map[card] = max(rel_map.get(card, 0), RELEVANCE_GRADES[grade_name])

            if not candidates:
                continue

            # Rank candidates
            ranked = rank_fn(query_card, candidates, max(ks))
            if not ranked:
                continue

            # Compute relevances in ranked order
            relevances = [rel_map.get(card, 0.0) for card, _ in ranked]

            for k in ks:
                metrics_agg[f"P@{k}"].append(precision_at_k(relevances, k))
                metrics_agg[f"nDCG@{k}"].append(ndcg_at_k(relevances, k))
            metrics_agg["MRR"].append(mrr(relevances))

        return {k: np.mean(v) if v else 0.0 for k, v in metrics_agg.items()}

    # Each embedding as standalone
    for name, wv in wv_models.items():
        print(f"\nEvaluating: {name} (embedding)...")
        results[name] = eval_signal(name, lambda q, cards, k, _wv=wv: embedding_ranking(_wv, q, cards, k))

    # Jaccard signal
    if adj_sets:
        print(f"\nEvaluating: jaccard (co-occurrence)...")
        results["jaccard"] = eval_signal("jaccard", lambda q, cards, k: jaccard_ranking(adj_sets, q, cards, k))

    # Card set signal
    if cs_index:
        print(f"\nEvaluating: card_sets (package co-membership)...")
        results["card_sets"] = eval_signal("card_sets", lambda q, cards, k: cardset_ranking(cs_index, q, cards, k))

    # ── Fusion combinations ──
    for name, wv in wv_models.items():
        signals = [("embed", lambda q, cards, k, _wv=wv: embedding_ranking(_wv, q, cards, k))]
        signal_names = [name]

        if adj_sets:
            signals.append(("jaccard", lambda q, cards, k: jaccard_ranking(adj_sets, q, cards, k)))
            signal_names.append("jaccard")

        if cs_index:
            signals.append(("cardsets", lambda q, cards, k: cardset_ranking(cs_index, q, cards, k)))
            signal_names.append("cardsets")

        if len(signals) > 1:
            fusion_name = f"RRF({'+'.join(signal_names)})"
            print(f"\nEvaluating: {fusion_name}...")
            results[fusion_name] = eval_signal(
                fusion_name,
                lambda q, cards, k, _sigs=signals: rrf_fuse(
                    [fn(q, cards, k * 5) for _, fn in _sigs]
                )[:k],
            )

    # ── Print results table ──
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    header = f"{'Model':<50} {'P@5':>6} {'nDCG@5':>8} {'P@10':>6} {'nDCG@10':>8} {'MRR':>6}"
    print(header)
    print("-" * len(header))

    # Sort by nDCG@10
    for name, res in sorted(results.items(), key=lambda x: -x[1].get("nDCG@10", 0)):
        p5 = res.get("P@5", 0)
        ndcg5 = res.get("nDCG@5", 0)
        p10 = res.get("P@10", 0)
        ndcg10 = res.get("nDCG@10", 0)
        mrr_val = res.get("MRR", 0)
        print(f"{name:<50} {p5:>6.4f} {ndcg5:>8.4f} {p10:>6.4f} {ndcg10:>8.4f} {mrr_val:>6.4f}")

    # Best
    best_name = max(results, key=lambda x: results[x].get("nDCG@10", 0))
    print(f"\nBest: {best_name} (nDCG@10={results[best_name]['nDCG@10']:.4f})")


if __name__ == "__main__":
    main()
