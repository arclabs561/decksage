#!/usr/bin/env python3
"""
Scrape Pokemon TCG pack/booster/starter deck information.

Uses pokemontcg-data GitHub repo (raw JSON):
  - Sets:  https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/sets/en.json
  - Cards: https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/cards/en/{set_id}.json
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path


try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from ..data.pack_database import PackDatabase
from ..utils.logging_config import setup_script_logging


logger = setup_script_logging()

GITHUB_RAW_BASE = "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master"
SETS_URL = f"{GITHUB_RAW_BASE}/sets/en.json"
MIN_DELAY = 0.1  # Rate limiting (polite to GitHub CDN)


def scrape_pokemon_packs(
    pack_db: PackDatabase,
    limit: int | None = None,
) -> dict[str, int]:
    """
    Scrape Pokemon pack information from pokemontcg-data GitHub repo.

    Args:
        pack_db: PackDatabase instance
        limit: Maximum number of packs to scrape

    Returns:
        Statistics dict
    """
    if not HAS_REQUESTS:
        logger.error("requests library not available")
        return {"packs_scraped": 0, "cards_added": 0}

    logger.info("Scraping Pokemon packs from pokemontcg-data GitHub repo...")

    # Fetch set index
    try:
        time.sleep(MIN_DELAY)
        response = requests.get(SETS_URL, timeout=30)
        response.raise_for_status()
        sets_data = response.json()
    except Exception as e:
        logger.error(f"Failed to fetch sets: {e}")
        return {"packs_scraped": 0, "cards_added": 0}

    if not isinstance(sets_data, list):
        logger.error("Invalid response format from pokemontcg-data")
        return {"packs_scraped": 0, "cards_added": 0}

    # Limit if specified
    if limit:
        sets_data = sets_data[:limit]

    logger.info(f"Found {len(sets_data)} sets to process")

    packs_scraped = 0
    cards_added = 0

    for i, set_data in enumerate(sets_data):
        set_id = set_data.get("id")
        set_name = set_data.get("name")
        set_code = set_data.get("ptcgoCode") or set_id

        if not set_id:
            continue

        # Determine pack type from set name/series
        pack_type = "booster"  # Default
        set_name_lower = (set_name or "").lower()
        series_lower = (set_data.get("series") or "").lower()
        if "starter" in set_name_lower or "theme" in set_name_lower:
            pack_type = "starter"
        elif "elite" in set_name_lower or "premium" in set_name_lower:
            pack_type = "premium"
        elif "promo" in set_name_lower or "promo" in series_lower:
            pack_type = "promo"

        release_date = set_data.get("releaseDate")

        pack_id = f"PKM_{set_id}"

        pack_db.add_pack(
            pack_id=pack_id,
            game="PKM",
            pack_name=set_name or f"Set {set_id}",
            pack_code=set_code,
            pack_type=pack_type,
            release_date=release_date,
            card_count=set_data.get("total"),
            metadata={
                "series": set_data.get("series"),
                "printedTotal": set_data.get("printedTotal"),
                "legalities": set_data.get("legalities"),
            },
        )

        # Fetch cards for this set from GitHub
        cards_url = f"{GITHUB_RAW_BASE}/cards/en/{set_id}.json"
        try:
            time.sleep(MIN_DELAY)
            cards_response = requests.get(cards_url, timeout=30)
            cards_response.raise_for_status()
            cards = cards_response.json()
        except Exception as e:
            logger.debug(f"Failed to fetch cards for {set_id}: {e}")
            packs_scraped += 1
            continue

        if not isinstance(cards, list) or not cards:
            logger.debug(f"No cards found for set {set_id}")
            packs_scraped += 1
            continue

        # Batch add cards
        card_batch = []
        for card in cards:
            card_name = card.get("name")
            if not card_name:
                continue

            card_batch.append(
                {
                    "pack_id": pack_id,
                    "card_name": card_name,
                    "rarity": card.get("rarity"),
                    "card_number": card.get("number"),
                    "is_foil": False,
                    "metadata": None,
                }
            )

        if card_batch:
            added = pack_db.add_pack_cards_batch(card_batch)
            cards_added += added

        packs_scraped += 1

        if (i + 1) % 10 == 0:
            logger.info(f"  Processed {i + 1}/{len(sets_data)} packs...")

    logger.info(f"Scraped {packs_scraped} packs, added {cards_added} card-pack relationships")

    return {
        "packs_scraped": packs_scraped,
        "cards_added": cards_added,
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Scrape Pokemon packs from pokemontcg-data")
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Path to pack database (default: data/packs.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of packs to scrape",
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Scrape Pokemon Packs from pokemontcg-data")
    logger.info("=" * 70)

    pack_db = PackDatabase(args.db_path)

    results = scrape_pokemon_packs(
        pack_db,
        limit=args.limit,
    )

    # Print statistics
    stats = pack_db.get_statistics()
    logger.info("\n" + "=" * 70)
    logger.info("Pack Database Statistics")
    logger.info("=" * 70)
    logger.info(f"Total packs: {stats['total_packs']}")
    logger.info(f"Packs by game: {stats['packs_by_game']}")
    logger.info(f"Packs by type: {stats['packs_by_type']}")
    logger.info(f"Total pack-card relationships: {stats['total_pack_cards']}")
    logger.info(f"Unique cards in packs: {stats['unique_cards']}")

    logger.info(f"\n✓ Results: {results}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
