#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "torch>=2.0.0",
#     "gensim>=4.3.0",
#     "numpy>=1.26.0",
#     "pydantic>=2.0",
# ]
# ///
"""
Train flow-based deck completion model.

Loads deck data from JSONL files, trains the conditional flow matching
network to complete partial decks, then evaluates on held-out test decks.

Usage:
    uv run scripts/training/train_flow_completion.py --game magic --epochs 50
    uv run scripts/training/train_flow_completion.py --game magic --evaluate-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from gensim.models import KeyedVectors


def load_decks(game: str, max_decks: int = 10000) -> list[list[str]]:
    """Load deck lists from JSONL export files."""
    jsonl_dir = DATA_DIR / "decks"
    if not jsonl_dir.exists():
        jsonl_dir = DATA_DIR / "processed"

    # Try multiple locations (game-specific deck files)
    deck_files = {
        "magic": ["decks_magic_goldfish.jsonl", "decks_magic_mtgtop8.jsonl"],
        "pokemon": ["decks_pokemon_limitless.jsonl", "decks_pokemon_limitless_expanded.jsonl"],
        "yugioh": ["decks_yugioh_masterduelmeta.jsonl"],
    }
    candidates = [DATA_DIR / "decks" / f for f in deck_files.get(game, [f"decks_{game}.jsonl"])]

    decks = []
    for path in candidates:
        if path.exists():
            print(f"Loading decks from {path}...")
            with open(path) as f:
                for i, line in enumerate(f):
                    if i >= max_decks:
                        break
                    try:
                        deck_data = json.loads(line)
                        # Extract card names from partitions format
                        cards = []
                        partitions = deck_data.get("partitions", [])
                        if not partitions and "cards" in deck_data:
                            # Flat format
                            for card in deck_data["cards"]:
                                name = (
                                    card.get("name", card) if isinstance(card, dict) else str(card)
                                )
                                count = card.get("count", 1) if isinstance(card, dict) else 1
                                cards.extend([name] * count)
                        else:
                            for part in partitions:
                                pname = part.get("name", "").lower()
                                if "side" in pname or "extra" in pname:
                                    continue
                                for card in part.get("cards", []):
                                    name = (
                                        card.get("name", card)
                                        if isinstance(card, dict)
                                        else str(card)
                                    )
                                    count = card.get("count", 1) if isinstance(card, dict) else 1
                                    cards.extend([name] * count)
                        if len(cards) >= 20:
                            decks.append(cards)
                    except (json.JSONDecodeError, KeyError):
                        continue
            break

    print(f"Loaded {len(decks)} decks")
    return decks


def evaluate_completion(
    completer,
    test_decks: list[list[str]],
    seed_fraction: float = 0.5,
) -> dict[str, float]:
    """Evaluate flow completion on held-out decks."""
    hit_at_10 = []
    hit_at_30 = []

    for deck in test_decks:
        if len(deck) < 20:
            continue

        # Split into seed and target
        n_seed = max(5, int(len(deck) * seed_fraction))
        indices = np.random.permutation(len(deck))
        seed = [deck[i] for i in indices[:n_seed]]
        target_set = {deck[i] for i in indices[n_seed:]}

        # Complete
        n_to_generate = min(len(target_set), 30)
        suggestions = completer.complete(seed, n_cards=n_to_generate)

        suggested_cards = {card for card, _ in suggestions}

        # Hit rate
        hits = len(suggested_cards & target_set)
        hit_at_10.append(hits / min(10, len(target_set)))
        hit_at_30.append(hits / min(n_to_generate, len(target_set)))

    return {
        "hit_at_10": float(np.mean(hit_at_10)) if hit_at_10 else 0.0,
        "hit_at_30": float(np.mean(hit_at_30)) if hit_at_30 else 0.0,
        "n_decks": len(hit_at_10),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train flow deck completion")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--max-decks", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--evaluate-only", action="store_true")
    args = parser.parse_args()

    # Load embeddings
    emb_map = {
        "magic": "magic_v7_spectral_mu35",
        "pokemon": "pokemon_v7_fused",
        "yugioh": "yugioh_v7_spectral_mu3",
    }
    emb_name = emb_map.get(args.game, f"{args.game}_v7_fused")
    emb_path = DATA_DIR / "embeddings" / f"{emb_name}.wv"

    print(f"Loading embeddings from {emb_path}...")
    kv = KeyedVectors.load(str(emb_path))
    print(f"  {len(kv)} cards, {kv.vector_size}D")

    # Load decks
    decks = load_decks(args.game, max_decks=args.max_decks)
    if not decks:
        print(f"No decks found for {args.game}. Check data/decks/ or data/processed/")
        return 1

    # Train/test split
    np.random.seed(42)
    n_test = max(100, int(len(decks) * 0.1))
    indices = np.random.permutation(len(decks))
    test_decks = [decks[i] for i in indices[:n_test]]
    train_decks = [decks[i] for i in indices[n_test:]]

    print(f"Split: {len(train_decks)} train, {len(test_decks)} test")

    from ml.deck_building.flow_completion import FlowCompletionConfig, FlowDeckCompleter

    config = FlowCompletionConfig(
        game=args.game,
        embed_dim=kv.vector_size,
    )

    completer = FlowDeckCompleter(kv, config)

    model_path = DATA_DIR / "models" / f"{args.game}_flow_completion.pt"

    if args.evaluate_only:
        if model_path.exists():
            completer.load(str(model_path))
        else:
            print(f"No saved model at {model_path}")
            return 1
    else:
        # Train
        print("\nTraining flow completion model...")
        t0 = time.monotonic()
        metrics = completer.train(
            train_decks,
            epochs=args.epochs,
            batch_size=args.batch_size,
            lr=args.lr,
        )
        elapsed = time.monotonic() - t0
        print(f"Training complete in {elapsed:.1f}s")
        print(f"Final loss: {metrics['loss'][-1]:.6f}")

        # Save
        model_path.parent.mkdir(parents=True, exist_ok=True)
        completer.save(str(model_path))
        print(f"Saved to {model_path}")

    # Evaluate
    print(f"\nEvaluating on {len(test_decks)} test decks...")
    eval_metrics = evaluate_completion(completer, test_decks)
    print(f"  Hit@10: {eval_metrics['hit_at_10']:.3f}")
    print(f"  Hit@30: {eval_metrics['hit_at_30']:.3f}")
    print(f"  Decks evaluated: {eval_metrics['n_decks']}")

    # Sample completion
    sample_deck = test_decks[0]
    n_seed = max(5, len(sample_deck) // 2)
    seed = sample_deck[:n_seed]
    suggestions = completer.complete(seed, n_cards=10)

    print(f"\nSample completion (seed: {n_seed} cards):")
    print(f"  Seed: {', '.join(seed[:5])}...")
    print("  Suggestions:")
    for card, score in suggestions[:10]:
        in_deck = " [IN DECK]" if card in set(sample_deck) else ""
        print(f"    {card}: {score:.3f}{in_deck}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
