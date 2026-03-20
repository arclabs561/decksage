#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sentence-transformers>=2.2.0",
#     "torch>=2.0.0",
#     "peft>=0.7.0",
#     "numpy<2.0.0",
#     "datasets>=2.0.0",
#     "accelerate>=1.1.0",
# ]
# ///
"""
LoRA fine-tune E5 for TCG card similarity (per arxiv 2602.04118).

Instead of full fine-tuning (which showed marginal gains and risks
catastrophic forgetting), this uses rank-1 or rank-4 LoRA adapters
to add a thin task-specific layer while preserving E5's general
semantic ability.

Key insight from the paper: rank-1 LoRA can encode interpretable
task-specific reasoning with just 13 parameters per layer. For E5,
this means we can learn substitution/synergy signal without destroying
the base model's card text understanding.

Usage:
    uv run scripts/training/train_e5_lora.py --game magic --rank 4 --epochs 3
    uv run scripts/training/train_e5_lora.py --game magic --rank 1 --task substitution
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Mode -> annotation score field
MODE_SCORE_FIELD = {
    "substitution": "functional_score",
    "synergy": "synergy_score",
    "meta": "meta_relevance",
}

MODE_INSTRUCTION = {
    "substitution": "query: Find functional substitute for",
    "synergy": "query: Find cards that synergize with",
    "meta": "query: Find similar cards to",
}


def load_training_data(game: str, task: str) -> list[tuple[str, str, float]]:
    """Load mode-filtered training pairs with graded labels."""
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(test_path) as f:
        test_data = json.load(f)

    pairs = []
    for query_card, labels in test_data.get("queries", {}).items():
        for ann in labels.get("annotations", []):
            candidate = ann.get("candidate", "")
            mode = ann.get("mode", "unknown")
            if not candidate:
                continue

            if task == "all" or mode == task:
                score_field = MODE_SCORE_FIELD.get(mode, "similarity_score")
                score = float(ann.get(score_field, 0.0) or 0.0)
                if task == "substitution":
                    sub = float(ann.get("substitutability", 0.0) or 0.0)
                    score = max(score, sub)
                pairs.append((query_card, candidate, score))

    logger.info(f"Loaded {len(pairs)} {task} pairs for {game}")
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA fine-tune E5")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--base-model", default="intfloat/e5-base-v2")
    parser.add_argument("--rank", type=int, default=4, help="LoRA rank (1=minimal, 4=default)")
    parser.add_argument("--task", default="all", choices=["substitution", "synergy", "meta", "all"])
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    try:
        from sentence_transformers import SentenceTransformer, InputExample, losses
        from torch.utils.data import DataLoader
        from peft import LoraConfig, get_peft_model, TaskType
        import torch
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        return 1

    logger.info(f"LoRA fine-tuning E5 (rank={args.rank}, task={args.task})")
    logger.info(f"Base model: {args.base_model}")

    # Load base model
    model = SentenceTransformer(args.base_model)
    logger.info(f"Loaded base model: {args.base_model}")

    # Apply LoRA to the transformer encoder
    # E5's first module is the transformer (Transformer → Pooling → Normalize)
    transformer = model[0].auto_model

    lora_config = LoraConfig(
        task_type=TaskType.FEATURE_EXTRACTION,
        r=args.rank,
        lora_alpha=args.rank * 2,  # alpha = 2*rank is standard
        lora_dropout=0.1,
        target_modules=["query", "value"],  # LoRA on attention Q and V
    )

    peft_model = get_peft_model(transformer, lora_config)
    trainable = sum(p.numel() for p in peft_model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in peft_model.parameters())
    logger.info(f"LoRA params: {trainable:,} trainable / {total:,} total ({trainable / total:.2%})")

    # Replace the transformer with LoRA version
    model[0].auto_model = peft_model

    # Load training data
    pairs = load_training_data(args.game, args.task)
    if not pairs:
        logger.error("No training pairs found")
        return 1

    instruction = MODE_INSTRUCTION.get(args.task, "query: Find similar cards to")

    examples = []
    for query, candidate, score in pairs:
        q_text = f"{instruction} {query}"
        c_text = f"{instruction} {candidate}"
        examples.append(InputExample(texts=[q_text, c_text], label=score))

    logger.info(f"Training examples: {len(examples)}")

    dataloader = DataLoader(examples, shuffle=True, batch_size=args.batch_size)
    train_loss = losses.CosineSimilarityLoss(model)

    # Train
    logger.info("Starting LoRA fine-tuning...")
    model.fit(
        train_objectives=[(dataloader, train_loss)],
        epochs=args.epochs,
        optimizer_params={"lr": args.lr},
        warmup_steps=50,
        show_progress_bar=True,
    )

    # Save
    out_dir = DATA_DIR / "embeddings" / f"e5_lora_r{args.rank}_{args.task}_{args.game}"
    model.save(str(out_dir))
    logger.info(f"Saved to {out_dir}")

    # Quick test
    test_pairs = [
        ("Lightning Bolt", "Lava Spike"),
        ("Swords to Plowshares", "Path to Exile"),
        ("Sol Ring", "Arcane Signet"),
    ]
    logger.info("Quality check:")
    for c1, c2 in test_pairs:
        q1 = f"{instruction} {c1}"
        q2 = f"{instruction} {c2}"
        embs = model.encode([q1, q2])
        import numpy as np

        sim = float(np.dot(embs[0], embs[1]) / (np.linalg.norm(embs[0]) * np.linalg.norm(embs[1])))
        logger.info(f"  {c1} <-> {c2}: {sim:.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
