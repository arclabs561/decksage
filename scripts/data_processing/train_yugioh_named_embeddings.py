#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "pecanpy>=2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Train Yu-Gi-Oh embeddings from the name-fixed pairs CSV and show sample
similarity results with real card names.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
from gensim.models import Word2Vec
from pecanpy.pecanpy import SparseOTF

REPO_ROOT = Path(__file__).resolve().parents[2]
PAIRS_CSV = REPO_ROOT / "data" / "processed" / "pairs_yugioh_ygoprodeck-tournament.csv"
OUTPUT_WV = REPO_ROOT / "data" / "embeddings" / "yugioh_pecanpy_named.wv"

# Training hyperparameters
DIM = 128
WALK_LENGTH = 80
NUM_WALKS = 10
WINDOW = 10
EPOCHS = 50


def load_pairs(csv_path: Path) -> dict[tuple[str, str], int]:
    """Load card co-occurrence pairs and weights."""
    print(f"Loading pairs from {csv_path} ...")
    df = pd.read_csv(csv_path)
    print(f"  {len(df):,} rows")

    weights: dict[tuple[str, str], int] = {}
    for _, row in df.iterrows():
        c1 = str(row["NAME_1"]).strip()
        c2 = str(row["NAME_2"]).strip()
        if not c1 or not c2 or c1 == c2:
            continue
        if c1 > c2:
            c1, c2 = c2, c1
        key = (c1, c2)
        count = int(row["COUNT"]) if pd.notna(row["COUNT"]) else 1
        weights[key] = weights.get(key, 0) + count

    cards = set()
    for c1, c2 in weights:
        cards.add(c1)
        cards.add(c2)
    print(f"  {len(cards):,} unique cards, {len(weights):,} edges")
    return weights


def train(weights: dict[tuple[str, str], int]) -> None:
    """Train Node2Vec embeddings via PecanPy + Word2Vec."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".edgelist", delete=False) as f:
        edgelist_path = Path(f.name)
        for (c1, c2), w in weights.items():
            f.write(f"{c1}\t{c2}\t{w}\n")

    try:
        print(f"Generating random walks (p=1.0, q=1.0) ...")
        g = SparseOTF(p=1.0, q=1.0, workers=4, verbose=True, extend=True)
        g.read_edg(str(edgelist_path), weighted=True, directed=False)
        walks = g.simulate_walks(num_walks=NUM_WALKS, walk_length=WALK_LENGTH)
        print(f"  {len(walks):,} walks generated")

        print(f"Training Word2Vec (dim={DIM}, window={WINDOW}, epochs={EPOCHS}) ...")
        model = Word2Vec(
            sentences=walks,
            vector_size=DIM,
            window=WINDOW,
            min_count=1,
            workers=4,
            epochs=EPOCHS,
        )

        OUTPUT_WV.parent.mkdir(parents=True, exist_ok=True)
        model.wv.save(str(OUTPUT_WV))
        print(f"  Saved embeddings to {OUTPUT_WV}")
        print(f"  Vocabulary size: {len(model.wv):,}")
    finally:
        edgelist_path.unlink(missing_ok=True)


def show_similarity_samples() -> None:
    """Load saved embeddings and display sample similarities."""
    from gensim.models import KeyedVectors

    print(f"\n{'='*60}")
    print("Sample similarity results (real card names)")
    print(f"{'='*60}\n")

    wv = KeyedVectors.load(str(OUTPUT_WV))

    # Iconic cards to query
    query_cards = [
        "Blue-Eyes White Dragon",
        "Dark Magician",
        "Ash Blossom & Joyous Spring",
        "Pot of Desires",
        "Nibiru, the Primal Being",
        "Called by the Grave",
        "Infinite Impermanence",
        "Monster Reborn",
    ]

    for card in query_cards:
        if card not in wv:
            print(f"  '{card}' not in vocabulary, skipping\n")
            continue
        print(f"  Most similar to '{card}':")
        neighbors = wv.most_similar(card, topn=5)
        for name, score in neighbors:
            print(f"    {score:+.4f}  {name}")
        print()


def main() -> int:
    weights = load_pairs(PAIRS_CSV)
    train(weights)
    show_similarity_samples()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
