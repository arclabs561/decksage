# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "pecanpy>=2.0.0", "numpy>=1.26.0"]
# ///
"""Sweep ns_exponent for Word2Vec training on deck co-occurrence graph.

Hamilton lens: "The negative sampling distribution should be positively but
sub-linearly correlated to their positive sampling distribution. degree^0.75
from word2vec is a special case." -- Yang et al., KDD 2020

Default ns_exponent=0.75 is optimal for NLP word frequency distributions
but may not be optimal for card co-occurrence graphs (power-law degree
distribution). This sweep tests [-1.0, -0.5, 0.0, 0.5, 0.75, 1.0].

Usage:
    uv run scripts/sweep_ns_exponent.py --game magic --dim 128
    uv run scripts/sweep_ns_exponent.py --game magic --dim 128 --dry-run
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


NS_EXPONENTS = [-1.0, -0.5, 0.0, 0.5, 0.75, 1.0]


def run_sweep(game: str, dim: int, window: int, epochs: int, dry_run: bool) -> None:
    from gensim.models import Word2Vec

    corpus_path = Path(f"data/decks/collections_{game}.csv")
    if not corpus_path.exists():
        print(f"Corpus not found: {corpus_path}")
        sys.exit(1)

    # Load corpus: each line is a "deck" (space-separated card names)
    print(f"Loading corpus: {corpus_path}")
    sentences = []
    with open(corpus_path) as f:
        for line in f:
            cards = line.strip().split(",")
            if len(cards) > 1:
                sentences.append(cards)
    print(f"  {len(sentences)} decks loaded")

    results = []
    for ns_exp in NS_EXPONENTS:
        label = f"ns_exp={ns_exp:+.1f}"
        out_path = Path(f"data/embeddings/{game}_ns{ns_exp:+.1f}_{dim}d.wv")

        if dry_run:
            print(f"[dry-run] Would train: {label} -> {out_path}")
            continue

        print(f"\n{'=' * 60}")
        print(f"Training: {label}")
        t0 = time.monotonic()

        model = Word2Vec(
            sentences=sentences,
            vector_size=dim,
            window=window,
            min_count=2,
            sg=1,  # Skip-gram
            ns_exponent=ns_exp,
            epochs=epochs,
            workers=4,
            seed=42,
        )

        elapsed = time.monotonic() - t0
        vocab_size = len(model.wv)
        model.wv.save(str(out_path))

        print(f"  vocab={vocab_size}, dim={dim}, time={elapsed:.1f}s")
        print(f"  saved: {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")

        results.append(
            {
                "ns_exponent": ns_exp,
                "vocab": vocab_size,
                "time_s": round(elapsed, 1),
                "path": str(out_path),
            }
        )

    if not dry_run and results:
        print(f"\n{'=' * 60}")
        print("Sweep complete. Run degree-stratified evaluation on each:")
        print()
        for r in results:
            print(f"  uv run scripts/eval_degree_stratified.py --game {game} --emb {r['path']}")


def main():
    parser = argparse.ArgumentParser(description="Sweep ns_exponent for Word2Vec training")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would run without training"
    )
    args = parser.parse_args()

    run_sweep(args.game, args.dim, args.window, args.epochs, args.dry_run)


if __name__ == "__main__":
    main()
