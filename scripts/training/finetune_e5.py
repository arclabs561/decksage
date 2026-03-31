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
Fine-tune E5-base-v2 on TCG card similarity pairs.

Instead of training a slow cross-encoder reranker on top of E5,
fine-tune E5 itself so the bi-encoder embeddings learn TCG semantics.
This improves ALL downstream lookups (not just reranked ones) and
runs at embedding speed (one forward pass), not cross-encoder speed
(one forward pass per candidate pair).

Uses self-supervised pairs from card attributes (no eval leakage).
Training time: ~10-20 min on MPS for 3 epochs.

Usage:
    uv run scripts/training/finetune_e5.py --all-games --epochs 3
    uv run scripts/training/finetune_e5.py --selfsupervised --epochs 2
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def load_pairs(source: str = "selfsupervised") -> list[dict]:
    """Load training pairs from specified source."""
    if source == "selfsupervised":
        ss_path = DATA_DIR / "training" / "selfsupervised_pairs.json"
        if not ss_path.exists():
            log.error(f"Self-supervised pairs not found: {ss_path}")
            log.error("Generate with: uv run scripts/training/generate_selfsupervised_pairs.py --all-games")
            return []
        with open(ss_path) as f:
            data = json.load(f)
        pairs = data.get("pairs", [])
        log.info(f"Loaded {len(pairs)} self-supervised pairs")
        return pairs
    else:
        # Load from annotations (with leakage warning)
        log.warning("Loading annotation pairs -- eval metrics will be upper bounds")
        from train_cross_encoder import load_training_pairs
        all_pairs = []
        for game in ["magic", "pokemon", "yugioh"]:
            all_pairs.extend(load_training_pairs(game))
        return all_pairs


def train(
    pairs: list[dict],
    epochs: int = 3,
    batch_size: int = 64,
    model_name: str = "intfloat/e5-base-v2",
    output_dir: str | None = None,
):
    """Fine-tune E5 bi-encoder with contrastive learning on TCG pairs."""
    from sentence_transformers import InputExample, SentenceTransformer, losses
    from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator
    from torch.utils.data import DataLoader

    log.info("=" * 60)
    log.info(f"E5 fine-tuning on {len(pairs)} pairs")
    log.info(f"Model: {model_name}, epochs: {epochs}, batch_size: {batch_size}")
    log.info("=" * 60)

    if len(pairs) < 100:
        log.error("Too few pairs")
        return

    # Query-level split
    from collections import defaultdict
    by_query = defaultdict(list)
    for i, p in enumerate(pairs):
        by_query[p["query"]].append(i)
    query_names = list(by_query.keys())
    rng = np.random.RandomState(42)
    rng.shuffle(query_names)
    split = int(len(query_names) * 0.9)
    train_queries = set(query_names[:split])

    train_idx = [i for q in train_queries for i in by_query[q]]
    val_idx = [i for q in query_names[split:] for i in by_query[q]]

    log.info(f"Query-level split: {len(train_queries)} train, {len(query_names) - split} val")
    log.info(f"Train: {len(train_idx)}, Val: {len(val_idx)}")

    # E5 requires "query: " or "passage: " prefix for instruction-tuned models
    def e5_text(text: str) -> str:
        return f"query: {text}" if not text.startswith("query:") else text

    train_examples = [
        InputExample(texts=[e5_text(pairs[i]["query_text"]), e5_text(pairs[i]["candidate_text"])],
                     label=pairs[i]["score"])
        for i in train_idx
    ]
    val_pairs = [pairs[i] for i in val_idx]

    # Score distribution
    scores = np.array([pairs[i]["score"] for i in train_idx])
    log.info(f"Train score distribution: mean={scores.mean():.3f}, median={np.median(scores):.3f}")

    # Load model
    model = SentenceTransformer(model_name)
    log.info(f"Model loaded: {model_name} ({sum(p.numel() for p in model.parameters()) / 1e6:.0f}M params)")

    # Use CosineSimilarityLoss (regression on cosine similarity)
    # This is the standard loss for similarity fine-tuning
    train_loss = losses.CosineSimilarityLoss(model)

    # Evaluator
    evaluator = EmbeddingSimilarityEvaluator(
        sentences1=[e5_text(p["query_text"]) for p in val_pairs],
        sentences2=[e5_text(p["candidate_text"]) for p in val_pairs],
        scores=[p["score"] for p in val_pairs],
        name="val",
    )

    train_dataloader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)

    if output_dir is None:
        output_dir = str(DATA_DIR / "models" / "e5_tcg_finetuned")
    os.makedirs(output_dir, exist_ok=True)

    warmup = min(100, len(train_examples) // batch_size)
    eval_steps = max(100, len(train_examples) // batch_size // 5)

    t0 = time.time()
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        evaluator=evaluator,
        epochs=epochs,
        evaluation_steps=eval_steps,
        warmup_steps=warmup,
        output_path=output_dir,
        show_progress_bar=True,
    )
    elapsed = time.time() - t0

    log.info(f"\nTraining complete in {elapsed:.0f}s")
    log.info(f"Model saved to {output_dir}")

    # Final eval
    val_result = evaluator(model, output_path=output_dir)
    log.info(f"Val similarity correlation: {val_result:.4f}")

    # Qualitative: encode pairs and check cosine
    log.info("\nQualitative check (cosine similarity):")
    test_texts = [
        ("query: Wrath of God | Sorcery | 2WW | Destroy all creatures. They can't be regenerated.",
         "query: Damnation | Sorcery | 2BB | Destroy all creatures. They can't be regenerated."),
        ("query: Wrath of God | Sorcery | 2WW | Destroy all creatures. They can't be regenerated.",
         "query: Counterspell | Instant | UU | Counter target spell."),
        ("query: Lightning Bolt | Instant | R | Lightning Bolt deals 3 damage to any target.",
         "query: Lightning Strike | Instant | 1R | Lightning Strike deals 3 damage to any target."),
        ("query: Lightning Bolt | Instant | R | Lightning Bolt deals 3 damage to any target.",
         "query: Cultivate | Sorcery | 2G | Search your library for up to two basic land cards."),
    ]
    for a, b in test_texts:
        emb_a = model.encode(a, normalize_embeddings=True)
        emb_b = model.encode(b, normalize_embeddings=True)
        cos = float(np.dot(emb_a, emb_b))
        a_short = a.split("|")[0].replace("query: ", "").strip()
        b_short = b.split("|")[0].replace("query: ", "").strip()
        log.info(f"  {a_short} vs {b_short} = {cos:.3f}")

    return output_dir


def main():
    parser = argparse.ArgumentParser(description="Fine-tune E5 on TCG card pairs")
    parser.add_argument("--source", choices=["selfsupervised", "annotations"], default="selfsupervised")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--model", default="intfloat/e5-base-v2")
    parser.add_argument("--output", default=None)
    parser.add_argument("--max-pairs", type=int, default=20000,
                        help="Subsample to N pairs (default 20K, faster training)")
    args = parser.parse_args()

    pairs = load_pairs(args.source)
    if not pairs:
        return

    # Subsample for speed (141K pairs at 2s/step = hours; 20K = ~20 min)
    if len(pairs) > args.max_pairs:
        rng = np.random.RandomState(42)
        indices = rng.choice(len(pairs), size=args.max_pairs, replace=False)
        pairs = [pairs[i] for i in indices]
        log.info(f"Subsampled to {len(pairs)} pairs for faster training")

    train(pairs, epochs=args.epochs, batch_size=args.batch_size,
          model_name=args.model, output_dir=args.output)


if __name__ == "__main__":
    main()
