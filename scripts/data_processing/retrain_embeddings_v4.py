#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
#     "pecanpy>=2.0.0",
#     "numpy<2.0.0",
# ]
# ///
"""
Retrain embeddings for all games using cleaned corpus data.

Trains Node2Vec (PecanPy) embeddings from co-occurrence pairs CSVs
and Word2Vec from collections CSVs, then blends them.

Input files (must be pre-cleaned with normalize_corpus_names.py):
  - data/processed/pairs_large.csv (Magic)
  - data/processed/pairs_pokemon_compat.csv
  - data/processed/pairs_yugioh_ygoprodeck-tournament.csv
  - data/decks/collections_pokemon.csv
  - data/decks/collections_yugioh.csv

Output:
  - data/embeddings/{game}_cleaned_v4.wv (per game)

Usage:
  uv run scripts/data_processing/retrain_embeddings_v4.py
  uv run scripts/data_processing/retrain_embeddings_v4.py --game pokemon
  uv run scripts/data_processing/retrain_embeddings_v4.py --game magic --dim 128
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors, Word2Vec
from pecanpy.pecanpy import SparseOTF

REPO_ROOT = Path(__file__).resolve().parents[2]
EMBEDDINGS_DIR = REPO_ROOT / "data" / "embeddings"

GAME_CONFIG = {
    "magic": {
        "pairs": REPO_ROOT / "data" / "processed" / "pairs_large.csv",
        "collections": None,  # Magic uses pairs-based training only
        "dim": 128,
        "walk_length": 80,
        "num_walks": 10,
        "window": 10,
        "epochs": 50,
        "query_cards": [
            "Lightning Bolt", "Counterspell", "Sol Ring",
            "Swords to Plowshares", "Brainstorm",
        ],
    },
    "pokemon": {
        "pairs": REPO_ROOT / "data" / "processed" / "pairs_pokemon_compat.csv",
        "collections": REPO_ROOT / "data" / "decks" / "collections_pokemon.csv",
        "dim": 128,
        "walk_length": 60,
        "num_walks": 10,
        "window": 10,
        "epochs": 100,
        "query_cards": [
            "Charizard ex", "Pikachu", "Arcanine ex",
            "Boss's Orders", "Professor's Research",
        ],
    },
    "yugioh": {
        "pairs": REPO_ROOT / "data" / "processed" / "pairs_yugioh_ygoprodeck-tournament.csv",
        "collections": REPO_ROOT / "data" / "decks" / "collections_yugioh.csv",
        "dim": 128,
        "walk_length": 80,
        "num_walks": 10,
        "window": 10,
        "epochs": 50,
        "query_cards": [
            "Dark Magician", "Blue-Eyes White Dragon",
            "Ash Blossom & Joyous Spring", "Nibiru, the Primal Being",
            "Called by the Grave",
        ],
    },
}


def load_pairs_as_edges(pairs_path: Path) -> dict[tuple[str, str], int]:
    """Load co-occurrence pairs as weighted edges."""
    weights: dict[tuple[str, str], int] = {}
    with open(pairs_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        # Determine count column
        count_idx = None
        for i, h in enumerate(header):
            if h.upper() in ("COUNT", "COUNT_SET", "COUNT_MULTISET"):
                count_idx = i
                break

        for row in reader:
            if len(row) < 2:
                continue
            c1, c2 = row[0].strip(), row[1].strip()
            if not c1 or not c2 or c1 == c2:
                continue
            if c1 > c2:
                c1, c2 = c2, c1
            count = int(row[count_idx]) if count_idx and count_idx < len(row) else 1
            weights[(c1, c2)] = weights.get((c1, c2), 0) + count
    return weights


def train_pecanpy(weights: dict[tuple[str, str], int], cfg: dict) -> KeyedVectors:
    """Train Node2Vec embeddings via PecanPy."""
    dim = cfg["dim"]
    walk_length = cfg["walk_length"]
    num_walks = cfg["num_walks"]
    window = cfg["window"]
    epochs = cfg["epochs"]

    cards = set()
    for c1, c2 in weights:
        cards.add(c1)
        cards.add(c2)
    print(f"  {len(cards):,} unique cards, {len(weights):,} edges")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".edgelist", delete=False) as f:
        edgelist_path = Path(f.name)
        for (c1, c2), w in weights.items():
            f.write(f"{c1}\t{c2}\t{w}\n")

    try:
        print(f"  Generating {num_walks} walks of length {walk_length}...")
        t0 = time.time()
        g = SparseOTF(p=1.0, q=1.0, workers=4, verbose=False, extend=True)
        g.read_edg(str(edgelist_path), weighted=True, directed=False)
        walks = g.simulate_walks(num_walks=num_walks, walk_length=walk_length)
        print(f"  {len(walks):,} walks in {time.time() - t0:.1f}s")

        print(f"  Training Word2Vec (dim={dim}, window={window}, epochs={epochs})...")
        t0 = time.time()
        model = Word2Vec(
            sentences=walks,
            vector_size=dim,
            window=window,
            min_count=1,
            workers=4,
            epochs=epochs,
        )
        print(f"  Trained in {time.time() - t0:.1f}s, vocab={len(model.wv):,}")
        return model.wv
    finally:
        edgelist_path.unlink(missing_ok=True)


def train_w2v_collections(collections_path: Path, cfg: dict) -> KeyedVectors:
    """Train Word2Vec from collections CSV (per-deck card lists)."""
    dim = cfg["dim"]
    epochs = cfg.get("epochs", 200)

    # Load collections
    sentences = []
    with open(collections_path, newline="") as f:
        for row in csv.reader(f):
            if row:
                random.shuffle(row)
                sentences.append(row)

    print(f"  {len(sentences):,} decks loaded")
    t0 = time.time()
    model = Word2Vec(
        sentences=sentences,
        vector_size=dim,
        window=60,
        negative=100,
        min_count=1,
        workers=4,
        epochs=epochs,
        shrink_windows=False,
    )
    print(f"  Trained in {time.time() - t0:.1f}s, vocab={len(model.wv):,}")
    return model.wv


def blend_embeddings(wv_list: list[KeyedVectors], weights: list[float] | None = None) -> KeyedVectors:
    """Blend multiple KeyedVectors into one by weighted average."""
    if len(wv_list) == 1:
        return wv_list[0]

    if weights is None:
        weights = [1.0 / len(wv_list)] * len(wv_list)

    # Union of all vocabularies
    all_keys = set()
    for wv in wv_list:
        all_keys.update(wv.index_to_key)

    dim = wv_list[0].vector_size
    blended = KeyedVectors(vector_size=dim)

    keys = []
    vectors = []
    for key in sorted(all_keys):
        vec = np.zeros(dim, dtype=np.float32)
        total_w = 0.0
        for wv, w in zip(wv_list, weights):
            if key in wv:
                vec += w * wv[key]
                total_w += w
        if total_w > 0:
            vec /= total_w
            # L2 normalize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            keys.append(key)
            vectors.append(vec)

    blended.add_vectors(keys, vectors)
    return blended


def show_samples(wv: KeyedVectors, query_cards: list[str]) -> None:
    """Show sample similarity results."""
    for card in query_cards:
        if card not in wv:
            print(f"    '{card}' not in vocab")
            continue
        neighbors = wv.most_similar(card, topn=5)
        print(f"    {card}:")
        for name, score in neighbors:
            print(f"      {score:+.4f}  {name}")


def train_game(game: str, cfg: dict) -> Path:
    """Train embeddings for one game."""
    output_path = EMBEDDINGS_DIR / f"{game}_cleaned_v4.wv"

    print(f"\n{'='*60}")
    print(f"Training {game.upper()}")
    print(f"{'='*60}")

    embeddings: list[KeyedVectors] = []

    # Train PecanPy on pairs
    if cfg["pairs"].exists():
        print(f"\n  [PecanPy] {cfg['pairs'].name}")
        weights = load_pairs_as_edges(cfg["pairs"])
        if weights:
            wv = train_pecanpy(weights, cfg)
            embeddings.append(wv)
    else:
        print(f"  SKIP: {cfg['pairs']} not found")

    # Train Word2Vec on collections
    if cfg.get("collections") and cfg["collections"].exists():
        print(f"\n  [Word2Vec] {cfg['collections'].name}")
        wv = train_w2v_collections(cfg["collections"], cfg)
        embeddings.append(wv)

    if not embeddings:
        print(f"  ERROR: No training data for {game}")
        return output_path

    # Blend if multiple
    if len(embeddings) > 1:
        print(f"\n  Blending {len(embeddings)} embeddings...")
        final = blend_embeddings(embeddings, weights=[0.5, 0.5])
    else:
        final = embeddings[0]

    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
    final.save(str(output_path))
    print(f"\n  Saved: {output_path} ({len(final):,} cards, {final.vector_size}D)")

    # Show samples
    if cfg.get("query_cards"):
        print(f"\n  Sample similarities:")
        show_samples(final, cfg["query_cards"])

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrain embeddings with cleaned data")
    parser.add_argument("--game", choices=["magic", "pokemon", "yugioh", "all"], default="all")
    parser.add_argument("--dim", type=int, default=None, help="Override embedding dimension")
    args = parser.parse_args()

    games = [args.game] if args.game != "all" else ["magic", "pokemon", "yugioh"]

    results = {}
    for game in games:
        cfg = GAME_CONFIG[game].copy()
        if args.dim:
            cfg["dim"] = args.dim
        output = train_game(game, cfg)
        results[game] = output

    print(f"\n{'='*60}")
    print("TRAINING COMPLETE")
    print(f"{'='*60}")
    for game, path in results.items():
        exists = path.exists()
        print(f"  {game}: {path.name} {'(OK)' if exists else '(MISSING)'}")

    print("\nTo use new embeddings, update .env:")
    for game, path in results.items():
        suffix = game.upper()
        print(f"  EMBEDDINGS_PATH_{suffix}=./{path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
