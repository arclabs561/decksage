#!/usr/bin/env python3
"""
Validate multilingual card fixes by checking translation accuracy.

Samples fixed cards and verifies that:
1. Translation is correct
2. Game assignment is correct
3. Card exists in the target game's database
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from ..data.card_database import get_card_database
from ..data.multilingual_translations import detect_language, translate_card_name
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def validate_fixes(
    graph_db: Path,
    sample_size: int = 50,
    min_decks: int = 100,
) -> dict[str, any]:
    """
    Validate multilingual card fixes.
    
    Args:
        graph_db: Path to graph database
        sample_size: Number of fixed cards to sample
        min_decks: Minimum deck count to consider
        
    Returns:
        Validation results
    """
    logger.info("Validating multilingual card fixes...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Get sample of recently fixed cards (cards that were unknown but now have games)
    # We'll check cards that have games and appear to be multilingual
    fixed_cards = conn.execute("""
        SELECT name, game, total_decks
        FROM nodes
        WHERE game IS NOT NULL
        AND game != 'Unknown'
        AND total_decks >= ?
        ORDER BY total_decks DESC
        LIMIT ?
    """, (min_decks, sample_size * 2)).fetchall()
    
    logger.info(f"Sampling {len(fixed_cards)} cards for validation...")
    
    card_db = get_card_database()
    card_db.load()
    
    validated = 0
    errors = []
    warnings = []
    
    for row in fixed_cards[:sample_size]:
        card_name = row["name"]
        assigned_game = row["game"]
        decks = row["total_decks"]
        
        # Check if card name appears multilingual
        lang = detect_language(card_name)
        if not lang:
            continue  # Skip non-multilingual cards
        
        # Try to translate
        translated = translate_card_name(card_name, from_lang=lang, use_api=False)
        
        if translated:
            # Verify the translated name exists in the assigned game
            game = card_db.get_game(translated, fuzzy=True)
            
            if game:
                game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO", "digimon": "DIG", "onepiece": "OP", "riftbound": "RFT"}
                expected_game_code = game_map.get(game.lower())
                
                if expected_game_code == assigned_game:
                    validated += 1
                    logger.debug(f"  ✓ {card_name} -> {translated} -> {assigned_game}")
                else:
                    error = f"Mismatch: {card_name} -> {translated} -> expected {expected_game_code}, got {assigned_game}"
                    errors.append(error)
                    logger.warning(f"  ✗ {error}")
            else:
                warning = f"Translated '{card_name}' -> '{translated}' but game not found"
                warnings.append(warning)
                logger.debug(f"  ~ {warning}")
        else:
            # Card appears multilingual but no translation found
            warning = f"Multilingual card '{card_name}' has no translation"
            warnings.append(warning)
            logger.debug(f"  ~ {warning}")
    
    conn.close()
    
    results = {
        "validated": validated,
        "errors": len(errors),
        "warnings": len(warnings),
        "error_details": errors[:10],  # First 10 errors
        "warning_details": warnings[:10],  # First 10 warnings
    }
    
    logger.info(f"Validation complete: {validated} correct, {len(errors)} errors, {len(warnings)} warnings")
    
    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate multilingual card fixes")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Number of cards to sample for validation",
    )
    parser.add_argument(
        "--min-decks",
        type=int,
        default=100,
        help="Minimum deck count to consider",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Validate Multilingual Card Fixes")
    logger.info("=" * 70)
    
    results = validate_fixes(args.graph_db, args.sample_size, args.min_decks)
    
    logger.info(f"\n✓ Validation Results:")
    logger.info(f"  Validated: {results['validated']}")
    logger.info(f"  Errors: {results['errors']}")
    logger.info(f"  Warnings: {results['warnings']}")
    
    if results['errors'] > 0:
        logger.warning("\nErrors found:")
        for error in results['error_details']:
            logger.warning(f"  {error}")
    
    return 0 if results['errors'] == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

