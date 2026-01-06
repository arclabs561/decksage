#!/usr/bin/env python3
"""
Scrape Magic: The Gathering pack/booster/starter deck information from Scryfall.

Uses Scryfall Sets API: https://api.scryfall.com/sets
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

SCRYFALL_SETS_API = "https://api.scryfall.com/sets"
SCRYFALL_CARDS_API = "https://api.scryfall.com/cards/search"
MIN_DELAY = 0.1  # Rate limiting


def scrape_magic_packs(
    pack_db: PackDatabase,
    pack_types: list[str] | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """
    Scrape Magic pack information from Scryfall.
    
    Args:
        pack_db: PackDatabase instance
        pack_types: Filter by pack types (e.g., ['booster', 'starter'])
        limit: Maximum number of packs to scrape
    
    Returns:
        Statistics dict
    """
    if not HAS_REQUESTS:
        logger.error("requests library not available")
        return {"packs_scraped": 0, "cards_added": 0}
    
    logger.info("Scraping Magic packs from Scryfall...")
    
    # Get all sets
    try:
        time.sleep(MIN_DELAY)
        response = requests.get(SCRYFALL_SETS_API, timeout=30)
        response.raise_for_status()
        sets_data = response.json()
    except Exception as e:
        logger.error(f"Failed to fetch sets: {e}")
        return {"packs_scraped": 0, "cards_added": 0}
    
    if "data" not in sets_data:
        logger.error("Invalid response format from Scryfall")
        return {"packs_scraped": 0, "cards_added": 0}
    
    sets_list = sets_data["data"]
    
    # Filter by pack types if specified
    if pack_types:
        sets_list = [
            s for s in sets_list
            if s.get("set_type") in pack_types
        ]
    
    # Limit if specified
    if limit:
        sets_list = sets_list[:limit]
    
    logger.info(f"Found {len(sets_list)} sets to process")
    
    packs_scraped = 0
    cards_added = 0
    
    for i, set_data in enumerate(sets_list):
        set_code = set_data.get("code")
        set_name = set_data.get("name")
        set_type = set_data.get("set_type")
        release_date = set_data.get("released_at")
        card_count = set_data.get("card_count")
        
        if not set_code:
            continue
        
        # Create pack ID
        pack_id = f"MTG_{set_code}"
        
        # Add pack to database
        pack_db.add_pack(
            pack_id=pack_id,
            game="MTG",
            pack_name=set_name or f"Set {set_code}",
            pack_code=set_code,
            pack_type=set_type,
            release_date=release_date,
            card_count=card_count,
            metadata={
                "scryfall_id": set_data.get("id"),
                "mtgo_code": set_data.get("mtgo_code"),
                "tcgplayer_id": set_data.get("tcgplayer_id"),
                "parent_set_code": set_data.get("parent_set_code"),
                "block": set_data.get("block"),
                "block_code": set_data.get("block_code"),
            },
        )
        
        # Fetch cards in this set (handle pagination)
        all_cards = []
        page = 1
        has_more = True
        
        while has_more:
            try:
                time.sleep(MIN_DELAY)
                url = f"{SCRYFALL_CARDS_API}?q=set:{set_code}&order=set&page={page}"
                cards_response = requests.get(url, timeout=30)
                cards_response.raise_for_status()
                cards_data = cards_response.json()
            except Exception as e:
                logger.debug(f"Failed to fetch cards for {set_code} page {page}: {e}")
                break
            
            if "data" not in cards_data:
                break
            
            all_cards.extend(cards_data["data"])
            
            # Check for next page
            has_more = cards_data.get("has_more", False)
            page += 1
            
            # Safety limit (Scryfall typically has < 500 cards per set)
            if page > 10:
                logger.warning(f"Hit page limit for {set_code}, stopping")
                break
        
        if not all_cards:
            packs_scraped += 1
            continue
        
        # Batch add cards to pack for better performance
        card_batch = []
        for card in all_cards:
            card_name = card.get("name")
            if not card_name:
                continue
            
            # Handle split cards (e.g., "Fire // Ice")
            if "//" in card_name:
                # Add both sides
                sides = [s.strip() for s in card_name.split("//")]
                for side in sides:
                    card_batch.append({
                        "pack_id": pack_id,
                        "card_name": side,
                        "rarity": card.get("rarity"),
                        "card_number": card.get("collector_number"),
                        "is_foil": card.get("foil", False),
                        "metadata": {
                            "full_name": card_name,
                            "is_split": True,
                        },
                    })
            else:
                card_batch.append({
                    "pack_id": pack_id,
                    "card_name": card_name,
                    "rarity": card.get("rarity"),
                    "card_number": card.get("collector_number"),
                    "is_foil": card.get("foil", False),
                    "metadata": None,
                })
        
        # Batch insert cards (much faster than individual inserts)
        if card_batch:
            added = pack_db.add_pack_cards_batch(card_batch)
            cards_added += added
        
        packs_scraped += 1
        
        if (i + 1) % 10 == 0:
            logger.info(f"  Processed {i + 1}/{len(sets_list)} packs...")
    
    logger.info(f"Scraped {packs_scraped} packs, added {cards_added} card-pack relationships")
    
    return {
        "packs_scraped": packs_scraped,
        "cards_added": cards_added,
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Scrape Magic packs from Scryfall")
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Path to pack database (default: data/packs.db)",
    )
    parser.add_argument(
        "--pack-types",
        nargs="+",
        choices=["core", "expansion", "masters", "draft_innovation", "commander", 
                 "planechase", "archenemy", "vanguard", "funny", "starter", 
                 "box", "promo", "token", "memorabilia", "alchemy", "minigame"],
        help="Filter by pack types",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of packs to scrape",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Scrape Magic Packs from Scryfall")
    logger.info("=" * 70)
    
    pack_db = PackDatabase(args.db_path)
    
    results = scrape_magic_packs(
        pack_db,
        pack_types=args.pack_types,
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

