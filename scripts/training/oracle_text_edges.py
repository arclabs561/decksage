#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["sentence-transformers>=2.2.0", "numpy>=1.24.0"]
# ///
"""
Generate organic similarity edges from card oracle text embeddings.

Uses sentence-transformers to embed card text (name + type + oracle text),
then creates edges between cards with high cosine similarity. This is an
organic training signal (no LLM annotations needed) based purely on card
text content.

Strategy:
  1. Load card attributes CSV with oracle text
  2. Embed all cards using sentence-transformers (batched)
  3. For each card, find top-K most similar by cosine distance
  4. Write edges above threshold as edgelist

This produces "functional replacement" edges -- cards that DO similar things
based on their rules text. Complements co-occurrence edges (synergy signal).

Usage:
    python scripts/training/oracle_text_edges.py \
        --csv data/processed/card_attributes_enriched.csv \
        --output data/graphs/magic_oracle_text.edg \
        --threshold 0.80 --top-k 20

    python scripts/training/oracle_text_edges.py \
        --csv data/processed/card_attributes_yugioh.csv \
        --text-col keywords \
        --output data/graphs/yugioh_oracle_text.edg \
        --threshold 0.80 --top-k 20
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np


def load_cards(csv_path: Path, name_col: str, text_col: str,
               type_col: str | None) -> list[tuple[str, str]]:
    """Load card names and text from CSV."""
    import csv

    cards = []
    seen = set()
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get(name_col, '').strip()
            if not name or name in seen:
                continue
            seen.add(name)

            # Build text from available fields
            parts = [name]
            if type_col and row.get(type_col):
                parts.append(row[type_col].strip())
            text = row.get(text_col, '').strip()
            if text and text != 'nan':
                parts.append(text)

            full_text = '. '.join(parts)
            if len(full_text) > len(name) + 5:  # Has meaningful text beyond name
                cards.append((name, full_text))

    return cards


def embed_cards(texts: list[str], model_name: str, batch_size: int = 256) -> np.ndarray:
    """Batch-embed card texts using sentence-transformers."""
    from sentence_transformers import SentenceTransformer

    print(f"Loading model: {model_name}")
    model = SentenceTransformer(model_name)

    print(f"Embedding {len(texts)} cards (batch_size={batch_size})...")
    t0 = time.time()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,  # Pre-normalize for cosine = dot product
    )
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s ({len(texts)/elapsed:.0f} cards/sec)")
    return embeddings


def find_similar_pairs(
    names: list[str],
    embeddings: np.ndarray,
    threshold: float,
    top_k: int,
    chunk_size: int = 1000,
) -> list[tuple[str, str, float]]:
    """Find pairs above threshold using chunked matrix multiplication."""
    n = len(names)
    pairs = []
    print(f"Computing pairwise similarities ({n} cards, chunks of {chunk_size})...")
    t0 = time.time()

    for i in range(0, n, chunk_size):
        chunk_end = min(i + chunk_size, n)
        # Dot product of normalized vectors = cosine similarity
        sims = embeddings[i:chunk_end] @ embeddings.T  # (chunk, n)

        for local_idx in range(chunk_end - i):
            global_idx = i + local_idx
            row = sims[local_idx]

            # Zero out self and already-processed pairs (lower triangle)
            row[:global_idx + 1] = -1

            # Get top-K indices above threshold
            if top_k < n:
                # Partial sort for efficiency
                top_indices = np.argpartition(row, -top_k)[-top_k:]
                top_indices = top_indices[row[top_indices] >= threshold]
            else:
                top_indices = np.where(row >= threshold)[0]

            for j in top_indices:
                score = float(row[j])
                if score >= threshold:
                    pairs.append((names[global_idx], names[int(j)], score))

        if (i // chunk_size) % 5 == 0:
            elapsed = time.time() - t0
            pct = chunk_end / n * 100
            print(f"  {pct:.0f}% ({chunk_end}/{n}) - {len(pairs):,} pairs so far ({elapsed:.0f}s)")

    elapsed = time.time() - t0
    print(f"  Found {len(pairs):,} pairs in {elapsed:.1f}s")
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate oracle text similarity edges",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--csv", type=Path, required=True,
                        help="Card attributes CSV with text column")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output edgelist (.edg)")
    parser.add_argument("--name-col", default="name",
                        help="Column name for card name (default: name)")
    parser.add_argument("--text-col", default="oracle_text",
                        help="Column name for card text (default: oracle_text)")
    parser.add_argument("--type-col", default="type",
                        help="Column name for card type (default: type)")
    parser.add_argument("--model", default="all-MiniLM-L6-v2",
                        help="Sentence transformer model (default: all-MiniLM-L6-v2)")
    parser.add_argument("--threshold", type=float, default=0.80,
                        help="Cosine similarity threshold for edges (default: 0.80)")
    parser.add_argument("--top-k", type=int, default=20,
                        help="Max neighbors per card (default: 20)")
    parser.add_argument("--weight-scale", type=float, default=5.0,
                        help="Scale factor for edge weights (default: 5.0)")
    parser.add_argument("--batch-size", type=int, default=256,
                        help="Embedding batch size (default: 256)")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Error: CSV not found: {args.csv}")
        return 1

    # Load cards
    cards = load_cards(args.csv, args.name_col, args.text_col, args.type_col)
    print(f"Loaded {len(cards)} cards with text from {args.csv}")

    if len(cards) < 2:
        print("Error: Need at least 2 cards with text")
        return 1

    names = [c[0] for c in cards]
    texts = [c[1] for c in cards]

    # Embed
    embeddings = embed_cards(texts, args.model, args.batch_size)

    # Find similar pairs
    pairs = find_similar_pairs(names, embeddings, args.threshold, args.top_k)

    # Sort by weight descending
    pairs.sort(key=lambda x: -x[2])

    # Stats
    if pairs:
        scores = [p[2] for p in pairs]
        print(f"\nEdge stats:")
        print(f"  Count: {len(pairs):,}")
        print(f"  Score range: [{min(scores):.3f}, {max(scores):.3f}]")
        print(f"  Mean: {np.mean(scores):.3f}, Median: {np.median(scores):.3f}")

        # Unique cards
        unique_cards = set()
        for a, b, _ in pairs:
            unique_cards.add(a)
            unique_cards.add(b)
        print(f"  Unique cards: {len(unique_cards):,}")
    else:
        print("\nNo pairs found above threshold. Try lowering --threshold.")
        return 0

    # Write edgelist
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, 'w') as f:
        for c1, c2, score in pairs:
            weight = score * args.weight_scale
            f.write(f"{c1}\t{c2}\t{weight:.4f}\n")

    print(f"\nWritten {len(pairs):,} edges to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
