#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#     "sentence-transformers>=2.2.0",
#     "torch>=2.0.0",
#     "numpy>=1.26.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Self-supervised contrastive fine-tuning of E5 for card substitution.

Uses deck co-occurrence as positive pairs (cards in the same deck serve
related functions) and random cards as negatives. NO annotation data
used for training -- annotations are evaluation-only.

This is SimCSE-style contrastive learning: the model learns to place
co-occurring cards closer together in text embedding space.

Usage:
    uv run scripts/training/train_simcse_e5.py --game magic --epochs 3
    uv run scripts/training/train_simcse_e5.py --game magic --epochs 1 --dry-run
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_card_texts(game: str) -> dict[str, str]:
    """Load card name -> oracle text mapping from Scryfall data."""
    # Try processed card attributes first
    attrs_path = DATA_DIR / "processed" / f"card_attributes_{game}.csv"
    if attrs_path.exists():
        import csv
        cards = {}
        with open(attrs_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("name", "")
                text = row.get("oracle_text", row.get("text", ""))
                type_line = row.get("type_line", "")
                mana_cost = row.get("mana_cost", "")
                if name:
                    # Combine all card text into a single description
                    desc = f"{type_line}. {mana_cost}. {text}".strip()
                    cards[name] = desc if desc != ". ." else name
        print(f"  Loaded {len(cards):,} card texts from {attrs_path.name}")
        return cards

    print(f"  WARNING: No card attributes found at {attrs_path}")
    return {}


def load_deck_pairs(game: str, max_pairs: int = 100000) -> list[tuple[str, str]]:
    """Load positive pairs from deck co-occurrence (self-supervised)."""
    deck_dir = DATA_DIR / "decks"
    pairs = []
    seen = set()

    basics = {"Plains", "Island", "Swamp", "Mountain", "Forest",
              "Snow-Covered Plains", "Snow-Covered Island",
              "Snow-Covered Swamp", "Snow-Covered Mountain",
              "Snow-Covered Forest", "Wastes"}

    for f in sorted(deck_dir.glob(f"decks_{game}_*.jsonl")):
        with open(f) as fh:
            for line in fh:
                if len(pairs) >= max_pairs:
                    break
                try:
                    deck = json.loads(line)
                except json.JSONDecodeError:
                    continue

                cards = set()
                if "cards" in deck:
                    for card in deck["cards"]:
                        name = card.get("name", "") if isinstance(card, dict) else str(card)
                        if name:
                            cards.add(name)
                if "partitions" in deck:
                    for part in deck["partitions"]:
                        for card in part.get("cards", []):
                            name = card.get("name", "") if isinstance(card, dict) else str(card)
                            if name:
                                cards.add(name)

                cards -= basics
                card_list = sorted(cards)
                if len(card_list) < 10:
                    continue

                # Sample pairs from this deck (not all O(n^2))
                rng = random.Random(hash(deck.get("deck_id", "")))
                n_samples = min(10, len(card_list))
                for _ in range(n_samples):
                    a, b = rng.sample(card_list, 2)
                    key = (min(a, b), max(a, b))
                    if key not in seen:
                        seen.add(key)
                        pairs.append((a, b))

        if len(pairs) >= max_pairs:
            break

    print(f"  {len(pairs):,} co-occurrence pairs from deck data")
    return pairs


class PairDataset(Dataset):
    def __init__(self, pairs, card_texts, all_cards):
        self.pairs = pairs
        self.card_texts = card_texts
        self.all_cards = all_cards

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        a, b = self.pairs[idx]
        text_a = self.card_texts.get(a, a)
        text_b = self.card_texts.get(b, b)
        # Negative: random card
        neg = random.choice(self.all_cards)
        while neg in (a, b):
            neg = random.choice(self.all_cards)
        text_neg = self.card_texts.get(neg, neg)
        return text_a, text_b, text_neg


def main() -> int:
    parser = argparse.ArgumentParser(description="SimCSE contrastive E5 fine-tuning")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--model", default="intfloat/e5-base-v2")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-pairs", type=int, default=50000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"SimCSE E5 Fine-tuning [{args.game}]")
    print(f"  model: {args.model}")
    print(f"  epochs: {args.epochs}, lr: {args.lr}")
    print(f"{'=' * 60}")

    # Load data
    print(f"\n[1/4] Loading card texts...")
    card_texts = load_card_texts(args.game)
    if not card_texts:
        print("  No card texts available. Cannot fine-tune text model.")
        return 1

    print(f"\n[2/4] Loading deck pairs (self-supervised)...")
    pairs = load_deck_pairs(args.game, max_pairs=args.max_pairs)
    if len(pairs) < 100:
        print(f"  Too few pairs ({len(pairs)}). Need at least 100.")
        return 1

    # Filter to cards with text
    pairs = [(a, b) for a, b in pairs if a in card_texts and b in card_texts]
    print(f"  {len(pairs):,} pairs with text (after filtering)")

    all_cards = list(card_texts.keys())

    if args.dry_run:
        print(f"\n  Dry run -- would train on {len(pairs):,} pairs")
        print(f"  Sample: {pairs[:3]}")
        return 0

    # Load model
    print(f"\n[3/4] Loading model...")
    from sentence_transformers import SentenceTransformer, losses, InputExample
    from torch.utils.data import DataLoader as STDataLoader

    model = SentenceTransformer(args.model)
    print(f"  Model loaded: {args.model}")

    # Build training examples (anchor, positive, negative)
    train_examples = []
    for a, b in pairs:
        neg = random.choice(all_cards)
        while neg in (a, b):
            neg = random.choice(all_cards)
        train_examples.append(InputExample(
            texts=[card_texts[a], card_texts[b], card_texts[neg]]
        ))

    train_dataloader = STDataLoader(train_examples, shuffle=True, batch_size=args.batch_size)
    train_loss = losses.TripletLoss(model=model)

    # Train
    print(f"\n[4/4] Training ({len(train_examples):,} examples, {args.epochs} epochs)...")
    t0 = time.monotonic()

    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=args.epochs,
        warmup_steps=int(len(train_dataloader) * 0.1),
        show_progress_bar=True,
    )

    elapsed = time.monotonic() - t0
    print(f"\n  Training complete in {elapsed:.1f}s")

    # Save embeddings for all cards
    print(f"\n  Encoding all cards...")
    all_names = list(card_texts.keys())
    all_texts = [card_texts[n] for n in all_names]
    embeddings = model.encode(all_texts, batch_size=64, show_progress_bar=True,
                              normalize_embeddings=True)

    from gensim.models import KeyedVectors
    kv = KeyedVectors(vector_size=embeddings.shape[1])
    kv.add_vectors(all_names, embeddings.astype(np.float32))

    out_path = DATA_DIR / "embeddings" / f"{args.game}_simcse_e5.wv"
    kv.save(str(out_path))
    print(f"  Saved {len(kv):,} embeddings to {out_path}")

    # Quality pairs
    sys.path.insert(0, str(Path(__file__).parent))
    from edge_registry import QUALITY_PAIRS
    for c1, c2 in QUALITY_PAIRS.get(args.game, []):
        if c1 in kv and c2 in kv:
            sim = float(kv.similarity(c1, c2))
            print(f"    {c1} <-> {c2}: {sim:.4f}")

    # Run summary
    logs_dir = DATA_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    import subprocess
    git_sha = "unknown"
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5, cwd=str(PROJECT_ROOT))
        if r.returncode == 0:
            git_sha = r.stdout.strip()
    except FileNotFoundError:
        pass

    summary = {
        "game": args.game, "model": "simcse_e5",
        "git_sha": git_sha,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "params": {"base_model": args.model, "epochs": args.epochs, "lr": args.lr,
                   "batch_size": args.batch_size, "max_pairs": args.max_pairs},
        "data": {"num_cards": len(all_names), "num_pairs": len(pairs),
                 "source": "deck co-occurrence (self-supervised, no annotations)"},
        "training": {"duration_s": round(elapsed, 1)},
        "artifacts": {"embeddings": str(out_path)},
    }
    summary_path = logs_dir / f"{args.game}_simcse_e5_run.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Run summary: {summary_path}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
