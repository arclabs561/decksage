#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sentence-transformers>=2.2.0",
#     "transformers>=4.40.0",
#     "torch>=2.0.0",
#     "numpy>=1.24.0",
#     "pandas>=2.0.0",
#     "pillow>=10.0.0",
#     "requests>=2.31.0",
#     "tqdm>=4.65.0",
#     "sentencepiece>=0.1.99",
#     "protobuf>=4.0.0",
# ]
# ///
"""
Pre-encode all card images with SigLIP visual embeddings.

Builds a numpy matrix of visual embeddings for the full card catalog,
enabling visual-based candidate generation in fusion (same pattern as
text embedding indices).

Downloads all card images (with caching), then batch-embeds with SigLIP.
Output goes to data/cache/visual_embeddings/{game}_embeddings.npy.

Usage:
    uv run scripts/training/build_visual_embedding_index.py --game magic
    uv run scripts/training/build_visual_embedding_index.py --game magic --download-only
    uv run scripts/training/build_visual_embedding_index.py --all-games
    uv run scripts/training/build_visual_embedding_index.py --all-games --download-workers 16
"""

from __future__ import annotations

import argparse
import hashlib
import io
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

IMAGE_CACHE_DIR = Path(".cache") / "card_images"
OUTPUT_DIR = DATA_DIR / "cache" / "visual_embeddings"


def load_card_catalog(game: str) -> list[dict]:
    """Load all cards with image URLs from enriched CSV."""
    path = DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        path = DATA_DIR / "processed" / f"card_attributes_{game}.csv"
    if not path.exists():
        log.error(f"No card attributes found for {game}")
        return []

    df = pd.read_csv(path, low_memory=False)
    cards = []
    for _, row in df.iterrows():
        name = str(row.get("name", ""))
        if not name:
            continue
        image_url = str(row.get("image_url", ""))
        if not image_url or image_url == "nan":
            continue
        cards.append({"name": name, "image_url": image_url})
    return cards


def _get_image_path(url: str) -> Path:
    """Get cache path for an image URL."""
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    return IMAGE_CACHE_DIR / f"{url_hash}.png"


def _download_single(args: tuple) -> tuple[str, bool]:
    """Download a single image. Returns (name, success)."""
    import requests
    from PIL import Image

    name, url, cache_path = args
    if cache_path.exists():
        return name, True

    try:
        headers = {"User-Agent": "DeckSage/1.0 (https://decksage.com)"}
        resp = requests.get(url, timeout=15, headers=headers)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        img.save(str(cache_path), "PNG")
        return name, True
    except Exception:
        return name, False


def download_all_images(
    cards: list[dict],
    workers: int = 8,
) -> tuple[int, int]:
    """Download all card images in parallel. Returns (success, failed)."""
    IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    tasks = []
    for card in cards:
        path = _get_image_path(card["image_url"])
        if not path.exists():
            tasks.append((card["name"], card["image_url"], path))

    already_cached = len(cards) - len(tasks)
    if already_cached:
        log.info(f"  {already_cached:,} images already cached")

    if not tasks:
        return len(cards), 0

    log.info(f"  Downloading {len(tasks):,} images with {workers} workers...")
    success = already_cached
    failed = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_download_single, t): t[0] for t in tasks}
        done = 0
        for future in as_completed(futures):
            done += 1
            _name, ok = future.result()
            if ok:
                success += 1
            else:
                failed += 1
            if done % 500 == 0 or done == len(tasks):
                log.info(f"    {done:,}/{len(tasks):,} downloaded ({success} ok, {failed} failed)")

    return success, failed


def build_visual_index(game: str, download_workers: int = 8) -> None:
    """Build visual embedding index for a game."""
    from PIL import Image

    cards = load_card_catalog(game)
    if not cards:
        return

    log.info(f"\n{'=' * 60}")
    log.info(f"{game.upper()}: {len(cards):,} cards with image URLs")
    log.info(f"{'=' * 60}")

    # Phase 1: Download images
    log.info("\nPhase 1: Downloading images...")
    t0 = time.time()
    success, failed = download_all_images(cards, workers=download_workers)
    log.info(f"  Downloaded in {time.time() - t0:.0f}s: {success:,} ok, {failed:,} failed")

    if success == 0:
        log.error("  No images downloaded, skipping embedding")
        return

    # Phase 2: Load SigLIP and embed
    log.info("\nPhase 2: Embedding with SigLIP...")
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder
    except ImportError:
        log.error("Could not import CardVisualEmbedder. Make sure src/ is in PYTHONPATH.")
        return

    sys.stdout.flush()
    log.info("  Loading SigLIP model (first run downloads ~800MB)...")
    sys.stdout.flush()
    embedder = CardVisualEmbedder(model_name="google/siglip2-so400m-patch16-384")
    log.info(f"  Model loaded: SigLIP (dim={embedder._embedding_dim})")
    sys.stdout.flush()

    # Batch embed all cards
    embeddings = np.zeros((len(cards), embedder._embedding_dim), dtype=np.float32)
    card_names = []
    skipped = 0
    batch_size = 64

    t0 = time.time()
    for i in range(0, len(cards), batch_size):
        batch = cards[i : i + batch_size]
        batch_images = []
        batch_indices = []

        for j, card in enumerate(batch):
            img_path = _get_image_path(card["image_url"])
            if img_path.exists():
                try:
                    img = Image.open(str(img_path)).convert("RGB")
                    batch_images.append(img)
                    batch_indices.append(i + j)
                except Exception:
                    skipped += 1
            else:
                skipped += 1
            card_names.append(card["name"])

        # Batch embed all loaded images at once (10-20x faster than one-by-one)
        if batch_images:
            try:
                batch_embs = embedder.embed_batch(batch_images)
                for k, idx in enumerate(batch_indices):
                    embeddings[idx] = batch_embs[k]
            except Exception as e:
                log.warning(f"Batch embed failed at {i}: {e}")
                for idx in batch_indices:
                    embeddings[idx] = np.zeros(embedder._embedding_dim, dtype=np.float32)
                    skipped += 1

        done = min(i + batch_size, len(cards))
        if done % 500 == 0 or done == len(cards):
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta = (len(cards) - done) / rate if rate > 0 else 0
            log.info(f"    {done:,}/{len(cards):,} embedded ({rate:.0f}/s, ETA {eta:.0f}s)")
            sys.stdout.flush()

    elapsed = time.time() - t0
    log.info(f"  Embedded in {elapsed:.0f}s ({len(cards) / elapsed:.0f} cards/s)")
    if skipped:
        log.info(f"  {skipped:,} cards skipped (no image or embed failed)")

    # L2 normalize for cosine similarity via dot product
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    embeddings = (embeddings / norms).astype(np.float32)

    # Phase 3: Save
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    np.save(OUTPUT_DIR / f"{game}_embeddings.npy", embeddings)
    with open(OUTPUT_DIR / f"{game}_names.txt", "w") as f:
        for name in card_names:
            f.write(name + "\n")

    mb = embeddings.nbytes / 1024 / 1024
    log.info(f"\nSaved: {OUTPUT_DIR}/{game}_embeddings.npy ({mb:.1f} MB)")
    log.info(f"       {OUTPUT_DIR}/{game}_names.txt ({len(card_names):,} names)")
    log.info(
        f"       Non-zero: {np.count_nonzero(embeddings) // embedder._embedding_dim:,}/{len(cards):,} cards"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build visual embedding index")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--download-workers", type=int, default=8)
    parser.add_argument(
        "--download-only", action="store_true", help="Only download images, skip embedding"
    )
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    for game in games:
        if args.download_only:
            cards = load_card_catalog(game)
            if cards:
                log.info(f"\n{game}: Downloading {len(cards):,} images...")
                s, f = download_all_images(cards, workers=args.download_workers)
                log.info(f"  Done: {s} ok, {f} failed")
        else:
            build_visual_index(game, download_workers=args.download_workers)

    return 0


if __name__ == "__main__":
    sys.exit(main())
