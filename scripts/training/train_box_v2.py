#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "subsumer>=0.7.2",
#     "numpy>=1.24.0",
# ]
# ///
"""
Train box embeddings for card-card containment relationships.

Three signal sources, combined:
1. Annotation upgrade pairs: A upgrades B => B's box inside A's box
2. Substitutability pairs: A substitutes B => high mutual containment
3. Deck-derived subset pairs: if card A appears in every deck that has B
   (but B doesn't always appear with A), then B's use-cases are a subset of A's

Usage:
    uv run scripts/training/train_box_v2.py --game magic --dim 32 --epochs 200
    uv run scripts/training/train_box_v2.py --game magic --dry-run
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path

import numpy as np

# Force unbuffered stdout
if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_annotation_pairs(game: str) -> list[tuple[str, str, str]]:
    """Load upgrade/substitute pairs from annotations.

    Returns list of (card_a, card_b, relation) where relation is:
    - 'a_upgrades_b': A subsumes B (B's box inside A's box)
    - 'b_upgrades_a': B subsumes A
    - 'substitute': high mutual containment
    """
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not path.exists():
        return []

    with open(path) as f:
        data = json.load(f)

    pairs = []
    queries = data.get("queries", {})
    for qname, qdata in queries.items():
        for ann in qdata.get("annotations", []):
            candidate = ann.get("candidate", "")
            if not candidate:
                continue

            ud = ann.get("upgrade_direction")
            sub_score = ann.get("substitutability")

            if ud == "a_upgrades_b":
                pairs.append((qname, candidate, "a_upgrades_b"))
            elif ud == "b_upgrades_a":
                pairs.append((qname, candidate, "b_upgrades_a"))
            elif sub_score is not None and float(sub_score) > 0.7:
                pairs.append((qname, candidate, "substitute"))

    return pairs


def load_deck_subset_pairs(
    game: str, min_cooccurrence: int = 10, max_pairs: int = 50000
) -> list[tuple[str, str]]:
    """Derive asymmetric containment from deck co-occurrence.

    If card A appears in 90%+ of decks that contain B, but B appears in
    only 50% of decks with A, then A's role subsumes B's role
    (A is more general, B is more specialized).

    Returns (general_card, specialized_card) pairs.
    """
    deck_dir = DATA_DIR / "decks"
    card_decks: dict[str, set[str]] = defaultdict(set)

    for f in sorted(deck_dir.glob(f"decks_{game}_*.jsonl")):
        with open(f) as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    deck = json.loads(line)
                except json.JSONDecodeError:
                    continue

                deck_id = deck.get("deck_id", deck.get("id", ""))
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

                for card in cards:
                    card_decks[card].add(deck_id)

    # Find asymmetric co-occurrence pairs
    # Only consider cards that appear in enough decks
    frequent = {c: d for c, d in card_decks.items() if len(d) >= min_cooccurrence}
    print(f"  {len(frequent)} cards with >= {min_cooccurrence} decks")

    pairs = []
    cards = list(frequent.keys())
    rng = random.Random(42)
    rng.shuffle(cards)

    for i, a in enumerate(cards):
        if len(pairs) >= max_pairs:
            break
        decks_a = frequent[a]
        for b in cards[i + 1 :]:
            if len(pairs) >= max_pairs:
                break
            decks_b = frequent[b]

            # How much of B's decks also have A?
            overlap = len(decks_a & decks_b)
            if overlap < min_cooccurrence:
                continue

            frac_b_in_a = overlap / len(decks_b)  # P(A | B)
            frac_a_in_b = overlap / len(decks_a)  # P(B | A)

            # Asymmetry: A subsumes B if A appears in most B-decks but not vice versa
            if frac_b_in_a > 0.8 and frac_a_in_b < 0.5:
                pairs.append((a, b))  # A is general, B is specialized
            elif frac_a_in_b > 0.8 and frac_b_in_a < 0.5:
                pairs.append((b, a))  # B is general, A is specialized

    return pairs


def build_triples(
    annotation_pairs: list[tuple[str, str, str]],
    deck_pairs: list[tuple[str, str]],
) -> tuple[list[tuple[int, int, int]], dict[str, int], int]:
    """Convert pairs to integer triples for subsumer.

    Relations:
    0 = subsumes (general card's box contains specialized card's box)
    """
    card_to_id: dict[str, int] = {}
    next_id = 0

    def get_id(name: str) -> int:
        nonlocal next_id
        if name not in card_to_id:
            card_to_id[name] = next_id
            next_id += 1
        return card_to_id[name]

    triples = []

    # Annotation pairs (high quality, weighted 3x by repetition)
    for a, b, rel in annotation_pairs:
        aid, bid = get_id(a), get_id(b)
        if rel == "a_upgrades_b":
            # A subsumes B: (A, subsumes, B)
            for _ in range(3):
                triples.append((aid, 0, bid))
        elif rel == "b_upgrades_a":
            for _ in range(3):
                triples.append((bid, 0, aid))
        elif rel == "substitute":
            # Mutual containment: both directions
            triples.append((aid, 0, bid))
            triples.append((bid, 0, aid))

    # Deck-derived pairs (lower quality, 1x weight)
    for general, specialized in deck_pairs:
        gid, sid = get_id(general), get_id(specialized)
        triples.append((gid, 0, sid))

    return triples, card_to_id, 1  # 1 relation type


def evaluate_boxes(trainer, card_to_id: dict[str, int], test_pairs: list[tuple[str, str, str]]) -> dict:
    """Evaluate box containment on held-out annotation pairs."""
    import subsumer

    # Export embeddings to build per-entity boxes
    entity_ids, mins, maxs = trainer.export_embeddings()
    id_to_idx = {eid: i for i, eid in enumerate(entity_ids)}
    temperature = 50.0  # default final gumbel_beta

    def get_box(entity_id: int):
        idx = id_to_idx.get(entity_id)
        if idx is None:
            return None
        return subsumer.NdarrayGumbelBox(mins[idx], maxs[idx], temperature)

    correct_direction = 0
    wrong_direction = 0
    sub_overlap = []
    total = 0

    for a, b, rel in test_pairs:
        if a not in card_to_id or b not in card_to_id:
            continue

        aid, bid = card_to_id[a], card_to_id[b]
        box_a, box_b = get_box(aid), get_box(bid)
        if box_a is None or box_b is None:
            continue

        p_a_contains_b = box_a.containment_prob(box_b)
        p_b_contains_a = box_b.containment_prob(box_a)

        if rel == "a_upgrades_b":
            if p_a_contains_b > p_b_contains_a:
                correct_direction += 1
            else:
                wrong_direction += 1
            total += 1
        elif rel == "b_upgrades_a":
            if p_b_contains_a > p_a_contains_b:
                correct_direction += 1
            else:
                wrong_direction += 1
            total += 1
        elif rel == "substitute":
            sub_overlap.append(min(p_a_contains_b, p_b_contains_a))

    accuracy = correct_direction / max(total, 1)
    avg_sub_overlap = sum(sub_overlap) / max(len(sub_overlap), 1) if sub_overlap else 0

    return {
        "direction_accuracy": round(accuracy, 4),
        "correct": correct_direction,
        "wrong": wrong_direction,
        "total_directional": total,
        "avg_substitute_overlap": round(avg_sub_overlap, 4),
        "n_substitute_pairs": len(sub_overlap),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train card-card box embeddings")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--dim", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--neg-samples", type=int, default=5)
    parser.add_argument("--max-deck-pairs", type=int, default=20000)
    parser.add_argument("--min-cooccurrence", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"Box Embeddings v2 [{args.game}]")
    print(f"{'=' * 60}")

    # 1. Load annotation pairs
    print(f"\n[1/5] Loading annotation pairs...")
    ann_pairs = load_annotation_pairs(args.game)
    upgrades = [p for p in ann_pairs if p[2] in ("a_upgrades_b", "b_upgrades_a")]
    subs = [p for p in ann_pairs if p[2] == "substitute"]
    print(f"  {len(upgrades)} upgrade pairs, {len(subs)} substitute pairs")

    # 2. Load deck-derived subset pairs
    print(f"\n[2/5] Deriving deck subset pairs...")
    deck_pairs = load_deck_subset_pairs(
        args.game, min_cooccurrence=args.min_cooccurrence, max_pairs=args.max_deck_pairs
    )
    print(f"  {len(deck_pairs)} deck-derived pairs")

    # 3. Split annotations into train/test (80/20)
    rng = random.Random(42)
    rng.shuffle(ann_pairs)
    split = int(len(ann_pairs) * 0.8)
    train_ann = ann_pairs[:split]
    test_ann = ann_pairs[split:]

    # 4. Build triples
    print(f"\n[3/5] Building triples...")
    triples, card_to_id, n_relations = build_triples(train_ann, deck_pairs)
    print(f"  {len(triples)} triples, {len(card_to_id)} entities, {n_relations} relation")

    if args.dry_run:
        print("\n  Dry run -- stopping here")
        return 0

    # 5. Train
    print(f"\n[4/5] Training (dim={args.dim}, epochs={args.epochs}, lr={args.lr})...")
    import subsumer

    config = subsumer.TrainingConfig(
        dim=args.dim,
        epochs=args.epochs,
        learning_rate=args.lr,
        negative_samples=args.neg_samples,
        batch_size=min(1024, len(triples)),
    )

    t0 = time.monotonic()
    trainer = subsumer.BoxEmbeddingTrainer.from_config(config)

    # Split annotation test set into val triples for early stopping
    val_triples_list = []
    for a, b, rel in test_ann:
        if a in card_to_id and b in card_to_id:
            aid, bid = card_to_id[a], card_to_id[b]
            if rel == "a_upgrades_b":
                val_triples_list.append((aid, 0, bid))
            elif rel == "b_upgrades_a":
                val_triples_list.append((bid, 0, aid))
            elif rel == "substitute":
                val_triples_list.append((aid, 0, bid))

    # subsumer expects list of tuples, not ndarray
    val_tuples = val_triples_list if val_triples_list else None

    fit_result = trainer.fit(
        triples,
        val_triples=val_tuples,
        num_entities=len(card_to_id),
    )
    elapsed = time.monotonic() - t0
    print(f"  Training complete in {elapsed:.1f}s")
    if isinstance(fit_result, dict):
        print(f"  MRR: {fit_result.get('mrr', 'N/A')}")
        print(f"  Hits@10: {fit_result.get('hits_at_10', 'N/A')}")
        print(f"  Best epoch: {fit_result.get('best_epoch', 'N/A')}")

    # 6. Evaluate
    print(f"\n[5/5] Evaluating...")
    results = evaluate_boxes(trainer, card_to_id, test_ann)
    print(f"  Direction accuracy: {results['direction_accuracy']:.3f} ({results['correct']}/{results['total_directional']})")
    print(f"  Substitute overlap: {results['avg_substitute_overlap']:.3f} ({results['n_substitute_pairs']} pairs)")

    # Save
    id_to_card = {v: k for k, v in card_to_id.items()}
    out_dir = DATA_DIR / "embeddings"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.game}_box_v2.json"

    box_data = {
        "game": args.game,
        "dim": args.dim,
        "n_entities": len(card_to_id),
        "card_to_id": card_to_id,
        "results": results,
        "params": {
            "epochs": args.epochs,
            "lr": args.lr,
            "neg_samples": args.neg_samples,
            "n_annotation_pairs": len(ann_pairs),
            "n_deck_pairs": len(deck_pairs),
            "n_triples": len(triples),
        },
    }

    with open(out_path, "w") as f:
        json.dump(box_data, f, indent=2)
    print(f"\n  Saved to {out_path}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
