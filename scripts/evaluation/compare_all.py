#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy<2.0.0"]
# ///
"""
Evaluate ALL embeddings for a game and produce a sorted comparison table.

Auto-discovers .wv files in data/embeddings/ matching the game prefix,
evaluates nDCG@{5,10,20}, P@{5,10,20}, and MRR on the annotation test set,
and optionally runs RRF fusion with co-occurrence and card-set signals.

Ranking methodology: candidates are drawn from each query's ground-truth
pool (not the full card universe), matching eval_fusion.py.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/evaluation/compare_all.py --game yugioh
    PYTHONPATH=src .venv/bin/python scripts/evaluation/compare_all.py --game magic \
        --edgelist data/graphs/magic_blended.edg \
        --card-sets data/processed/card_sets_magic_top.jsonl
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


# ── Evaluation metrics (from eval_fusion.py) ──

RELEVANCE_GRADES = {
    "highly_relevant": 3,
    "relevant": 2,
    "somewhat_relevant": 1,
    "marginally_relevant": 0.5,
    "irrelevant": 0,
}


def dcg_at_k(scores: list[float], k: int) -> float:
    return sum(s / math.log2(i + 2) for i, s in enumerate(scores[:k]))


def ndcg_at_k(relevances: list[float], k: int) -> float:
    dcg = dcg_at_k(relevances, k)
    ideal = dcg_at_k(sorted(relevances, reverse=True), k)
    return dcg / ideal if ideal > 0 else 0.0


def precision_at_k(relevances: list[float], k: int, threshold: float = 0.5) -> float:
    top_k = relevances[:k]
    if not top_k:
        return 0.0
    return sum(1 for r in top_k if r >= threshold) / k


def mrr(relevances: list[float], threshold: float = 0.5) -> float:
    for i, r in enumerate(relevances):
        if r >= threshold:
            return 1.0 / (i + 1)
    return 0.0


# ── Ranking functions ──

def embedding_ranking(
    wv: KeyedVectors, query: str, candidates: list[str], top_k: int
) -> list[tuple[str, float]]:
    if query not in wv:
        return []
    scores = []
    for c in candidates:
        if c in wv:
            scores.append((c, float(wv.similarity(query, c))))
    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]


def jaccard_ranking(
    adj: dict[str, set[str]], query: str, candidates: list[str], top_k: int
) -> list[tuple[str, float]]:
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


def cardset_ranking(
    cs_index: dict[str, list[frozenset[str]]],
    query: str,
    candidates: list[str],
    top_k: int,
) -> list[tuple[str, float]]:
    q_sets = cs_index.get(query, [])
    if not q_sets:
        return []
    candidate_set = set(candidates)
    scores: dict[str, float] = defaultdict(float)
    for card_set in q_sets:
        for card in card_set:
            if card != query and card in candidate_set:
                scores[card] += 1.0
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return ranked[:top_k]


def rrf_fuse(
    ranked_lists: list[list[tuple[str, float]]], k: int = 60
) -> list[tuple[str, float]]:
    fused: dict[str, float] = defaultdict(float)
    for ranked in ranked_lists:
        for rank, (card, _) in enumerate(ranked):
            fused[card] += 1.0 / (k + rank + 1)
    return sorted(fused.items(), key=lambda x: -x[1])


# ── Data loading ──

def load_adj_sets(edgelist_path: Path) -> dict[str, set[str]]:
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


# ── Core evaluation ──

KS = [5, 10, 20]


def evaluate_on_test_set(
    queries: dict,
    rank_fn,
) -> dict[str, float]:
    """Evaluate a ranking function. Candidate pool = each query's ground-truth cards."""
    metrics_agg: dict[str, list[float]] = {f"P@{k}": [] for k in KS}
    metrics_agg.update({f"nDCG@{k}": [] for k in KS})
    metrics_agg["MRR"] = []

    for query_card, grade_dict in queries.items():
        candidates = []
        rel_map: dict[str, float] = {}
        for grade_name, cards in grade_dict.items():
            if grade_name not in RELEVANCE_GRADES:
                continue
            for card in cards:
                candidates.append(card)
                rel_map[card] = max(rel_map.get(card, 0), RELEVANCE_GRADES[grade_name])

        if not candidates:
            continue

        ranked = rank_fn(query_card, candidates, max(KS))
        if not ranked:
            continue

        relevances = [rel_map.get(card, 0.0) for card, _ in ranked]

        for k in KS:
            metrics_agg[f"P@{k}"].append(precision_at_k(relevances, k))
            metrics_agg[f"nDCG@{k}"].append(ndcg_at_k(relevances, k))
        metrics_agg["MRR"].append(mrr(relevances))

    return {k: float(np.mean(v)) if v else 0.0 for k, v in metrics_agg.items()}


def evaluate_per_use_case(
    queries: dict,
    rank_fn,
) -> dict[str, dict[str, float]]:
    """Evaluate grouped by use_case field, returning {use_case: metrics}."""
    by_uc: dict[str, dict] = defaultdict(dict)
    for query_card, grade_dict in queries.items():
        uc = grade_dict.get("use_case", "unknown")
        by_uc[uc][query_card] = grade_dict

    return {uc: evaluate_on_test_set(uc_queries, rank_fn) for uc, uc_queries in by_uc.items()}


# ── Discovery ──

def discover_embeddings(game: str, embeddings_dir: Path) -> list[Path]:
    """Find all .wv files whose stem starts with the game prefix."""
    found = sorted(embeddings_dir.glob(f"{game}*.wv"))
    return found


def find_test_set(game: str, data_dir: Path) -> Path:
    """Locate the test set JSON for a game."""
    # Prefer _hub variant for magic if it exists
    hub = data_dir / f"test_set_from_annotations_{game}_hub.json"
    base = data_dir / f"test_set_from_annotations_{game}.json"
    if game == "magic" and hub.exists():
        return hub
    if base.exists():
        return base
    if hub.exists():
        return hub
    print(f"ERROR: no test set found for {game} in {data_dir}", file=sys.stderr)
    sys.exit(1)


# ── Main ──

def main():
    parser = argparse.ArgumentParser(
        description="Compare all embeddings for a game on the annotation test set"
    )
    parser.add_argument(
        "--game",
        required=True,
        choices=["magic", "pokemon", "yugioh"],
        help="Which game to evaluate",
    )
    parser.add_argument(
        "--embeddings-dir",
        type=Path,
        default=Path("data/embeddings"),
        help="Directory containing .wv files (default: data/embeddings)",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=None,
        help="Override test set path (default: auto-detect)",
    )
    parser.add_argument(
        "--edgelist",
        type=Path,
        default=None,
        help="Co-occurrence edgelist for Jaccard + RRF fusion",
    )
    parser.add_argument(
        "--card-sets",
        type=Path,
        default=None,
        help="Card sets JSONL for package co-membership + RRF fusion",
    )
    parser.add_argument(
        "--per-use-case",
        action="store_true",
        help="Also report nDCG@10 broken down by use_case",
    )
    parser.add_argument(
        "--include",
        nargs="*",
        help="Only evaluate these embedding stems (substring match)",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        help="Skip these embedding stems (substring match)",
    )
    args = parser.parse_args()

    # Discover embeddings
    wv_paths = discover_embeddings(args.game, args.embeddings_dir)
    if not wv_paths:
        print(f"No .wv files found for game={args.game} in {args.embeddings_dir}", file=sys.stderr)
        sys.exit(1)

    # Apply include/exclude filters
    if args.include:
        wv_paths = [p for p in wv_paths if any(inc in p.stem for inc in args.include)]
    if args.exclude:
        wv_paths = [p for p in wv_paths if not any(exc in p.stem for exc in args.exclude)]

    if not wv_paths:
        print("No embeddings left after filtering.", file=sys.stderr)
        sys.exit(1)

    # Load test set
    test_set_path = args.test_set or find_test_set(args.game, Path("data"))
    with open(test_set_path) as f:
        test_set = json.load(f)
    queries = test_set["queries"]
    print(f"Game: {args.game}")
    print(f"Test set: {test_set_path} ({len(queries)} queries)")
    print(f"Embeddings to evaluate: {len(wv_paths)}")

    # Load optional fusion signals
    adj_sets = None
    if args.edgelist and args.edgelist.exists():
        print(f"Loading edgelist: {args.edgelist}")
        adj_sets = load_adj_sets(args.edgelist)

    cs_index = None
    if args.card_sets and args.card_sets.exists():
        print(f"Loading card sets: {args.card_sets}")
        cs_index = load_card_set_index(args.card_sets)

    # Evaluate each embedding
    results: dict[str, dict[str, float]] = {}
    uc_results: dict[str, dict[str, dict[str, float]]] = {}

    for wv_path in wv_paths:
        name = wv_path.stem
        print(f"  Loading {name}...", end="", flush=True)
        wv = KeyedVectors.load(str(wv_path))

        # Check coverage
        covered = sum(1 for q in queries if q in wv)
        print(f" ({covered}/{len(queries)} queries in vocab)", end="", flush=True)

        rank_fn = lambda q, c, k, _wv=wv: embedding_ranking(_wv, q, c, k)
        results[name] = evaluate_on_test_set(queries, rank_fn)
        print(f" nDCG@10={results[name]['nDCG@10']:.4f}")

        if args.per_use_case:
            uc_results[name] = evaluate_per_use_case(queries, rank_fn)

    # Evaluate fusion signals if available
    if adj_sets:
        name = "jaccard"
        print(f"  Evaluating {name}...", end="", flush=True)
        rank_fn = lambda q, c, k: jaccard_ranking(adj_sets, q, c, k)
        results[name] = evaluate_on_test_set(queries, rank_fn)
        print(f" nDCG@10={results[name]['nDCG@10']:.4f}")
        if args.per_use_case:
            uc_results[name] = evaluate_per_use_case(queries, rank_fn)

    if cs_index:
        name = "card_sets"
        print(f"  Evaluating {name}...", end="", flush=True)
        rank_fn = lambda q, c, k: cardset_ranking(cs_index, q, c, k)
        results[name] = evaluate_on_test_set(queries, rank_fn)
        print(f" nDCG@10={results[name]['nDCG@10']:.4f}")
        if args.per_use_case:
            uc_results[name] = evaluate_per_use_case(queries, rank_fn)

    # RRF fusion: best embedding + available signals
    if adj_sets or cs_index:
        best_emb_name = max(
            (n for n in results if n not in ("jaccard", "card_sets")),
            key=lambda n: results[n].get("nDCG@10", 0),
        )
        best_wv = KeyedVectors.load(str(args.embeddings_dir / f"{best_emb_name}.wv"))

        signals = [("embed", lambda q, c, k, _wv=best_wv: embedding_ranking(_wv, q, c, k))]
        signal_names = [best_emb_name]
        if adj_sets:
            signals.append(("jaccard", lambda q, c, k: jaccard_ranking(adj_sets, q, c, k)))
            signal_names.append("jaccard")
        if cs_index:
            signals.append(("cardsets", lambda q, c, k: cardset_ranking(cs_index, q, c, k)))
            signal_names.append("cardsets")

        fusion_name = f"RRF({'+'.join(signal_names)})"
        print(f"  Evaluating {fusion_name}...", end="", flush=True)

        def fusion_rank_fn(q, c, k, _sigs=signals):
            return rrf_fuse([fn(q, c, k * 5) for _, fn in _sigs])[:k]

        results[fusion_name] = evaluate_on_test_set(queries, fusion_rank_fn)
        print(f" nDCG@10={results[fusion_name]['nDCG@10']:.4f}")
        if args.per_use_case:
            uc_results[fusion_name] = evaluate_per_use_case(queries, fusion_rank_fn)

    # ── Print results table ──
    print()
    print("=" * 90)
    print(f"RESULTS -- {args.game} ({len(queries)} queries)")
    print("=" * 90)

    header = f"{'Model':<45} {'P@5':>6} {'nDCG@5':>8} {'P@10':>6} {'nDCG@10':>8} {'nDCG@20':>8} {'MRR':>6}"
    print(header)
    print("-" * len(header))

    for name, res in sorted(results.items(), key=lambda x: -x[1].get("nDCG@10", 0)):
        print(
            f"{name:<45} "
            f"{res.get('P@5', 0):>6.4f} "
            f"{res.get('nDCG@5', 0):>8.4f} "
            f"{res.get('P@10', 0):>6.4f} "
            f"{res.get('nDCG@10', 0):>8.4f} "
            f"{res.get('nDCG@20', 0):>8.4f} "
            f"{res.get('MRR', 0):>6.4f}"
        )

    best_name = max(results, key=lambda x: results[x].get("nDCG@10", 0))
    best_ndcg = results[best_name]["nDCG@10"]
    print(f"\nBest: {best_name} (nDCG@10={best_ndcg:.4f})")

    # Per-use-case breakdown
    if args.per_use_case and uc_results:
        use_cases = sorted({uc for ucs in uc_results.values() for uc in ucs})
        print()
        print("=" * 90)
        print("PER-USE-CASE nDCG@10")
        print("=" * 90)

        uc_header = f"{'Model':<45}" + "".join(f" {uc:>12}" for uc in use_cases)
        print(uc_header)
        print("-" * len(uc_header))

        for name, _ in sorted(results.items(), key=lambda x: -x[1].get("nDCG@10", 0)):
            if name not in uc_results:
                continue
            ucs = uc_results[name]
            row = f"{name:<45}"
            for uc in use_cases:
                val = ucs.get(uc, {}).get("nDCG@10", 0)
                row += f" {val:>12.4f}"
            print(row)


if __name__ == "__main__":
    main()
