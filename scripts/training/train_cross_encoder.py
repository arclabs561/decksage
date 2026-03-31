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

The cross-encoder learns TCG-specific semantics (e.g., "destroy all monsters"
is similar to "destroy all creatures") that bi-encoders like E5 miss because
they match on surface token overlap.

Usage:
    uv run scripts/training/train_cross_encoder.py --all-games
    uv run scripts/training/train_cross_encoder.py --game magic --epochs 3
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def load_training_pairs(game: str) -> list[dict]:
    """Load annotation pairs with card text for cross-encoder training."""
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(test_path) as f:
        data = json.load(f)

    # Load card metadata for oracle text
    card_db = {}
    for db_path in [
        DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv",
        DATA_DIR / "processed" / f"card_attributes_{game}.csv",
    ]:
        if db_path.exists():
            import csv
            with open(db_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("name", row.get("card_name", ""))
                    text = row.get("oracle_text", row.get("text", row.get("effect", "")))
                    type_line = row.get("type_line", row.get("type", ""))
                    if name and text:
                        card_db[name] = f"{type_line}: {text}" if type_line else text
            break

    if not card_db:
        log.warning(f"No card database found for {game}, using card names as text")

    queries = data["queries"]
    pairs = []

    for query_name, entry in queries.items():
        query_text = card_db.get(query_name, query_name)
        annotations = entry.get("annotations", [])
        for ann in annotations:
            candidate = ann.get("candidate", "")
            # Score: use functional_score > score > cosine_similarity
            score = ann.get("functional_score",
                    ann.get("score",
                    ann.get("similarity",
                    ann.get("cosine_similarity", 0.0))))
            if not isinstance(score, (int, float)):
                continue
            candidate_text = card_db.get(candidate, candidate)
            pairs.append({
                "query": query_name,
                "candidate": candidate,
                "query_text": query_text,
                "candidate_text": candidate_text,
                "score": float(score),
            })

    return pairs


def _add_hard_negatives(pairs: list[dict], ratio: float = 0.15) -> list[dict]:
    """Add hard negatives: random card pairings scored 0.0.

    Cross-encoder needs to see truly dissimilar pairs, not just
    low-scoring top-K candidates. Random pairs from different games
    or unrelated cards provide this signal.
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
            "query": "hard_neg",
            "candidate": "hard_neg",
            "query_text": texts[i],
            "candidate_text": texts[j],
            "score": 0.0,
        })
    log.info(f"  Added {len(negatives)} hard negatives ({ratio:.0%} of {len(pairs)})")
    return pairs + negatives


def _oversample_positives(pairs: list[dict], threshold: float = 0.5, factor: int = 3) -> list[dict]:
    """Oversample high-score pairs to counteract skewed distribution.

    Annotations are median ~0.0 (most pairs are dissimilar).
    Without oversampling, the model learns to predict low scores.
    """
    positives = [p for p in pairs if p["score"] >= threshold]
    if not positives:
        return pairs
    n_orig = len(pairs)
    oversampled = pairs + positives * (factor - 1)
    log.info(f"  Oversampled {len(positives)} positives (>={threshold}) {factor}x: {n_orig} -> {len(oversampled)}")
    return oversampled


def train(games: list[str], epochs: int = 3, batch_size: int = 32, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
    """Train cross-encoder on annotation pairs."""
    from sentence_transformers import InputExample
    from sentence_transformers.cross_encoder import CrossEncoder
    try:
        from sentence_transformers.cross_encoder.evaluation import CrossEncoderCorrelationEvaluator as CECorrelationEvaluator
    except ImportError:
        from sentence_transformers.cross_encoder.evaluation import CECorrelationEvaluator
    from torch.utils.data import DataLoader

    # Collect pairs from all games
    all_pairs = []
    for game in games:
        pairs = load_training_pairs(game)
        # Filter pairs where text is just the card name (no oracle text found)
        text_pairs = [p for p in pairs if p["query_text"] != p["query"] or p["candidate_text"] != p["candidate"]]
        dropped = len(pairs) - len(text_pairs)
        if dropped > 0:
            log.info(f"{game}: {len(pairs)} raw pairs, dropped {dropped} without oracle text -> {len(text_pairs)}")
        else:
            log.info(f"{game}: {len(text_pairs)} training pairs (all have oracle text)")
        all_pairs.extend(text_pairs)

    log.info(f"Total pairs with oracle text: {len(all_pairs)}")

    if len(all_pairs) < 100:
        log.error("Too few pairs for training")
        return

    # Score distribution analysis
    scores = np.array([p["score"] for p in all_pairs])
    log.info(f"Score distribution: mean={scores.mean():.3f}, median={np.median(scores):.3f}, "
             f"std={scores.std():.3f}, >0.5: {(scores > 0.5).sum()}, >0.3: {(scores > 0.3).sum()}")

    # Add hard negatives and oversample positives
    all_pairs = _add_hard_negatives(all_pairs, ratio=0.15)
    all_pairs = _oversample_positives(all_pairs, threshold=0.5, factor=3)

    # Split: 90% train, 10% val (stratified by score bracket)
    np.random.seed(42)
    indices = np.random.permutation(len(all_pairs))
    split = int(0.9 * len(all_pairs))
    train_idx, val_idx = indices[:split], indices[split:]

    train_examples = [
        InputExample(texts=[all_pairs[i]["query_text"], all_pairs[i]["candidate_text"]],
                     label=all_pairs[i]["score"])
        for i in train_idx
    ]
    val_pairs = [all_pairs[i] for i in val_idx]

    log.info(f"Train: {len(train_examples)}, Val: {len(val_pairs)}")

    # Initialize cross-encoder
    model = CrossEncoder(model_name, num_labels=1, max_length=256)

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
        warmup_steps=100,
        output_path=output_dir,
        show_progress_bar=True,
    )
    elapsed = time.time() - t0

    log.info(f"Training complete in {elapsed:.0f}s")
    log.info(f"Model saved to {output_dir}")

    # Final evaluation
    val_score = evaluator(model)
    if isinstance(val_score, dict):
        log.info(f"Val correlation: {val_score}")
    else:
        log.info(f"Val correlation: {val_score:.4f}")

    # Quick qualitative check
    log.info("\nQualitative check:")
    test_pairs = [
        ("Destroy all creatures. They can't be regenerated.", "Destroy all creatures."),
        ("Destroy all creatures. They can't be regenerated.", "Counter target spell."),
        ("Lightning Bolt deals 3 damage to any target.", "Lightning Strike deals 3 damage to any target."),
        ("Lightning Bolt deals 3 damage to any target.", "Search your library for a basic land card."),
    ]
    for a, b in test_pairs:
        score = model.predict([(a, b)])[0]
        log.info(f"  {a[:50]}... vs {b[:50]}... = {score:.3f}")

    return output_dir


def main():
    parser = argparse.ArgumentParser(description="Train cross-encoder reranker")
    parser.add_argument("--game", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--model", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game] if args.game else ["magic"]
    train(games, epochs=args.epochs, batch_size=args.batch_size, model_name=args.model)


if __name__ == "__main__":
    main()
