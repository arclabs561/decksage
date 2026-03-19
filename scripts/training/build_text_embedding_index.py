#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sentence-transformers>=2.2.0",
#     "torch>=2.0.0",
#     "numpy>=1.24.0",
#     "pandas>=2.0.0",
#     "datasets>=2.0.0",
#     "accelerate>=1.1.0",
# ]
# ///
"""
Pre-encode all cards with E5 text embeddings for candidate generation.

Builds a numpy matrix of text embeddings for the full card catalog,
enabling text-based candidate retrieval in fusion (breaking the
co-occurrence echo chamber that limits catalog coverage to 11.6%).

Usage:
    uv run scripts/training/build_text_embedding_index.py --game magic
    uv run scripts/training/build_text_embedding_index.py --game magic --model data/embeddings/e5_finetuned_magic_multitask
    uv run scripts/training/build_text_embedding_index.py --all-games
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))


def load_card_catalog(game: str) -> list[dict]:
    """Load all cards from enriched CSV."""
    import pandas as pd

    path = DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        path = DATA_DIR / "processed" / f"card_attributes_{game}.csv"
    if not path.exists():
        print(f"No card attributes found for {game}")
        return []

    df = pd.read_csv(path, low_memory=False)
    cards = []
    for _, row in df.iterrows():
        name = str(row.get("name", ""))
        if not name:
            continue
        card = {k: v for k, v in row.to_dict().items() if not (isinstance(v, float) and v != v)}
        cards.append(card)
    return cards


def build_index(game: str, model_path: str = "intfloat/e5-base-v2") -> None:
    """Build text embedding index for a game."""
    from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder

    cards = load_card_catalog(game)
    if not cards:
        return

    print(f"\n{game.upper()}: {len(cards)} cards")
    print(f"Model: {model_path}")

    embedder = InstructionTunedCardEmbedder(model_name=model_path)

    # Batch encode all cards
    t0 = time.time()
    embeddings = embedder.embed_cards_batch(cards, instruction_type="similar", batch_size=64)
    elapsed = time.time() - t0

    print(f"Encoded in {elapsed:.1f}s ({len(cards) / elapsed:.0f} cards/s)")
    print(f"Shape: {embeddings.shape}")

    # L2 normalize for cosine similarity via dot product
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    embeddings = (embeddings / norms).astype(np.float32)

    # Save index
    out_dir = DATA_DIR / "cache" / "text_embeddings"
    out_dir.mkdir(parents=True, exist_ok=True)

    card_names = [c.get("name", "") for c in cards]
    np.save(out_dir / f"{game}_embeddings.npy", embeddings)
    with open(out_dir / f"{game}_names.txt", "w") as f:
        for name in card_names:
            f.write(name + "\n")

    print(f"Saved to {out_dir}/{game}_embeddings.npy ({embeddings.nbytes / 1024 / 1024:.1f} MB)")
    print(f"  + {out_dir}/{game}_names.txt ({len(card_names)} names)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build text embedding index")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--model", default="intfloat/e5-base-v2", help="E5 model path")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    for game in games:
        build_index(game, args.model)

    return 0


if __name__ == "__main__":
    sys.exit(main())
