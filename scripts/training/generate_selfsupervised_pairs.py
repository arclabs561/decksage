#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
# ]
# ///
"""
Generate self-supervised training pairs from card attributes.

Creates (card_text_A, card_text_B, similarity_score) triples using
attribute overlap as pseudo-labels. No human/LLM annotations needed.

Signals used:
- Keyword/ability overlap (Jaccard): "Flying" + "First strike" cards are similar
- Type match: Creatures are more similar to Creatures than to Sorceries
- Cost proximity: 3-mana cards are more similar to 2-mana cards than to 7-mana
- Oracle text token overlap: cards that mention "destroy" + "creature" share function

Output: JSON file with pairs suitable for cross-encoder training.

Usage:
    uv run scripts/training/generate_selfsupervised_pairs.py --game magic
    uv run scripts/training/generate_selfsupervised_pairs.py --all-games
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def _load_cards(game: str) -> list[dict]:
    """Load card attributes from CSV."""
    for db_path in [
        DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv",
        DATA_DIR / "processed" / f"card_attributes_{game}.csv",
    ]:
        if db_path.exists():
            with open(db_path) as f:
                return list(csv.DictReader(f))
    return []


def _card_text(row: dict) -> str:
    """Build text representation matching cross-encoder training format."""
    name = row.get("name", row.get("card_name", ""))
    typ = row.get("type_line", row.get("type", ""))
    oracle = row.get("oracle_text", row.get("text", row.get("effect", "")))
    cost = row.get("mana_cost", row.get("cmc", ""))
    if not oracle:
        return ""
    parts = [name]
    if typ:
        parts.append(typ)
    if cost:
        parts.append(str(cost))
    pw = row.get("power", "")
    tg = row.get("toughness", "")
    if pw and tg:
        parts.append(f"{pw}/{tg}")
    hp = row.get("hp", "")
    if hp:
        parts.append(f"HP {hp}")
    parts.append(oracle)
    return " | ".join(parts)


def _keyword_set(row: dict) -> set[str]:
    """Extract keyword set from card."""
    kws = set()
    for field in ["keywords", "keyword_abilities"]:
        raw = row.get(field, "").strip()
        if raw:
            for kw in raw.split(","):
                kw = kw.strip().lower()
                if kw:
                    kws.add(kw)
    return kws


def _base_type(row: dict) -> str:
    """Extract base type (before em-dash)."""
    typ = row.get("type_line", row.get("type", ""))
    return typ.split("—")[0].strip().split("\u2014")[0].strip().lower() if typ else ""


def _cmc(row: dict) -> float:
    """Extract converted mana cost."""
    cmc = row.get("cmc", "")
    try:
        return float(cmc) if cmc else -1.0
    except (ValueError, TypeError):
        return -1.0


def _oracle_tokens(row: dict) -> set[str]:
    """Extract meaningful oracle text tokens."""
    oracle = row.get("oracle_text", row.get("text", row.get("effect", "")))
    if not oracle:
        return set()
    # Simple tokenization, lowercase, filter short/common words
    stop = {"the", "a", "an", "to", "of", "and", "or", "is", "it", "its", "this", "that", "for", "in", "on", "at", "with", "from", "by", "as", "if", "you", "your"}
    tokens = set()
    for word in oracle.lower().split():
        word = word.strip(".,;:()\"'")
        if len(word) >= 3 and word not in stop:
            tokens.add(word)
    return tokens


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


def compute_similarity(row_a: dict, row_b: dict) -> float:
    """Compute attribute-based similarity score in [0, 1].

    Weighted combination of:
    - Keyword overlap (40%): functional role signal
    - Oracle text overlap (30%): shared mechanics
    - Type match (20%): same card category
    - Cost proximity (10%): similar mana cost
    """
    kw_sim = _jaccard(_keyword_set(row_a), _keyword_set(row_b))
    oracle_sim = _jaccard(_oracle_tokens(row_a), _oracle_tokens(row_b))
    type_sim = 1.0 if _base_type(row_a) == _base_type(row_b) and _base_type(row_a) else 0.0
    cmc_a, cmc_b = _cmc(row_a), _cmc(row_b)
    cost_sim = max(0.0, 1.0 - abs(cmc_a - cmc_b) / 5.0) if cmc_a >= 0 and cmc_b >= 0 else 0.5

    return 0.40 * kw_sim + 0.30 * oracle_sim + 0.20 * type_sim + 0.10 * cost_sim


def generate_pairs(game: str, max_pairs: int = 50000) -> list[dict]:
    """Generate self-supervised training pairs from card attributes."""
    rows = _load_cards(game)
    if not rows:
        log.warning(f"No cards found for {game}")
        return []

    # Filter to cards with oracle text
    rows = [r for r in rows if _card_text(r)]
    log.info(f"{game}: {len(rows)} cards with oracle text")

    # Build keyword index for efficient candidate selection
    kw_index: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        for kw in _keyword_set(row):
            kw_index[kw].append(i)

    # Strategy: for each card, find candidates via shared keywords (not random)
    # This produces informative pairs, not trivially distinguishable ones
    rng = np.random.RandomState(42)
    pairs = []
    seen = set()

    for i, row_a in enumerate(rows):
        kws_a = _keyword_set(row_a)
        text_a = _card_text(row_a)
        if not text_a:
            continue

        # Candidates: cards sharing at least one keyword
        candidates = set()
        for kw in kws_a:
            for j in kw_index[kw]:
                if j != i:
                    candidates.add(j)

        # Also add some random cards for negative examples
        n_random = min(5, len(rows) - 1)
        random_indices = rng.choice(len(rows), size=n_random, replace=False)
        candidates.update(int(j) for j in random_indices if j != i)

        # Sample up to 10 candidates per card
        cand_list = list(candidates)
        if len(cand_list) > 10:
            cand_list = [cand_list[j] for j in rng.choice(len(cand_list), size=10, replace=False)]

        for j in cand_list:
            key = (min(i, j), max(i, j))
            if key in seen:
                continue
            seen.add(key)

            row_b = rows[j]
            text_b = _card_text(row_b)
            if not text_b:
                continue

            score = compute_similarity(row_a, row_b)
            pairs.append({
                "query_text": text_a,
                "candidate_text": text_b,
                "score": round(score, 4),
                "query": row_a.get("name", ""),
                "candidate": row_b.get("name", ""),
            })

        if len(pairs) >= max_pairs:
            break

    log.info(f"  Generated {len(pairs)} pairs")

    # Score distribution
    scores = np.array([p["score"] for p in pairs])
    log.info(f"  Score distribution: mean={scores.mean():.3f}, median={np.median(scores):.3f}")
    brackets = [(0, 0.1), (0.1, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 1.01)]
    for lo, hi in brackets:
        n = int(((scores >= lo) & (scores < hi)).sum())
        log.info(f"    [{lo:.1f}, {hi:.1f}): {n} ({n/len(scores)*100:.0f}%)")

    return pairs


def main():
    parser = argparse.ArgumentParser(description="Generate self-supervised training pairs")
    parser.add_argument("--game", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--max-pairs", type=int, default=50000)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game] if args.game else ["magic"]

    all_pairs = []
    for game in games:
        pairs = generate_pairs(game, max_pairs=args.max_pairs)
        all_pairs.extend(pairs)

    out_path = args.output or str(DATA_DIR / "training" / "selfsupervised_pairs.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"pairs": all_pairs, "count": len(all_pairs)}, f)
    log.info(f"\nSaved {len(all_pairs)} pairs to {out_path}")


if __name__ == "__main__":
    main()
