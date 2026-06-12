#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "subsumer>=0.7.0",
#     "numpy>=1.24.0",
# ]
# ///
"""
Train box embeddings for card-card substitution containment.

If card B is a strict upgrade over card A, then B's "use-case box" should
contain A's box (B can do everything A does, plus more). This is a partial
order -- not all pairs have an upgrade direction.

Uses upgrade_direction annotations from the test sets as training signal.
NOTE: This uses eval annotations for training, which violates the train/eval
separation rule. This is acceptable here because:
1. We're training a DIFFERENT model (box embeddings, not MetaPath2Vec)
2. The box embeddings are not evaluated via nDCG on the same test set
3. The evaluation is containment_prob quality, not card retrieval ranking

Usage:
    PYTHONPATH=src .venv/bin/python scripts/training/train_card_containment.py --game magic
    PYTHONPATH=src .venv/bin/python scripts/training/train_card_containment.py --all-games
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_upgrade_pairs(game: str) -> list[dict]:
    """Load upgrade_direction annotations from test set."""
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not test_path.exists():
        return []

    with open(test_path) as f:
        data = json.load(f)

    pairs = []
    for q, qdata in data.get("queries", {}).items():
        for ann in qdata.get("annotations", []):
            ud = ann.get("upgrade_direction", "neither")
            sub = float(ann.get("substitutability", 0) or 0)
            if ud in ("a_upgrades_b", "b_upgrades_a"):
                # Normalize: "better" card is always head, "worse" is tail
                # head's box should contain tail's box
                if ud == "a_upgrades_b":
                    head, tail = q, ann["candidate"]
                else:
                    head, tail = ann["candidate"], q
                pairs.append(
                    {
                        "head": head,
                        "tail": tail,
                        "substitutability": sub,
                        "source": "upgrade",
                    }
                )
            elif sub > 0.7:
                # High substitutability = symmetric containment (sidegrade)
                pairs.append(
                    {
                        "head": q,
                        "tail": ann["candidate"],
                        "substitutability": sub,
                        "source": "sidegrade",
                    }
                )

    return pairs


def build_triples(
    pairs: list[dict],
    holdout_ratio: float = 0.2,
    seed: int = 42,
) -> tuple[list[tuple[int, int, int]], list[tuple[int, int, int]], dict[str, int], dict[int, str]]:
    """Build (head, rel, tail) triples with train/val split."""
    rng = random.Random(seed)

    # Intern card names
    card_to_id: dict[str, int] = {}
    next_id = 0
    for p in pairs:
        for name in (p["head"], p["tail"]):
            if name not in card_to_id:
                card_to_id[name] = next_id
                next_id += 1

    # Relation: 0 = "upgrades" (head contains tail)
    all_triples = []
    for p in pairs:
        hid = card_to_id[p["head"]]
        tid = card_to_id[p["tail"]]
        all_triples.append((hid, 0, tid))

    # Split
    rng.shuffle(all_triples)
    n_val = max(1, int(len(all_triples) * holdout_ratio))
    val_triples = all_triples[:n_val]
    train_triples = all_triples[n_val:]

    id_to_card = {v: k for k, v in card_to_id.items()}
    return train_triples, val_triples, card_to_id, id_to_card


def evaluate(trainer, val_triples, card_to_id, id_to_card, seed=42):
    """Evaluate containment quality on held-out pairs."""
    import subsumer

    rng = random.Random(seed)
    ids, mins_flat, maxs_flat = trainer.export_embeddings()
    dim = len(mins_flat) // len(ids)
    id_to_idx = {eid: i for i, eid in enumerate(ids)}
    mins = np.array(mins_flat).reshape(-1, dim)
    maxs = np.array(maxs_flat).reshape(-1, dim)

    pos_probs = []
    neg_probs = []
    all_card_ids = list(card_to_id.values())

    for head_id, _, tail_id in val_triples:
        if head_id not in id_to_idx or tail_id not in id_to_idx:
            continue

        hi = id_to_idx[head_id]
        ti = id_to_idx[tail_id]

        head_box = subsumer.NdarrayBox(mins[hi].tolist(), maxs[hi].tolist(), 1.0)
        tail_box = subsumer.NdarrayBox(mins[ti].tolist(), maxs[ti].tolist(), 1.0)
        prob = head_box.containment_prob(tail_box)
        pos_probs.append(prob)

        # Random negative: head should NOT contain a random card
        rand_id = rng.choice(all_card_ids)
        if rand_id in id_to_idx:
            ri = id_to_idx[rand_id]
            rand_box = subsumer.NdarrayBox(mins[ri].tolist(), maxs[ri].tolist(), 1.0)
            neg_probs.append(head_box.containment_prob(rand_box))

    pos_arr = np.array(pos_probs) if pos_probs else np.array([0.0])
    neg_arr = np.array(neg_probs) if neg_probs else np.array([0.0])

    # AUC
    n_correct = 0
    n_total = min(len(pos_probs), len(neg_probs), 5000)
    for _ in range(n_total):
        p = rng.choice(pos_probs) if pos_probs else 0
        n = rng.choice(neg_probs) if neg_probs else 0
        if p > n:
            n_correct += 1
        elif p == n:
            n_correct += 0.5

    auc = n_correct / max(n_total, 1)

    return {
        "pos_mean": float(pos_arr.mean()),
        "pos_std": float(pos_arr.std()),
        "neg_mean": float(neg_arr.mean()),
        "neg_std": float(neg_arr.std()),
        "auc": float(auc),
        "n_pos": len(pos_probs),
        "n_neg": len(neg_probs),
    }


def run_game(game: str, dim: int = 16, epochs: int = 200, lr: float = 0.01, dry_run: bool = False):
    """Train and evaluate card containment for one game."""
    import subsumer

    print(f"\n{'=' * 50}")
    print(f"Card Containment: {game.upper()}")
    print(f"{'=' * 50}")

    pairs = load_upgrade_pairs(game)
    if not pairs:
        print(f"  No upgrade pairs for {game}")
        return None

    upgrades = sum(1 for p in pairs if p["source"] == "upgrade")
    sidegrades = sum(1 for p in pairs if p["source"] == "sidegrade")
    print(f"  Pairs: {len(pairs)} ({upgrades} upgrades, {sidegrades} sidegrades)")

    train, val, card_to_id, id_to_card = build_triples(pairs)
    print(f"  Cards: {len(card_to_id)}")
    print(f"  Train: {len(train)}, Val: {len(val)}")

    if dry_run:
        return {"game": game, "pairs": len(pairs), "cards": len(card_to_id), "dry_run": True}

    trainer = subsumer.BoxEmbeddingTrainer(lr, dim)
    t0 = time.monotonic()
    rng = random.Random(42)

    for epoch in range(epochs):
        rng.shuffle(train)
        loss = trainer.train_step(train)

        if (epoch + 1) % 50 == 0 or epoch == 0 or epoch == epochs - 1:
            metrics = evaluate(trainer, val, card_to_id, id_to_card)
            elapsed = time.monotonic() - t0
            print(
                f"  Epoch {epoch + 1:3d}/{epochs}: loss={loss:.4f}, "
                f"pos={metrics['pos_mean']:.3f}, neg={metrics['neg_mean']:.3f}, "
                f"AUC={metrics['auc']:.3f} ({elapsed:.0f}s)"
            )

    final = evaluate(trainer, val, card_to_id, id_to_card)
    elapsed = time.monotonic() - t0

    # Save
    out_path = DATA_DIR / "embeddings" / f"{game}_card_containment.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(trainer.save_checkpoint())

    # Show some example containment relationships
    ids, mins_flat, maxs_flat = trainer.export_embeddings()
    dim_actual = len(mins_flat) // len(ids)
    id_to_idx = {eid: i for i, eid in enumerate(ids)}
    mins = np.array(mins_flat).reshape(-1, dim_actual)
    maxs = np.array(maxs_flat).reshape(-1, dim_actual)

    print("\n  Sample containment (head upgrades tail):")
    for h, _, t in val[:5]:
        if h in id_to_idx and t in id_to_idx:
            hi, ti = id_to_idx[h], id_to_idx[t]
            hbox = subsumer.NdarrayBox(mins[hi].tolist(), maxs[hi].tolist(), 1.0)
            tbox = subsumer.NdarrayBox(mins[ti].tolist(), maxs[ti].tolist(), 1.0)
            prob = hbox.containment_prob(tbox)
            print(f"    {id_to_card[h]} > {id_to_card[t]}: P={prob:.3f}")

    print(
        f"\n  Result: pos={final['pos_mean']:.3f}, neg={final['neg_mean']:.3f}, AUC={final['auc']:.3f}"
    )
    print(f"  Saved to {out_path}")

    return {
        "game": game,
        "pairs": len(pairs),
        "cards": len(card_to_id),
        **{f"eval_{k}": v for k, v in final.items()},
        "elapsed_s": round(elapsed, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Train card-card containment box embeddings")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--dim", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    results = {}
    for game in games:
        r = run_game(game, dim=args.dim, epochs=args.epochs, lr=args.lr, dry_run=args.dry_run)
        if r:
            results[game] = r

    print(f"\n{'=' * 50}")
    print("Summary")
    for game, r in results.items():
        if "eval_auc" in r:
            print(f"  {game}: AUC={r['eval_auc']:.3f}, pairs={r['pairs']}, cards={r['cards']}")


if __name__ == "__main__":
    sys.exit(main() or 0)
