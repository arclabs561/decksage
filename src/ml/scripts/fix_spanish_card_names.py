#!/usr/bin/env python3
"""
Fix Spanish card names by translating and updating game labels.

Many high-frequency unknown nodes are Spanish card names that need translation.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from ..data.card_database import get_card_database
from ..data.spanish_card_translations import translate_spanish_name
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def fix_spanish_card_names(graph_db: Path, min_decks: int = 100) -> dict[str, int]:
    """Fix Spanish card names by translating and updating game labels."""
    logger.info("Fixing Spanish card names...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Get unknown nodes with high frequency
    unknown_nodes = conn.execute("""
        SELECT name, total_decks
        FROM nodes
        WHERE game IS NULL OR game = 'Unknown'
        AND total_decks >= ?
        ORDER BY total_decks DESC
    """, (min_decks,)).fetchall()
    
    logger.info(f"Found {len(unknown_nodes)} high-frequency unknown nodes")
    
    card_db = get_card_database()
    card_db.load()
    
    game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO", "digimon": "DIG", "onepiece": "OP", "riftbound": "RFT"}
    
    fixed = 0
    not_found = 0
    updates = []
    
    cursor = conn.cursor()
    
    for i, row in enumerate(unknown_nodes):
        card_name = row["name"]
        
        # Try Spanish translation
        english_name = translate_spanish_name(card_name)
        if english_name and english_name != card_name:
            # Try to find game for translated name
            game = card_db.get_game(english_name, fuzzy=True)
            if game:
                game_code = game_map.get(game.lower())
                if game_code:
                    updates.append((game_code, card_name))
                    fixed += 1
                    if fixed <= 10:
                        logger.debug(f"  {card_name} -> {english_name} -> {game_code}")
                else:
                    not_found += 1
            else:
                not_found += 1
        else:
            not_found += 1
        
        if (i + 1) % 100 == 0:
            if updates:
                cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", updates)
                conn.commit()
                updates = []
            logger.info(f"  Processed {i + 1}/{len(unknown_nodes)}... (fixed: {fixed})")
    
    if updates:
        cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", updates)
        conn.commit()
    
    conn.close()
    
    logger.info(f"Fixed {fixed} Spanish card names")
    logger.info(f"Still unknown: {not_found}")
    
    return {"fixed": fixed, "not_found": not_found}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix Spanish card names")
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
        help="Minimum deck count to fix (default: 100)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Fix Spanish Card Names")
    logger.info("=" * 70)
    
    results = fix_spanish_card_names(args.graph_db, args.min_decks)
    
    logger.info(f"\n✓ Fixed {results['fixed']} Spanish card names")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

