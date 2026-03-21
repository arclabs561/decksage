#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "subsumer>=0.7.0",
#     "numpy>=1.24.0",
# ]
# ///
"""
Train box embeddings for deck-contains-card containment.

Converts deck JSONL files into (deck_id, "contains", card_id) triples
and trains box embeddings via subsumer. Evaluates held-out containment
probability vs random cards.

Usage:
    uv run scripts/training/train_box_containment.py --game magic --dim 32 --epochs 100
    uv run scripts/training/train_box_containment.py --game magic --dry-run
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_decks(game: str, min_cards: int = 20, max_decks: int = 50000) -> list[dict]:
    """Load deck JSONL files for a game."""
    deck_dir = DATA_DIR / "decks"
    decks = []

    patterns = [f"decks_{game}_*.jsonl"]
    if game == "magic":
        patterns.append("decks_magic_*.jsonl")

    seen_ids = set()
    for pattern in patterns:
        for f in sorted(deck_dir.glob(pattern)):
            with open(f) as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        deck = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    deck_id = deck.get("deck_id", deck.get("id", ""))
                    if deck_id in seen_ids:
                        continue
                    seen_ids.add(deck_id)

                    # Extract card names
                    cards = []
                    if "cards" in deck:
                        for card in deck["cards"]:
                            if isinstance(card, dict):
                                name = card.get("name", "")
                            else:
                                name = str(card)
                            if name:
                                cards.append(name)
                    if "partitions" in deck:
                        for part in deck["partitions"]:
                            for card in part.get("cards", []):
                                if isinstance(card, dict):
                                    name = card.get("name", "")
                                else:
                                    name = str(card)
                                if name:
                                    cards.append(name)

                    if len(cards) >= min_cards:
                        decks.append({"id": deck_id, "cards": list(set(cards))})

                    if len(decks) >= max_decks:
                        break
            if len(decks) >= max_decks:
                break

    return decks


def build_triples(
    decks: list[dict],
    holdout_ratio: float = 0.2,
    seed: int = 42,
) -> tuple[list[tuple[int, int, int]], list[tuple[int, int, int]], dict[int, str], dict[int, str]]:
    """Build (deck_id, relation_id=0, card_id) triples with train/val split.

    Returns: (train_triples, val_triples, id_to_deck, id_to_card)
    """
    rng = random.Random(seed)

    # Intern all entity IDs: decks get IDs first, then cards
    card_to_id: dict[str, int] = {}
    deck_to_id: dict[str, int] = {}
    next_id = 0

    # Assign deck IDs
    for deck in decks:
        if deck["id"] not in deck_to_id:
            deck_to_id[deck["id"]] = next_id
            next_id += 1

    # Assign card IDs
    for deck in decks:
        for card in deck["cards"]:
            if card not in card_to_id:
                card_to_id[card] = next_id
                next_id += 1

    # Build triples with holdout
    train_triples = []
    val_triples = []

    for deck in decks:
        did = deck_to_id[deck["id"]]
        cards = deck["cards"][:]
        rng.shuffle(cards)

        n_holdout = max(1, int(len(cards) * holdout_ratio))
        holdout = cards[:n_holdout]
        train_cards = cards[n_holdout:]

        for card in train_cards:
            cid = card_to_id[card]
            train_triples.append((did, 0, cid))

        for card in holdout:
            cid = card_to_id[card]
            val_triples.append((did, 0, cid))

    id_to_deck = {v: k for k, v in deck_to_id.items()}
    id_to_card = {v: k for k, v in card_to_id.items()}

    return train_triples, val_triples, id_to_deck, id_to_card


def evaluate(
    trainer,
    val_triples: list[tuple[int, int, int]],
    all_card_ids: list[int],
    n_random: int = 5,
    seed: int = 42,
) -> dict:
    """Evaluate containment probability on held-out vs random cards."""
    import subsumer

    rng = random.Random(seed)

    ids, mins_flat, maxs_flat = trainer.export_embeddings()
    dim = len(mins_flat) // len(ids)

    # Build ID -> box mapping
    id_to_idx = {eid: i for i, eid in enumerate(ids)}
    mins = np.array(mins_flat).reshape(-1, dim)
    maxs = np.array(maxs_flat).reshape(-1, dim)

    held_out_probs = []
    random_probs = []

    for deck_id, _, card_id in val_triples:
        if deck_id not in id_to_idx or card_id not in id_to_idx:
            continue

        di = id_to_idx[deck_id]
        ci = id_to_idx[card_id]

        deck_box = subsumer.NdarrayBox(mins[di].tolist(), maxs[di].tolist(), 1.0)
        card_box = subsumer.NdarrayBox(mins[ci].tolist(), maxs[ci].tolist(), 1.0)
        prob = deck_box.containment_prob(card_box)
        held_out_probs.append(prob)

        # Random cards
        for _ in range(n_random):
            rand_cid = rng.choice(all_card_ids)
            if rand_cid not in id_to_idx:
                continue
            ri = id_to_idx[rand_cid]
            rand_box = subsumer.NdarrayBox(mins[ri].tolist(), maxs[ri].tolist(), 1.0)
            rprob = deck_box.containment_prob(rand_box)
            random_probs.append(rprob)

    held_out_arr = np.array(held_out_probs) if held_out_probs else np.array([0.0])
    random_arr = np.array(random_probs) if random_probs else np.array([0.0])

    # AUC: proportion of (held_out, random) pairs where held_out > random
    n_correct = 0
    n_total = 0
    sample_size = min(len(held_out_probs), len(random_probs), 10000)
    for _ in range(sample_size):
        h = rng.choice(held_out_probs) if held_out_probs else 0
        r = rng.choice(random_probs) if random_probs else 0
        if h > r:
            n_correct += 1
        elif h == r:
            n_correct += 0.5
        n_total += 1

    auc = n_correct / n_total if n_total > 0 else 0.5

    return {
        "held_out_mean": float(held_out_arr.mean()),
        "held_out_median": float(np.median(held_out_arr)),
        "held_out_std": float(held_out_arr.std()),
        "random_mean": float(random_arr.mean()),
        "random_median": float(np.median(random_arr)),
        "random_std": float(random_arr.std()),
        "auc": float(auc),
        "n_held_out": len(held_out_probs),
        "n_random": len(random_probs),
    }


def main():
    parser = argparse.ArgumentParser(description="Train box containment embeddings")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--dim", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--lr", type=float, default=0.02)
    parser.add_argument("--batch-size", type=int, default=1024)
    parser.add_argument("--max-decks", type=int, default=20000)
    parser.add_argument("--holdout", type=float, default=0.2)
    parser.add_argument("--eval-every", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    import subsumer

    print(f"Loading {args.game} decks...")
    decks = load_decks(args.game, max_decks=args.max_decks)
    print(f"  Loaded {len(decks)} decks")

    if not decks:
        print("No decks found")
        return 1

    print("Building triples...")
    train_triples, val_triples, id_to_deck, id_to_card = build_triples(
        decks, holdout_ratio=args.holdout
    )

    n_entities = max(
        max(t[0] for t in train_triples + val_triples),
        max(t[2] for t in train_triples + val_triples),
    ) + 1
    all_card_ids = list(id_to_card.keys())

    print(f"  Decks: {len(id_to_deck)}")
    print(f"  Cards: {len(id_to_card)}")
    print(f"  Entities: {n_entities}")
    print(f"  Train triples: {len(train_triples)}")
    print(f"  Val triples: {len(val_triples)}")

    if args.dry_run:
        print("\n--- Dry Run ---")
        print(f"  Would train {args.dim}D box embeddings for {args.epochs} epochs")
        print(f"  lr={args.lr}, batch_size={args.batch_size}")
        return 0

    # Train
    print(f"\nTraining {args.dim}D box embeddings (lr={args.lr}, epochs={args.epochs})...")
    trainer = subsumer.BoxEmbeddingTrainer(args.lr, args.dim)

    # Register all entities by doing an initial pass
    # subsumer auto-creates entities on first use in train_step

    t0 = time.monotonic()
    rng = random.Random(42)

    for epoch in range(args.epochs):
        # Shuffle and batch
        rng.shuffle(train_triples)
        epoch_loss = 0.0
        n_batches = 0

        for i in range(0, len(train_triples), args.batch_size):
            batch = train_triples[i : i + args.batch_size]
            loss = trainer.train_step(batch)
            epoch_loss += loss
            n_batches += 1

        avg_loss = epoch_loss / max(n_batches, 1)

        if (epoch + 1) % args.eval_every == 0 or epoch == 0 or epoch == args.epochs - 1:
            elapsed = time.monotonic() - t0
            metrics = evaluate(trainer, val_triples, all_card_ids)
            print(
                f"  Epoch {epoch + 1:3d}/{args.epochs}: "
                f"loss={avg_loss:.4f}, "
                f"held_out={metrics['held_out_mean']:.3f}, "
                f"random={metrics['random_mean']:.3f}, "
                f"AUC={metrics['auc']:.3f}, "
                f"({elapsed:.0f}s)"
            )

    # Final evaluation
    final = evaluate(trainer, val_triples, all_card_ids)
    elapsed = time.monotonic() - t0

    print(f"\n--- Final Results ({elapsed:.0f}s) ---")
    print(f"  Held-out containment: {final['held_out_mean']:.4f} +/- {final['held_out_std']:.4f}")
    print(f"  Random containment:   {final['random_mean']:.4f} +/- {final['random_std']:.4f}")
    print(f"  AUC (held-out vs random): {final['auc']:.4f}")
    print(f"  Separation ratio: {final['held_out_mean'] / max(final['random_mean'], 1e-6):.2f}x")

    # Save checkpoint
    output_path = args.output or str(
        DATA_DIR / "embeddings" / f"{args.game}_box_containment.json"
    )
    checkpoint = trainer.save_checkpoint()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(checkpoint)
    print(f"  Checkpoint: {output_path}")

    # Save metadata
    meta_path = Path(output_path).with_suffix(".meta.json")
    meta = {
        "game": args.game,
        "dim": args.dim,
        "epochs": args.epochs,
        "lr": args.lr,
        "n_decks": len(id_to_deck),
        "n_cards": len(id_to_card),
        "n_train_triples": len(train_triples),
        "n_val_triples": len(val_triples),
        "final_loss": float(avg_loss),
        **{f"eval_{k}": v for k, v in final.items()},
        "elapsed_s": round(elapsed, 1),
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Metadata: {meta_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
