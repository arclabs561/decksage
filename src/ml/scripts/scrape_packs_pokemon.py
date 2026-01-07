#!/usr/bin/env python3
"""
Scrape Pokemon TCG pack/booster/starter deck information from TCGdx API.

Uses TCGdx API: https://api.tcgdx.net/v2
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

TCGDX_API_BASE = "https://api.tcgdx.net/v2"
MIN_DELAY = 0.1  # Rate limiting


def scrape_pokemon_packs(
    pack_db: PackDatabase,
    limit: int | None = None,
) -> dict[str, int]:
    """
    Scrape Pokemon pack information from TCGdx API.
    
    Args:
        pack_db: PackDatabase instance
        limit: Maximum number of packs to scrape
    
    Returns:
        Statistics dict
    """
    if not HAS_REQUESTS:
        logger.error("requests library not available")
        return {"packs_scraped": 0, "cards_added": 0}
    
    logger.info("Scraping Pokemon packs from TCGdx API...")
    
    # TCGdx v2: Get sets for English (en)
    try:
        time.sleep(MIN_DELAY)
        response = requests.get(f"{TCGDX_API_BASE}/en/sets", timeout=30)
        response.raise_for_status()
        sets_data = response.json()
    except Exception as e:
        logger.error(f"Failed to fetch sets: {e}")
        return {"packs_scraped": 0, "cards_added": 0}
    
    if not isinstance(sets_data, list):
        logger.error("Invalid response format from TCGdx")
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
        set_code = set_data.get("id")  # TCGdx uses ID as code
        
        if not set_id:
            continue
        
        # Determine pack type from set name/ID
        pack_type = "booster"  # Default
        set_name_lower = (set_name or "").lower()
        if "starter" in set_name_lower or "theme" in set_name_lower:
            pack_type = "starter"
        elif "elite" in set_name_lower or "premium" in set_name_lower:
            pack_type = "premium"
        
        # Get release date
        release_date = set_data.get("releaseDate")
        
        # Create pack ID
        pack_id = f"PKM_{set_id}"
        
        # Add pack to database
        pack_db.add_pack(
            pack_id=pack_id,
            game="PKM",
            pack_name=set_name or f"Set {set_id}",
            pack_code=set_code,
            pack_type=pack_type,
            release_date=release_date,
            metadata={
                "tcgdx_id": set_id,
                "logo": set_data.get("logo"),
                "symbol": set_data.get("symbol"),
            },
        )
        
        # Fetch cards in this set
        # Note: TCGdx v2 set endpoint may return cards directly or need separate query
        try:
            time.sleep(MIN_DELAY)
            # Try set detail endpoint first
            set_detail_response = requests.get(
                f"{TCGDX_API_BASE}/en/sets/{set_id}",
                timeout=30
            )
            set_detail_response.raise_for_status()
            set_detail = set_detail_response.json()
            
            # TCGdx set detail may include cards array
            cards = set_detail.get("cards", [])
            
            # If no cards in set detail, try cards endpoint with set filter
            if not cards:
                time.sleep(MIN_DELAY)
                cards_response = requests.get(
                    f"{TCGDX_API_BASE}/en/cards",
                    timeout=30
                )
                cards_response.raise_for_status()
                all_cards = cards_response.json()
                
                if isinstance(all_cards, list):
                    # Filter cards by set_id
                    cards = [
                        card for card in all_cards[:5000]  # Limit for performance
                        if card.get("set", {}).get("id") == set_id
                        or card.get("setId") == set_id
                    ]
        except Exception as e:
            logger.debug(f"Failed to fetch cards for {set_id}: {e}")
            packs_scraped += 1
            continue
        
        if not cards:
            logger.debug(f"No cards found for set {set_id}")
            packs_scraped += 1
            continue
        
        # Batch add cards to pack for better performance
        card_batch = []
        for card in cards:
            card_name = card.get("name") or card.get("localizedName")
            if not card_name:
                continue
            
            card_batch.append({
                "pack_id": pack_id,
                "card_name": card_name,
                "rarity": card.get("rarity"),
                "card_number": card.get("number"),
                "is_foil": False,
                "metadata": {
                    "tcgdx_id": card.get("id"),
                    "image": card.get("image"),
                },
            })
        
        # Batch insert cards
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
    parser = argparse.ArgumentParser(description="Scrape Pokemon packs from TCGdx")
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
    logger.info("Scrape Pokemon Packs from TCGdx")
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

