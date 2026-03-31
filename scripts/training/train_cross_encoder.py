#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sentence-transformers>=3.0.0",
#     "torch>=2.0.0",
#     "numpy>=1.24.0",
#     "datasets>=2.0.0",
#     "accelerate>=1.1.0",
# ]
# ///
"""
Train a cross-encoder reranker on DeckSage annotation pairs.

Takes (query_card_text, candidate_card_text, similarity_score) triples from
the annotated test sets and fine-tunes a cross-encoder for pairwise scoring.

WARNING: This trains on eval annotations (annotated_*_v2.json). If deployed
as a reranker, nDCG numbers from eval_per_mode.py are upper bounds, not
generalizable metrics. This is acceptable for demonstration but not for
claiming production quality. See critique in docs/experimental_narrative.md.

Usage:
    uv run scripts/training/train_cross_encoder.py --all-games
    uv run scripts/training/train_cross_encoder.py --game magic --epochs 5
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def _load_card_db(game: str) -> dict[str, dict[str, str]]:
    """Load card metadata with structured fields for richer text representation."""
    card_db: dict[str, dict[str, str]] = {}
    for db_path in [
        DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv",
        DATA_DIR / "processed" / f"card_attributes_{game}.csv",
    ]:
        if db_path.exists():
            with open(db_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("name", row.get("card_name", ""))
                    if not name:
                        continue
                    card_db[name] = {
                        "name": name,
                        "type": row.get("type_line", row.get("type", "")),
                        "oracle_text": row.get("oracle_text", row.get("text", row.get("effect", ""))),
                        "mana_cost": row.get("mana_cost", row.get("cmc", "")),
                        "keywords": row.get("keywords", ""),
                        # Game-specific
                        "power": row.get("power", ""),
                        "toughness": row.get("toughness", ""),
                        "hp": row.get("hp", ""),
                        "attribute": row.get("attribute", ""),
                        "race": row.get("race", ""),
                    }
            break
    return card_db


def _card_to_text(name: str, card_db: dict[str, dict[str, str]]) -> str | None:
    """Build rich text representation from card metadata.

    Format: "{name} | {type} | {cost/stats} | {oracle_text}"
    Returns None if no oracle text available (caller should skip).
    """
    info = card_db.get(name)
    if not info or not info.get("oracle_text"):
        return None

    parts = [info["name"]]
    if info.get("type"):
        parts.append(info["type"])
    # Stats line
    stats = []
    if info.get("mana_cost"):
        stats.append(info["mana_cost"])
    if info.get("power") and info.get("toughness"):
        stats.append(f"{info['power']}/{info['toughness']}")
    if info.get("hp"):
        stats.append(f"HP {info['hp']}")
    if info.get("attribute"):
        stats.append(info["attribute"])
    if stats:
        parts.append(" ".join(stats))
    parts.append(info["oracle_text"])
    return " | ".join(parts)


def load_training_pairs(game: str) -> list[dict]:
    """Load annotation pairs with rich card text for cross-encoder training."""
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(test_path) as f:
        data = json.load(f)

    card_db = _load_card_db(game)
    if not card_db:
        log.warning(f"No card database found for {game}, skipping")
        return []

    queries = data["queries"]
    pairs = []
    skipped_no_text = 0

    for query_name, entry in queries.items():
        query_text = _card_to_text(query_name, card_db)
        if query_text is None:
            skipped_no_text += 1
            continue

        for ann in entry.get("annotations", []):
            candidate = ann.get("candidate", "")
            score = ann.get("functional_score",
                    ann.get("score",
                    ann.get("similarity",
                    ann.get("cosine_similarity", None))))
            if not isinstance(score, (int, float)):
                continue

            candidate_text = _card_to_text(candidate, card_db)
            if candidate_text is None:
                skipped_no_text += 1
                continue

            pairs.append({
                "query": query_name,
                "candidate": candidate,
                "query_text": query_text,
                "candidate_text": candidate_text,
                "score": float(score),
            })

    if skipped_no_text > 0:
        log.info(f"  Skipped {skipped_no_text} cards without oracle text")
    return pairs


def _add_symmetric_pairs(pairs: list[dict]) -> list[dict]:
    """Add reverse pairs (B, A, score) to enforce similarity symmetry."""
    seen = {(p["query"], p["candidate"]) for p in pairs}
    symmetric = []
    for p in pairs:
        key = (p["candidate"], p["query"])
        if key not in seen:
            symmetric.append({
                "query": p["candidate"],
                "candidate": p["query"],
                "query_text": p["candidate_text"],
                "candidate_text": p["query_text"],
                "score": p["score"],
            })
            seen.add(key)
    log.info(f"  Added {len(symmetric)} symmetric pairs ({len(pairs)} -> {len(pairs) + len(symmetric)})")
    return pairs + symmetric


def _balance_scores(pairs: list[dict], zero_ratio: float = 0.20) -> list[dict]:
    """Downsample zero-score pairs, preferring hard negatives.

    Raw annotations are 36-51% exactly 0.0. Downsample to ~20%, but
    prioritize same-type zeros (hard negatives: Creature vs Creature=0)
    over cross-type zeros (easy negatives: Creature vs Sorcery=0).
    Hard negatives provide more gradient signal because the model
    can't trivially distinguish them by type alone.
    """
    zeros = [p for p in pairs if p["score"] < 0.01]
    nonzeros = [p for p in pairs if p["score"] >= 0.01]

    if not zeros or not nonzeros:
        return pairs

    target_zeros = int(len(nonzeros) * zero_ratio / (1.0 - zero_ratio))
    if target_zeros >= len(zeros):
        return pairs

    # Classify zeros as hard (same base type) or easy (different type)
    hard_zeros = []
    easy_zeros = []
    for p in zeros:
        q_type = p["query_text"].split("|")[1].strip().split(" — ")[0].strip() if "|" in p["query_text"] else ""
        c_type = p["candidate_text"].split("|")[1].strip().split(" — ")[0].strip() if "|" in p["candidate_text"] else ""
        if q_type and c_type and q_type == c_type:
            hard_zeros.append(p)
        else:
            easy_zeros.append(p)

    rng = np.random.RandomState(42)
    # Take all hard negatives first, fill remainder with easy ones
    if len(hard_zeros) >= target_zeros:
        sampled = [hard_zeros[i] for i in rng.choice(len(hard_zeros), size=target_zeros, replace=False)]
    else:
        remainder = target_zeros - len(hard_zeros)
        easy_sample = [easy_zeros[i] for i in rng.choice(len(easy_zeros), size=min(remainder, len(easy_zeros)), replace=False)]
        sampled = hard_zeros + easy_sample

    log.info(f"  Downsampled zeros: {len(zeros)} -> {len(sampled)} "
             f"(hard: {min(len(hard_zeros), target_zeros)}, easy: {len(sampled) - min(len(hard_zeros), target_zeros)})")
    return nonzeros + sampled


def _add_hard_negatives(pairs: list[dict], ratio: float = 0.10) -> list[dict]:
    """Add hard negatives: random card pairings scored 0.0.

    Random pairs provide signal for truly dissimilar cards that
    wouldn't appear in top-K candidate lists.
    """
    texts = list({p["query_text"] for p in pairs} | {p["candidate_text"] for p in pairs})
    if len(texts) < 10:
        return pairs

    n_neg = int(len(pairs) * ratio)
    rng = np.random.RandomState(123)
    negatives = []
    for _ in range(n_neg):
        i, j = rng.choice(len(texts), size=2, replace=False)
        negatives.append({
            "query": "_hard_neg",
            "candidate": "_hard_neg",
            "query_text": texts[i],
            "candidate_text": texts[j],
            "score": 0.0,
        })
    log.info(f"  Added {len(negatives)} hard negatives ({ratio:.0%})")
    return pairs + negatives


def _query_level_split(pairs: list[dict], val_ratio: float = 0.10):
    """Split by query card, not by pair.

    All pairs for a given query go into either train or val.
    This tests whether the model generalizes to unseen cards,
    not just unseen pairs of seen cards.
    """
    # Group pairs by query card
    by_query: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(pairs):
        by_query[p["query"]].append(i)

    query_names = list(by_query.keys())
    rng = np.random.RandomState(42)
    rng.shuffle(query_names)

    # Split queries
    split = int(len(query_names) * (1.0 - val_ratio))
    train_queries = set(query_names[:split])

    train_idx = []
    val_idx = []
    for q, indices in by_query.items():
        if q in train_queries:
            train_idx.extend(indices)
        else:
            val_idx.extend(indices)

    log.info(f"  Query-level split: {len(train_queries)} train queries, "
             f"{len(query_names) - len(train_queries)} val queries")
    return train_idx, val_idx


def train(
    games: list[str],
    epochs: int = 3,
    batch_size: int = 32,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
    max_length: int = 384,
):
    """Train cross-encoder on annotation pairs."""
    from sentence_transformers import InputExample
    from sentence_transformers.cross_encoder import CrossEncoder
    try:
        from sentence_transformers.cross_encoder.evaluation import CrossEncoderCorrelationEvaluator as CECorrelationEvaluator
    except ImportError:
        from sentence_transformers.cross_encoder.evaluation import CECorrelationEvaluator
    from torch.utils.data import DataLoader

    log.info("=" * 60)
    log.info("Cross-encoder training (v3)")
    log.info(f"Model: {model_name}, max_length: {max_length}")
    log.info(f"NOTE: Training on eval annotations -- metrics are upper bounds")
    log.info("=" * 60)

    # Collect pairs from all games
    all_pairs = []
    for game in games:
        pairs = load_training_pairs(game)
        log.info(f"{game}: {len(pairs)} pairs with oracle text")
        all_pairs.extend(pairs)

    log.info(f"\nTotal raw pairs: {len(all_pairs)}")

    if len(all_pairs) < 100:
        log.error("Too few pairs for training")
        return

    # Score distribution before processing
    scores = np.array([p["score"] for p in all_pairs])
    log.info(f"Raw score distribution: mean={scores.mean():.3f}, median={np.median(scores):.3f}, "
             f"std={scores.std():.3f}")
    brackets = [(0, 0.01), (0.01, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.01)]
    for lo, hi in brackets:
        n = int(((scores >= lo) & (scores < hi)).sum())
        log.info(f"  [{lo:.2f}, {hi:.2f}): {n} ({n/len(scores)*100:.1f}%)")

    # Processing pipeline
    log.info("\nProcessing pipeline:")
    all_pairs = _add_symmetric_pairs(all_pairs)
    all_pairs = _balance_scores(all_pairs, zero_ratio=0.20)
    all_pairs = _add_hard_negatives(all_pairs, ratio=0.10)

    # Post-processing distribution
    scores = np.array([p["score"] for p in all_pairs])
    log.info(f"\nProcessed: {len(all_pairs)} pairs, mean={scores.mean():.3f}, "
             f"median={np.median(scores):.3f}")

    # Query-level split
    log.info("\nSplitting:")
    train_idx, val_idx = _query_level_split(all_pairs, val_ratio=0.10)

    train_examples = [
        InputExample(texts=[all_pairs[i]["query_text"], all_pairs[i]["candidate_text"]],
                     label=all_pairs[i]["score"])
        for i in train_idx
    ]
    val_pairs = [all_pairs[i] for i in val_idx]

    # Val score distribution
    val_scores = np.array([p["score"] for p in val_pairs])
    log.info(f"  Train: {len(train_examples)}, Val: {len(val_pairs)}")
    log.info(f"  Val score distribution: mean={val_scores.mean():.3f}, "
             f">0.5: {(val_scores > 0.5).sum()}, =0: {(val_scores == 0).sum()}")

    # Initialize cross-encoder
    model = CrossEncoder(model_name, num_labels=1, max_length=max_length)

    # Evaluator
    evaluator = CECorrelationEvaluator(
        sentence_pairs=[[p["query_text"], p["candidate_text"]] for p in val_pairs],
        scores=[p["score"] for p in val_pairs],
        name="val",
    )

    # Train
    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)
    output_dir = str(DATA_DIR / "models" / "cross_encoder_reranker")
    os.makedirs(output_dir, exist_ok=True)

    t0 = time.time()
    model.fit(
        train_dataloader=train_dataloader,
        evaluator=evaluator,
        epochs=epochs,
        evaluation_steps=500,
        warmup_steps=min(200, len(train_examples) // batch_size),
        output_path=output_dir,
        show_progress_bar=True,
    )
    elapsed = time.time() - t0

    log.info(f"\nTraining complete in {elapsed:.0f}s")
    log.info(f"Model saved to {output_dir}")

    # Final evaluation
    val_result = evaluator(model)
    if isinstance(val_result, dict):
        log.info(f"Val correlation: Pearson={val_result.get('pearson', '?')}, "
                 f"Spearman={val_result.get('spearman', '?')}")
    else:
        log.info(f"Val correlation: {val_result}")

    # Ranking evaluation: per-query nDCG on val set
    log.info("\nRanking evaluation (per-query nDCG on val):")
    _eval_ranking(model, val_pairs)

    # Qualitative check
    log.info("\nQualitative check:")
    test_pairs = [
        ("Wrath of God | Sorcery | 2WW | Destroy all creatures. They can't be regenerated.",
         "Damnation | Sorcery | 2BB | Destroy all creatures. They can't be regenerated."),
        ("Wrath of God | Sorcery | 2WW | Destroy all creatures. They can't be regenerated.",
         "Counterspell | Instant | UU | Counter target spell."),
        ("Lightning Bolt | Instant | R | Lightning Bolt deals 3 damage to any target.",
         "Lightning Strike | Instant | 1R | Lightning Strike deals 3 damage to any target."),
        ("Lightning Bolt | Instant | R | Lightning Bolt deals 3 damage to any target.",
         "Cultivate | Sorcery | 2G | Search your library for up to two basic land cards."),
    ]
    for a, b in test_pairs:
        score = model.predict([(a, b)])[0]
        a_short = a.split("|")[0].strip()
        b_short = b.split("|")[0].strip()
        log.info(f"  {a_short} vs {b_short} = {score:.3f}")

    return output_dir


def _eval_ranking(model, val_pairs: list[dict]) -> None:
    """Compute per-query nDCG on validation set using cross-encoder scores."""
    # Group val pairs by query
    by_query: dict[str, list[dict]] = defaultdict(list)
    for p in val_pairs:
        by_query[p["query"]].append(p)

    ndcgs = []
    for query, pairs in by_query.items():
        if len(pairs) < 2:
            continue
        # Get cross-encoder predictions
        inputs = [(p["query_text"], p["candidate_text"]) for p in pairs]
        preds = model.predict(inputs)
        # Sort by predicted score descending
        ranked = sorted(zip(preds, pairs), key=lambda x: -x[0])
        # Compute DCG with annotation scores as relevance
        dcg = sum(p["score"] / np.log2(i + 2) for i, (_, p) in enumerate(ranked))
        # Ideal: sort by annotation score
        ideal = sorted([p["score"] for p in pairs], reverse=True)
        idcg = sum(s / np.log2(i + 2) for i, s in enumerate(ideal))
        if idcg > 0:
            ndcgs.append(dcg / idcg)

    if ndcgs:
        arr = np.array(ndcgs)
        log.info(f"  Queries evaluated: {len(ndcgs)}")
        log.info(f"  nDCG: mean={arr.mean():.4f}, median={np.median(arr):.4f}, "
                 f"std={arr.std():.4f}")
        log.info(f"  nDCG quartiles: Q1={np.percentile(arr, 25):.4f}, "
                 f"Q3={np.percentile(arr, 75):.4f}")
    else:
        log.info("  No queries with 2+ candidates in val set")


def main():
    parser = argparse.ArgumentParser(description="Train cross-encoder reranker")
    parser.add_argument("--game", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=384)
    parser.add_argument("--model", default="cross-encoder/ms-marco-MiniLM-L-12-v2",
                        help="Base model (default: L-12 for deeper capacity)")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game] if args.game else ["magic"]
    train(games, epochs=args.epochs, batch_size=args.batch_size,
          model_name=args.model, max_length=args.max_length)


if __name__ == "__main__":
    main()
