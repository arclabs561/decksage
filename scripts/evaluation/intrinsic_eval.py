#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "gensim>=4.3.0",
#     "scikit-learn>=1.3.0",
# ]
# ///
"""
Intrinsic evaluation of card embeddings.

Three annotation-free metrics that measure embedding quality without
LLM-generated relevance labels:

1. Leave-one-out deck reconstruction: remove a card from a deck, check if
   the embedding retrieves it in top-K neighbors. Reports Hit@5, Hit@10, MRR.

2. Same-deck-vs-random AUC: cosine similarity between cards from the same
   deck should be higher than between random cards. Reports AUC-ROC.

3. Functional similarity test set: cosine similarity on hand-curated
   substitution pairs vs negative pairs. Reports AUC-ROC and mean sim gap.

Usage:
    uv run scripts/evaluation/intrinsic_eval.py --game magic
    uv run scripts/evaluation/intrinsic_eval.py --game magic --embedding magic_cleaned_v4
    uv run scripts/evaluation/intrinsic_eval.py --game magic --functional-only
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
DECKS_DIR = DATA_DIR / "decks"
TEST_SETS_DIR = DATA_DIR / "test_sets"

DEFAULT_EMBEDDINGS = {
    "magic": "magic_cleaned_v4",
    "pokemon": "pokemon_cleaned_v4",
    "yugioh": "yugioh_cleaned_v4",
}

# Deck files per game, ordered by preference (largest/richest first)
DECK_FILES = {
    "magic": [
        "decks_magic_goldfish.jsonl",
        "decks_magic_mtgtop8.jsonl",
        "decks_magic_commander.jsonl",
    ],
    "pokemon": [
        "decks_pokemon_limitless.jsonl",
        "decks_pokemon_limitless-web.jsonl",
    ],
    "yugioh": [
        "decks_yugioh_resolved.jsonl",
        "decks_yugioh_ygoprodeck-tournament.jsonl",
        "decks_yugioh_masterduelmeta.jsonl",
    ],
}

MAIN_PARTITIONS = {
    "magic": "Main",
    "pokemon": "Deck",
    "yugioh": "Main Deck",
}


# -- Deck loading --


def load_decks(game: str, max_decks: int = 0) -> list[list[str]]:
    """Load decks as lists of card names (main partition only, deduplicated)."""
    decks: list[list[str]] = []
    main_part = MAIN_PARTITIONS.get(game, "Main")

    for fname in DECK_FILES.get(game, []):
        path = DECKS_DIR / fname
        if not path.exists():
            continue
        with open(path) as f:
            for line in f:
                if not line.strip():
                    continue
                d = json.loads(line)
                cards_raw = d.get("cards", [])
                # Extract unique card names from main partition
                names: list[str] = []
                seen: set[str] = set()
                for c in cards_raw:
                    name = c.get("name", "")
                    part = c.get("partition", main_part)
                    if part == main_part and name and name not in seen:
                        seen.add(name)
                        names.append(name)
                if len(names) >= 5:  # skip tiny/degenerate decks
                    decks.append(names)
                if max_decks and len(decks) >= max_decks:
                    return decks
    return decks


# -- Metric 1: Leave-one-out deck reconstruction --


def leave_one_out(
    wv: KeyedVectors,
    decks: list[list[str]],
    sample_size: int = 1000,
    top_k: int = 10,
    seed: int = 42,
) -> dict:
    """Remove one card from a deck, query top-K neighbors, check if removed card is found."""
    rng = random.Random(seed)

    # Filter to decks where all cards are in vocab (at least 5 in-vocab cards)
    eligible: list[list[str]] = []
    for deck in decks:
        in_vocab = [c for c in deck if c in wv]
        if len(in_vocab) >= 5:
            eligible.append(in_vocab)

    if not eligible:
        return {"error": "no eligible decks (all cards out of vocab)"}

    sample = rng.sample(eligible, min(sample_size, len(eligible)))

    hits_at_5 = 0
    hits_at_10 = 0
    reciprocal_ranks: list[float] = []
    total = 0

    for deck in sample:
        # Pick a random card to remove
        idx = rng.randint(0, len(deck) - 1)
        removed = deck[idx]
        remaining = [c for i, c in enumerate(deck) if i != idx]

        if not remaining:
            continue

        # Compute centroid of remaining cards
        vecs = [wv[c] for c in remaining]
        centroid = np.mean(vecs, axis=0)

        # Find top-K most similar to centroid
        neighbors = wv.similar_by_vector(centroid, topn=top_k)
        neighbor_names = [name for name, _ in neighbors]

        total += 1
        if removed in neighbor_names[:5]:
            hits_at_5 += 1
        if removed in neighbor_names[:10]:
            hits_at_10 += 1

        # MRR
        if removed in neighbor_names:
            rank = neighbor_names.index(removed) + 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

    if total == 0:
        return {"error": "no valid leave-one-out trials"}

    return {
        "total_trials": total,
        "eligible_decks": len(eligible),
        "sampled_decks": len(sample),
        "hit_at_5": hits_at_5 / total,
        "hit_at_10": hits_at_10 / total,
        "mrr": float(np.mean(reciprocal_ranks)),
    }


# -- Metric 2: Same-deck vs random AUC --


def same_deck_vs_random_auc(
    wv: KeyedVectors,
    decks: list[list[str]],
    n_pairs: int = 5000,
    seed: int = 42,
) -> dict:
    """Compare cosine similarity of same-deck pairs vs random pairs."""
    rng = random.Random(seed)
    vocab = set(wv.index_to_key)

    # Build eligible decks (in-vocab cards only, at least 2)
    eligible: list[list[str]] = []
    for deck in decks:
        in_vocab = [c for c in deck if c in vocab]
        if len(in_vocab) >= 2:
            eligible.append(in_vocab)

    if len(eligible) < 10:
        return {"error": "too few eligible decks"}

    # Positive pairs: sample from same deck
    positive_sims: list[float] = []
    attempts = 0
    max_attempts = n_pairs * 10
    while len(positive_sims) < n_pairs and attempts < max_attempts:
        attempts += 1
        deck = rng.choice(eligible)
        if len(deck) < 2:
            continue
        a, b = rng.sample(deck, 2)
        sim = float(wv.similarity(a, b))
        positive_sims.append(sim)

    # Negative pairs: sample random cards from different decks
    all_cards = list(vocab)
    negative_sims: list[float] = []
    attempts = 0
    while len(negative_sims) < n_pairs and attempts < max_attempts:
        attempts += 1
        a = rng.choice(all_cards)
        b = rng.choice(all_cards)
        if a == b:
            continue
        sim = float(wv.similarity(a, b))
        negative_sims.append(sim)

    if not positive_sims or not negative_sims:
        return {"error": "could not generate enough pairs"}

    # AUC-ROC
    labels = [1] * len(positive_sims) + [0] * len(negative_sims)
    scores = positive_sims + negative_sims
    auc = roc_auc_score(labels, scores)

    pos_arr = np.array(positive_sims)
    neg_arr = np.array(negative_sims)

    return {
        "auc_roc": float(auc),
        "n_positive": len(positive_sims),
        "n_negative": len(negative_sims),
        "mean_positive_sim": float(pos_arr.mean()),
        "mean_negative_sim": float(neg_arr.mean()),
        "separation_gap": float(pos_arr.mean() - neg_arr.mean()),
        "std_positive": float(pos_arr.std()),
        "std_negative": float(neg_arr.std()),
    }


# -- Metric 3: Random-pair cosine distribution --


def random_cosine_distribution(
    wv: KeyedVectors,
    n_pairs: int = 10000,
    seed: int = 42,
) -> dict:
    """Compute distribution of cosine similarities between random card pairs."""
    rng = random.Random(seed)
    all_cards = list(wv.index_to_key)

    if len(all_cards) < 2:
        return {"error": "vocab too small"}

    sims: list[float] = []
    attempts = 0
    while len(sims) < n_pairs and attempts < n_pairs * 5:
        attempts += 1
        a = rng.choice(all_cards)
        b = rng.choice(all_cards)
        if a == b:
            continue
        sims.append(float(wv.similarity(a, b)))

    arr = np.array(sims)
    percentiles = [5, 25, 50, 75, 95]

    return {
        "n_pairs": len(sims),
        "mean": float(arr.mean()),
        "std": float(arr.std()),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "percentiles": {str(p): float(np.percentile(arr, p)) for p in percentiles},
    }


# -- Metric 4: Functional similarity test set --


def functional_similarity_eval(
    wv: KeyedVectors,
    game: str,
) -> dict | None:
    """Evaluate on hand-curated functional similarity test set."""
    test_file = TEST_SETS_DIR / f"functional_similarity_{game}.json"
    if not test_file.exists():
        return None

    with open(test_file) as f:
        data = json.load(f)

    pairs = data.get("pairs", [])
    neg_pairs = data.get("negative_pairs", [])

    relevance_weights = {
        "highly_relevant": 1.0,
        "relevant": 0.75,
        "irrelevant": 0.0,
    }

    # Positive pairs
    pos_sims: list[float] = []
    pos_details: list[dict] = []
    missing_pos = 0
    for p in pairs:
        a, b = p["card_a"], p["card_b"]
        if a not in wv or b not in wv:
            missing_pos += 1
            continue
        sim = float(wv.similarity(a, b))
        pos_sims.append(sim)
        pos_details.append(
            {
                "card_a": a,
                "card_b": b,
                "similarity": round(sim, 4),
                "relevance": p["relevance"],
                "reason": p.get("reason", ""),
            }
        )

    # Negative pairs
    neg_sims: list[float] = []
    neg_details: list[dict] = []
    missing_neg = 0
    for p in neg_pairs:
        a, b = p["card_a"], p["card_b"]
        if a not in wv or b not in wv:
            missing_neg += 1
            continue
        sim = float(wv.similarity(a, b))
        neg_sims.append(sim)
        neg_details.append(
            {
                "card_a": a,
                "card_b": b,
                "similarity": round(sim, 4),
            }
        )

    if not pos_sims or not neg_sims:
        return {
            "error": "insufficient in-vocab pairs",
            "missing_positive": missing_pos,
            "missing_negative": missing_neg,
            "total_positive": len(pairs),
            "total_negative": len(neg_pairs),
        }

    # AUC-ROC: can functional pairs be separated from negatives?
    labels = [1] * len(pos_sims) + [0] * len(neg_sims)
    scores = pos_sims + neg_sims
    auc = roc_auc_score(labels, scores)

    pos_arr = np.array(pos_sims)
    neg_arr = np.array(neg_sims)

    # Sort positive details by similarity (ascending = worst at top)
    pos_details_sorted = sorted(pos_details, key=lambda x: x["similarity"])

    return {
        "auc_roc": float(auc),
        "n_positive_evaluated": len(pos_sims),
        "n_negative_evaluated": len(neg_sims),
        "missing_positive": missing_pos,
        "missing_negative": missing_neg,
        "mean_positive_sim": float(pos_arr.mean()),
        "mean_negative_sim": float(neg_arr.mean()),
        "separation_gap": float(pos_arr.mean() - neg_arr.mean()),
        "highly_relevant_mean": float(
            np.mean([d["similarity"] for d in pos_details if d["relevance"] == "highly_relevant"])
        )
        if any(d["relevance"] == "highly_relevant" for d in pos_details)
        else None,
        "relevant_mean": float(
            np.mean([d["similarity"] for d in pos_details if d["relevance"] == "relevant"])
        )
        if any(d["relevance"] == "relevant" for d in pos_details)
        else None,
        "worst_positive_pairs": pos_details_sorted[:5],
        "best_negative_pairs": sorted(neg_details, key=lambda x: -x["similarity"])[:5],
    }


# -- Main --


def main() -> int:
    parser = argparse.ArgumentParser(description="Intrinsic evaluation of card embeddings")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument(
        "--embedding",
        default=None,
        help="Embedding name (without .wv extension). Default: {game}_cleaned_v4",
    )
    parser.add_argument("--sample-decks", type=int, default=1000, help="Decks to sample for LOO")
    parser.add_argument("--n-pairs", type=int, default=5000, help="Pairs for AUC metric")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--functional-only", action="store_true", help="Only run functional similarity eval"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    emb_name = args.embedding or DEFAULT_EMBEDDINGS[args.game]
    emb_path = EMBEDDINGS_DIR / f"{emb_name}.wv"

    if not emb_path.exists():
        print(f"Embedding not found: {emb_path}", file=sys.stderr)
        return 1

    print(f"Loading embedding: {emb_path}")
    t0 = time.time()
    wv = KeyedVectors.load(str(emb_path))
    print(f"  Loaded {len(wv)} vectors in {time.time() - t0:.1f}s")

    results: dict = {
        "game": args.game,
        "embedding": emb_name,
        "vocab_size": len(wv),
    }

    if not args.functional_only:
        # Load decks
        print(f"Loading decks for {args.game}...")
        decks = load_decks(args.game, max_decks=0)
        print(f"  Loaded {len(decks)} decks")

        # Metric 1: Leave-one-out
        print(f"Running leave-one-out (sample={args.sample_decks})...")
        t0 = time.time()
        loo = leave_one_out(wv, decks, sample_size=args.sample_decks, seed=args.seed)
        print(f"  Done in {time.time() - t0:.1f}s")
        results["leave_one_out"] = loo

        if "error" not in loo:
            print(f"  Hit@5:  {loo['hit_at_5']:.4f}")
            print(f"  Hit@10: {loo['hit_at_10']:.4f}")
            print(f"  MRR:    {loo['mrr']:.4f}")
        else:
            print(f"  ERROR: {loo['error']}")

        # Metric 2: Same-deck vs random AUC
        print(f"Running same-deck vs random AUC (n_pairs={args.n_pairs})...")
        t0 = time.time()
        auc_result = same_deck_vs_random_auc(wv, decks, n_pairs=args.n_pairs, seed=args.seed)
        print(f"  Done in {time.time() - t0:.1f}s")
        results["same_deck_vs_random"] = auc_result

        if "error" not in auc_result:
            print(f"  AUC-ROC:        {auc_result['auc_roc']:.4f}")
            print(f"  Mean pos sim:   {auc_result['mean_positive_sim']:.4f}")
            print(f"  Mean neg sim:   {auc_result['mean_negative_sim']:.4f}")
            print(f"  Separation gap: {auc_result['separation_gap']:.4f}")
        else:
            print(f"  ERROR: {auc_result['error']}")

        # Metric 3: Random cosine distribution
        print("Computing random cosine distribution...")
        t0 = time.time()
        rand_dist = random_cosine_distribution(wv, n_pairs=10000, seed=args.seed)
        print(f"  Done in {time.time() - t0:.1f}s")
        results["random_cosine_distribution"] = rand_dist

        if "error" not in rand_dist:
            print(f"  Mean: {rand_dist['mean']:.4f}  Std: {rand_dist['std']:.4f}")
            print(f"  Range: [{rand_dist['min']:.4f}, {rand_dist['max']:.4f}]")
            pct = rand_dist["percentiles"]
            print(
                f"  Percentiles: p5={pct['5']:.4f} p25={pct['25']:.4f} "
                f"p50={pct['50']:.4f} p75={pct['75']:.4f} p95={pct['95']:.4f}"
            )
        else:
            print(f"  ERROR: {rand_dist['error']}")

    # Metric 4: Functional similarity test set
    print(f"Running functional similarity eval for {args.game}...")
    t0 = time.time()
    func_result = functional_similarity_eval(wv, args.game)
    print(f"  Done in {time.time() - t0:.1f}s")

    if func_result is None:
        print(f"  No functional similarity test set for {args.game}")
        results["functional_similarity"] = {"status": "no_test_set"}
    elif "error" in func_result:
        print(f"  ERROR: {func_result['error']}")
        results["functional_similarity"] = func_result
    else:
        results["functional_similarity"] = func_result
        print(f"  AUC-ROC:        {func_result['auc_roc']:.4f}")
        print(f"  Mean pos sim:   {func_result['mean_positive_sim']:.4f}")
        print(f"  Mean neg sim:   {func_result['mean_negative_sim']:.4f}")
        print(f"  Separation gap: {func_result['separation_gap']:.4f}")
        if func_result.get("highly_relevant_mean") is not None:
            print(f"  Highly relevant mean: {func_result['highly_relevant_mean']:.4f}")
        if func_result.get("relevant_mean") is not None:
            print(f"  Relevant mean:        {func_result['relevant_mean']:.4f}")
        print(
            f"  Missing: {func_result['missing_positive']} positive, "
            f"{func_result['missing_negative']} negative"
        )
        print("  Worst positive pairs (lowest similarity):")
        for d in func_result.get("worst_positive_pairs", []):
            print(f"    {d['card_a']} <-> {d['card_b']}: {d['similarity']:.4f} ({d['reason']})")

    if args.json:
        print("\n--- JSON output ---")
        print(json.dumps(results, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
