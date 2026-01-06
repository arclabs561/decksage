#!/usr/bin/env python3
"""
Collect card images for fine-tuning visual embeddings.

Downloads card images from Scryfall/Riftcodex/YGOPRODeck and organizes them
for fine-tuning SigLIP 2 on trading card datasets.

Usage:
    python scripts/data/collect_card_images.py --game magic --output data/card_images/magic
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import requests
except ImportError:
    requests = None
    logger.error("requests not installed. Install with: uv add requests")

try:
    from PIL import Image
except ImportError:
    Image = None
    logger.error("PIL/Pillow not installed. Install with: uv add pillow")


def load_card_data(game: str) -> list[dict[str, Any]]:
    """
    Load card data from backend blob storage.

    Args:
        game: Game name ('magic', 'pokemon', 'yugioh', 'riftbound')

    Returns:
        List of card dicts with image URLs
    """
    # This would need to be adapted to your actual data loading mechanism
    # For now, this is a placeholder that shows the structure
    logger.warning("Card data loading not implemented - adapt to your data source")
    return []


def download_image(url: str, output_path: Path, max_retries: int = 3) -> bool:
    """
    Download image from URL.

    Args:
        url: Image URL
        output_path: Path to save image
        max_retries: Maximum retry attempts

    Returns:
        True if successful, False otherwise
    """
    if requests is None:
        logger.error("requests not available")
        return False

    if output_path.exists():
        logger.debug(f"Image already exists: {output_path}")
        return True

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10, stream=True)
            response.raise_for_status()

            # Save image
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Verify it's a valid image
            if Image is not None:
                try:
                    img = Image.open(output_path)
                    img.verify()
                except Exception as e:
                    logger.warning(f"Invalid image file {output_path}: {e}")
                    output_path.unlink()
                    return False

            logger.debug(f"Downloaded: {output_path}")
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                logger.debug(f"Download failed (attempt {attempt + 1}/{max_retries}): {e}")
            else:
                logger.warning(f"Failed to download {url} after {max_retries} attempts: {e}")
                return False

    return False


def collect_images(
    game: str,
    output_dir: Path,
    limit: int | None = None,
    card_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Collect card images for a game.

    Args:
        game: Game name
        output_dir: Output directory for images
        limit: Maximum number of images to download (None = all)
        card_data: Optional pre-loaded card data

    Returns:
        Statistics dict
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load card data
    if card_data is None:
        card_data = load_card_data(game)

    if not card_data:
        logger.warning(f"No card data found for {game}")
        return {"total": 0, "downloaded": 0, "failed": 0}

    # Create metadata file
    metadata = []

    total = len(card_data) if limit is None else min(limit, len(card_data))
    downloaded = 0
    failed = 0

    logger.info(f"Collecting images for {total} cards...")

    for i, card in enumerate(card_data[:total]):
        card_name = card.get("name", f"card_{i}")
        image_url = None

        # Extract image URL (same logic as visual_embeddings.py)
        if "image_url" in card:
            image_url = card["image_url"]
        elif "image" in card:
            image_url = card["image"]
        elif "images" in card:
            images = card["images"]
            if isinstance(images, list) and len(images) > 0:
                if isinstance(images[0], dict):
                    image_url = images[0].get("url") or images[0].get("URL")
                else:
                    image_url = images[0]
            elif isinstance(images, dict):
                image_url = images.get("large") or images.get("png") or images.get("url")

        if not image_url:
            logger.debug(f"No image URL for card: {card_name}")
            failed += 1
            continue

        # Sanitize card name for filename
        safe_name = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in card_name)
        safe_name = safe_name.replace(" ", "_").lower()
        image_path = output_dir / f"{safe_name}.png"

        # Download image
        if download_image(image_url, image_path):
            downloaded += 1
            metadata.append(
                {
                    "card_name": card_name,
                    "image_url": image_url,
                    "image_path": str(image_path.relative_to(output_dir)),
                    "game": game,
                }
            )
        else:
            failed += 1

        if (i + 1) % 100 == 0:
            logger.info(f"Progress: {i + 1}/{total} ({downloaded} downloaded, {failed} failed)")

    # Save metadata
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    stats = {
        "total": total,
        "downloaded": downloaded,
        "failed": failed,
        "metadata_file": str(metadata_path),
    }

    logger.info(
        f"Collection complete: {downloaded}/{total} downloaded, {failed} failed. "
        f"Metadata saved to {metadata_path}"
    )

    return stats


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Collect card images for fine-tuning")
    parser.add_argument(
        "--game",
        required=True,
        choices=["magic", "pokemon", "yugioh", "riftbound"],
        help="Game to collect images for",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory for images",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of images to download (default: all)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if requests is None:
        logger.error("requests not installed. Install with: uv add requests")
        return 1

    if Image is None:
        logger.error("PIL/Pillow not installed. Install with: uv add pillow")
        return 1

    try:
        stats = collect_images(args.game, args.output, limit=args.limit)
        print(f"\nCollection Statistics:")
        print(f"  Total cards: {stats['total']}")
        print(f"  Downloaded: {stats['downloaded']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Metadata: {stats['metadata_file']}")
        return 0
    except Exception as e:
        logger.exception(f"Collection failed: {e}")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())

