#!/usr/bin/env python3
"""
Scrape Yu-Gi-Oh! pack/booster/starter deck information from YGOProDeck API.

Uses YGOProDeck API: https://db.ygoprodeck.com/api/v7/cardinfo.php
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

YGOPRODECK_API = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
MIN_DELAY = 0.1  # Rate limiting


def scrape_yugioh_packs(
    pack_db: PackDatabase,
    limit: int | None = None,
) -> dict[str, int]:
    """
    Scrape Yu-Gi-Oh pack information from YGOProDeck API.
    
    Args:
        pack_db: PackDatabase instance
        limit: Maximum number of packs to scrape
    
    Returns:
        Statistics dict
    """
    if not HAS_REQUESTS:
        logger.error("requests library not available")
        return {"packs_scraped": 0, "cards_added": 0}
    
    logger.info("Scraping Yu-Gi-Oh packs from YGOProDeck API...")
    
    # YGOProDeck: Get all cards with set information
    try:
        time.sleep(MIN_DELAY)
        response = requests.get(
            f"{YGOPRODECK_API}?misc=yes",
            timeout=60  # Large response
        )
        response.raise_for_status()
        cards_data = response.json()
    except Exception as e:
        logger.error(f"Failed to fetch cards: {e}")
        return {"packs_scraped": 0, "cards_added": 0}
    
    if "data" not in cards_data:
        logger.error("Invalid response format from YGOProDeck")
        return {"packs_scraped": 0, "cards_added": 0}
    
    cards = cards_data["data"]
    
    # Build pack information from card set data
    packs_dict: dict[str, dict[str, any]] = {}
    seen_pack_codes: set[str] = set()  # Track unique pack codes
    
    for card in cards:
        card_name = card.get("name")
        if not card_name:
            continue
        
        # Get set information
        card_sets = card.get("card_sets", [])
        if not card_sets:
            continue
        
        for card_set in card_sets:
            set_name = card_set.get("set_name")
            set_code = card_set.get("set_code")
            set_rarity = card_set.get("set_rarity")
            set_price = card_set.get("set_price")
            
            if not set_name:
                continue
            
            # Create pack ID (use set_code if available, otherwise sanitize set_name)
            if set_code:
                pack_id = f"YGO_{set_code}"
            else:
                # Sanitize set_name for pack_id
                sanitized = set_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
                sanitized = "".join(c for c in sanitized if c.isalnum() or c == "_")
                pack_id = f"YGO_{sanitized}"
            
            # Deduplicate by pack_code if available
            if set_code and set_code in seen_pack_codes:
                # Find existing pack with this code
                existing_pack_id = f"YGO_{set_code}"
                if existing_pack_id in packs_dict:
                    pack_id = existing_pack_id
                else:
                    # Shouldn't happen, but handle gracefully
                    pass
            
            if set_code:
                seen_pack_codes.add(set_code)
            
            # Initialize pack if not seen
            if pack_id not in packs_dict:
                # Determine pack type from set name
                pack_type = "booster"  # Default
                set_name_lower = set_name.lower()
                if "starter" in set_name_lower or "structure" in set_name_lower:
                    pack_type = "starter"
                elif "premium" in set_name_lower or "gold" in set_name_lower:
                    pack_type = "premium"
                elif "collection" in set_name_lower:
                    pack_type = "collection"
                
                packs_dict[pack_id] = {
                    "pack_id": pack_id,
                    "pack_name": set_name,
                    "pack_code": set_code,
                    "pack_type": pack_type,
                    "cards": [],
                }
            
            # Add card to pack (avoid duplicates)
            existing_card_names = {c["card_name"] for c in packs_dict[pack_id]["cards"]}
            if card_name not in existing_card_names:
                packs_dict[pack_id]["cards"].append({
                    "card_name": card_name,
                    "rarity": set_rarity,
                    "card_number": card_set.get("set_number"),
                    "metadata": {
                        "set_price": set_price,
                    },
                })
    
    # Limit if specified
    if limit:
        packs_dict = dict(list(packs_dict.items())[:limit])
    
    logger.info(f"Found {len(packs_dict)} packs to process")
    
    packs_scraped = 0
    cards_added = 0
    
    for pack_id, pack_data in packs_dict.items():
        # Add pack to database
        pack_db.add_pack(
            pack_id=pack_id,
            game="YGO",
            pack_name=pack_data["pack_name"],
            pack_code=pack_data["pack_code"],
            pack_type=pack_data["pack_type"],
        )
        
        # Batch add cards to pack for better performance
        card_batch = []
        for card_data in pack_data["cards"]:
            card_batch.append({
                "pack_id": pack_id,
                "card_name": card_data["card_name"],
                "rarity": card_data["rarity"],
                "card_number": card_data["card_number"],
                "is_foil": False,
                "metadata": card_data.get("metadata"),
            })
        
        # Batch insert cards
        if card_batch:
            added = pack_db.add_pack_cards_batch(card_batch)
            cards_added += added
        
        packs_scraped += 1
        
        if packs_scraped % 10 == 0:
            logger.info(f"  Processed {packs_scraped}/{len(packs_dict)} packs...")
    
    logger.info(f"Scraped {packs_scraped} packs, added {cards_added} card-pack relationships")
    
    return {
        "packs_scraped": packs_scraped,
        "cards_added": cards_added,
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Scrape Yu-Gi-Oh packs from YGOProDeck")
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
    logger.info("Scrape Yu-Gi-Oh Packs from YGOProDeck")
    logger.info("=" * 70)
    
    pack_db = PackDatabase(args.db_path)
    
    results = scrape_yugioh_packs(
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

