#!/usr/bin/env python3
"""
Fix multilingual card names for ALL games.

Unified script that handles:
- Magic: The Gathering (via Scryfall API)
- Pokemon (via TCGdx API - when integrated)
- Yu-Gi-Oh (via YGOProDeck API - when integrated)
- Digimon, One Piece, Riftbound (when APIs available)
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from ..data.card_database import get_card_database
from ..data.multilingual_translations import detect_language
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def fix_all_games_multilingual(
    graph_db: Path,
    min_decks: int = 100,
    limit: int = 100,
    games: list[str] | None = None,
) -> dict[str, any]:
    """
    Fix multilingual card names for all games.
    
    Args:
        graph_db: Path to graph database
        min_decks: Minimum deck count to fix
        limit: Maximum number of cards to query per game
        games: List of game codes to fix (None = all)
        
    Returns:
        Results by game
    """
    logger.info("Fixing multilingual cards for all games...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Get game distribution
    game_counts = conn.execute("""
        SELECT game, COUNT(*) as count
        FROM nodes
        WHERE game IS NOT NULL AND game != 'Unknown'
        GROUP BY game
        ORDER BY count DESC
    """).fetchall()
    
    logger.info("Games in database:")
    for game_code, count in game_counts:
        if game_code:
            logger.info(f"  {game_code}: {count:,} nodes")
    
    results = {}
    
    # Fix Magic cards (complete support)
    logger.info("\n" + "=" * 70)
    logger.info("Fixing Magic: The Gathering cards...")
    logger.info("=" * 70)
    try:
        from .fix_multilingual_cards_with_api import fix_multilingual_cards_with_api
        magic_results = fix_multilingual_cards_with_api(
            graph_db, min_decks=min_decks, limit=limit, languages=None
        )
        results["magic"] = magic_results
    except Exception as e:
        logger.warning(f"Could not fix Magic cards: {e}")
        results["magic"] = {"error": str(e)}
    
    # Fix Pokemon cards
    logger.info("\n" + "=" * 70)
    logger.info("Fixing Pokemon cards...")
    logger.info("=" * 70)
    try:
        from .fix_pokemon_multilingual import fix_pokemon_multilingual
        pokemon_results = fix_pokemon_multilingual(
            graph_db, min_decks=min_decks, limit=limit
        )
        results["pokemon"] = pokemon_results
        if pokemon_results.get("fixed", 0) > 0:
            logger.info(f"✓ Fixed {pokemon_results.get('fixed', 0)} Pokemon cards")
    except Exception as e:
        logger.warning(f"Pokemon multilingual fix failed: {e}")
        results["pokemon"] = {"error": str(e)}
    
    # Fix Yu-Gi-Oh cards
    logger.info("\n" + "=" * 70)
    logger.info("Fixing Yu-Gi-Oh cards...")
    logger.info("=" * 70)
    try:
        from .fix_yugioh_multilingual import fix_yugioh_multilingual
        yugioh_results = fix_yugioh_multilingual(
            graph_db, min_decks=min_decks, limit=limit
        )
        results["yugioh"] = yugioh_results
        if yugioh_results.get("fixed", 0) > 0:
            logger.info(f"✓ Fixed {yugioh_results.get('fixed', 0)} Yu-Gi-Oh cards")
    except Exception as e:
        logger.warning(f"Yu-Gi-Oh multilingual fix failed: {e}")
        results["yugioh"] = {"error": str(e)}
    
    # Digimon, One Piece, Riftbound
    logger.info("\n" + "=" * 70)
    logger.info("Other games (Digimon, One Piece, Riftbound)...")
    logger.info("=" * 70)
    logger.info("Multilingual support not yet implemented for these games")
    logger.info("Would need API research and integration")
    
    results["other"] = {"note": "Not yet implemented"}
    
    conn.close()
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("Summary by game:")
    logger.info("=" * 70)
    for game, result in results.items():
        if isinstance(result, dict):
            if "fixed" in result:
                logger.info(f"  {game}: {result.get('fixed', 0)} cards fixed")
            else:
                logger.info(f"  {game}: {result.get('note', 'No results')}")
    
    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix multilingual cards for all games")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--min-decks",
        type=int,
        default=100,
        help="Minimum deck count to fix",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of cards to query per game",
    )
    parser.add_argument(
        "--games",
        nargs="+",
        choices=["magic", "pokemon", "yugioh", "digimon", "onepiece", "riftbound"],
        help="Specific games to fix (default: all)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Fix Multilingual Cards for ALL Games")
    logger.info("=" * 70)
    
    results = fix_all_games_multilingual(
        args.graph_db,
        args.min_decks,
        args.limit,
        args.games,
    )
    
    logger.info(f"\n✓ Multilingual fixes complete for all games")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

