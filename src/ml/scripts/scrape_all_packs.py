#!/usr/bin/env python3
"""
Unified script to scrape packs for all games.

Orchestrates scraping for Magic, Pokemon, and Yu-Gi-Oh.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..data.pack_database import PackDatabase
from ..scripts.scrape_packs_magic import scrape_magic_packs
from ..scripts.scrape_packs_pokemon import scrape_pokemon_packs
from ..scripts.scrape_packs_yugioh import scrape_yugioh_packs
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def scrape_all_packs(
    pack_db: PackDatabase,
    games: list[str] | None = None,
    limit_per_game: int | None = None,
) -> dict[str, dict[str, int]]:
    """
    Scrape packs for all games.
    
    Args:
        pack_db: PackDatabase instance
        games: List of games to scrape (default: all)
        limit_per_game: Maximum packs per game
    
    Returns:
        Results dict by game
    """
    if games is None:
        games = ["MTG", "PKM", "YGO"]
    
    results = {}
    
    for game in games:
        logger.info("=" * 70)
        logger.info(f"Scraping {game} packs...")
        logger.info("=" * 70)
        
        if game == "MTG":
            result = scrape_magic_packs(pack_db, limit=limit_per_game)
        elif game == "PKM":
            result = scrape_pokemon_packs(pack_db, limit=limit_per_game)
        elif game == "YGO":
            result = scrape_yugioh_packs(pack_db, limit=limit_per_game)
        else:
            logger.warning(f"Unknown game: {game}, skipping")
            continue
        
        results[game] = result
    
    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Scrape packs for all games")
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Path to pack database (default: data/packs.db)",
    )
    parser.add_argument(
        "--games",
        nargs="+",
        choices=["MTG", "PKM", "YGO"],
        help="Games to scrape (default: all)",
    )
    parser.add_argument(
        "--limit-per-game",
        type=int,
        help="Maximum packs per game",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Scrape Packs for All Games")
    logger.info("=" * 70)
    
    pack_db = PackDatabase(args.db_path)
    
    results = scrape_all_packs(
        pack_db,
        games=args.games,
        limit_per_game=args.limit_per_game,
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
    
    logger.info("\n" + "=" * 70)
    logger.info("Results by Game")
    logger.info("=" * 70)
    for game, result in results.items():
        logger.info(f"{game}: {result}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

