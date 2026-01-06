#!/usr/bin/env python3
"""
Update card data with image URLs from Scryfall API.

Part of the standard data processing pipeline. Enriches card_attributes_enriched.csv
with image URLs for visual embeddings.

This script:
1. Reads card names from card_attributes CSV
2. Fetches image URLs from Scryfall API (with rate limiting)
3. Updates card data with image URLs (in-place or to new file)
4. Creates a mapping file for visual embeddings

Integrates with:
- Data lineage Order 0-1: Card attributes enrichment
- Visual embeddings pipeline: Provides image URLs for CardVisualEmbedder
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.path_setup import setup_project_paths
    setup_project_paths()
except ImportError:
    src_path = project_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.path_setup import setup_project_paths
    setup_project_paths()
except ImportError:
    src_path = project_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))

try:
    import pandas as pd
    import requests
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def get_scryfall_image_url(card_name: str, retry_delay: float = 0.1) -> str | None:
    """
    Get image URL from Scryfall API for a card name.
    
    Args:
        card_name: Card name to look up
        retry_delay: Delay between API calls (Scryfall rate limit: 50-100ms)
    
    Returns:
        Image URL or None if not found
    """
    if not HAS_DEPS:
        logger.error("pandas and requests required")
        return None
    
    # Scryfall API endpoint for named card
    url = "https://api.scryfall.com/cards/named"
    params = {"exact": card_name, "format": "json"}
    
    try:
        time.sleep(retry_delay)  # Rate limiting
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract image URL (prefer PNG, fallback to large/normal)
        if "image_uris" in data:
            image_uris = data["image_uris"]
            return image_uris.get("png") or image_uris.get("large") or image_uris.get("normal")
        
        # Handle multi-faced cards (DFCs)
        if "card_faces" in data and len(data["card_faces"]) > 0:
            face = data["card_faces"][0]
            if "image_uris" in face:
                image_uris = face["image_uris"]
                return image_uris.get("png") or image_uris.get("large") or image_uris.get("normal")
        
        return None
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.debug(f"Card not found in Scryfall: {card_name}")
        else:
            logger.warning(f"HTTP error for {card_name}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Error fetching image URL for {card_name}: {e}")
        return None


def update_card_data_with_images(
    card_attrs_path: Path,
    output_path: Path | None = None,
    limit: int | None = None,
    sample_size: int | None = None,
) -> dict[str, Any]:
    """
    Update card data with image URLs from Scryfall.
    
    Args:
        card_attrs_path: Path to card_attributes CSV
        output_path: Path to save updated CSV (default: add _with_images suffix)
        limit: Maximum number of cards to process (None = all)
        sample_size: Random sample size (None = no sampling)
    
    Returns:
        Statistics dict
    """
    if not HAS_DEPS:
        logger.error("pandas and requests required")
        return {"error": "Missing dependencies"}
    
    logger.info(f"Loading card data from {card_attrs_path}...")
    df = pd.read_csv(card_attrs_path, nrows=limit)
    logger.info(f"  Loaded {len(df)} cards")
    
    # Sample if requested
    if sample_size and len(df) > sample_size:
        import random
        random.seed(42)
        df = df.sample(n=sample_size, random_state=42)
        logger.info(f"  Sampled {len(df)} cards")
    
    # Check if image_url column exists
    if "image_url" not in df.columns:
        df["image_url"] = None
    
    # Fetch image URLs
    logger.info("Fetching image URLs from Scryfall API...")
    logger.info("  (This may take a while due to rate limiting...)")
    
    fetched = 0
    failed = 0
    already_had = 0
    
    for idx, row in df.iterrows():
        card_name = str(row["name"])
        
        # Skip if already has image URL
        if pd.notna(row.get("image_url")) and str(row["image_url"]).strip():
            already_had += 1
            continue
        
        # Fetch from Scryfall
        image_url = get_scryfall_image_url(card_name)
        
        if image_url:
            df.at[idx, "image_url"] = image_url
            fetched += 1
        else:
            failed += 1
        
        if (fetched + failed) % 50 == 0:
            logger.info(f"  Progress: {fetched} fetched, {failed} failed, {already_had} already had URLs")
    
    logger.info(f"  Complete: {fetched} fetched, {failed} failed, {already_had} already had URLs")
    
    # Save updated CSV
    if output_path is None:
        output_path = card_attrs_path.parent / f"{card_attrs_path.stem}_with_images.csv"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info(f"Saved updated card data to {output_path}")
    
    # Create JSON mapping for quick lookup
    json_path = output_path.parent / f"{card_attrs_path.stem}_image_urls.json"
    image_mapping = {}
    for _, row in df.iterrows():
        card_name = str(row["name"])
        image_url = row.get("image_url")
        if pd.notna(image_url) and str(image_url).strip():
            image_mapping[card_name] = str(image_url)
    
    with open(json_path, "w") as f:
        json.dump(image_mapping, f, indent=2)
    logger.info(f"Saved image URL mapping to {json_path}")
    
    return {
        "total": len(df),
        "fetched": fetched,
        "failed": failed,
        "already_had": already_had,
        "with_images": len(image_mapping),
        "output_csv": str(output_path),
        "output_json": str(json_path),
    }


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Update card data with image URLs from Scryfall"
    )
    parser.add_argument(
        "--card-attrs",
        type=Path,
        default=None,  # Will use PATHS.card_attributes
        help="Path to card_attributes CSV (default: data/processed/card_attributes_enriched.csv)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to save updated CSV (default: add _with_images suffix)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of cards to process (default: all)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        help="Random sample size (default: no sampling)",
    )
    parser.add_argument(
        "--test-set-only",
        action="store_true",
        help="Only update cards in test set",
    )
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        logger.error("pandas and requests required. Install with: uv add pandas requests")
        return 1
    
    # Use canonical path if not provided
    if args.card_attrs is None:
        try:
            from ml.utils.paths import PATHS
            args.card_attrs = PATHS.card_attributes
        except ImportError:
            args.card_attrs = Path("data/processed/card_attributes_enriched.csv")
    
    # If test-set-only, load test set and filter
    if args.test_set_only:
        try:
            from ml.utils.paths import PATHS
            test_set_path = PATHS.test_magic
        except ImportError:
            test_set_path = Path("experiments/test_set_unified_magic.json")
        
        if test_set_path.exists():
            with open(test_set_path) as f:
                test_data = json.load(f)
            queries = test_data.get("queries", test_data)
            test_cards = set(queries.keys())
            logger.info(f"Test set has {len(test_cards)} unique cards")
            # We'll filter after loading
        else:
            logger.warning(f"Test set not found: {test_set_path}")
            args.test_set_only = False
    
    # Update card data (default: update in-place)
    if args.output is None:
        args.output = args.card_attrs  # Update in-place
    
    stats = update_card_data_with_images(
        card_attrs_path=args.card_attrs,
        output_path=args.output,
        limit=args.limit,
        sample_size=args.sample,
    )
    
    if "error" in stats:
        return 1
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("Update Complete")
    logger.info("=" * 60)
    logger.info(f"Total cards: {stats['total']}")
    logger.info(f"Fetched: {stats['fetched']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info(f"Already had: {stats['already_had']}")
    logger.info(f"With images: {stats['with_images']}")
    logger.info(f"Output CSV: {stats['output_csv']}")
    logger.info(f"Output JSON: {stats['output_json']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

