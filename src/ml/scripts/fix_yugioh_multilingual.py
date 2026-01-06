#!/usr/bin/env python3
"""
Fix Yu-Gi-Oh card names in multiple languages.

Uses YGOProDeck API or official Yu-Gi-Oh APIs for translations.
Yu-Gi-Oh cards are printed in multiple languages.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from ..data.card_database import get_card_database
from ..data.multilingual_translations import detect_language, translate_yugioh_card_name
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()

# Yu-Gi-Oh APIs
# YGOProDeck API v7: https://ygoprodeck.com/api-guide/
# Supports: en (default), fr, de, it, pt
# Note: Does NOT support Japanese
YGOPRODECK_API = "https://db.ygoprodeck.com/api/v7"

MIN_DELAY = 0.1

# Language code mapping (detected -> YGOProDeck)
YGOPRODECK_LANG_MAP = {
    "fr": "fr",
    "de": "de",
    "it": "it",
    "pt": "pt",
    "en": "en",
    # Note: es (Spanish) not explicitly supported, but may work
    "es": "en",  # Fallback to English
}


def query_ygoprodeck(card_name: str, language: str = "en") -> dict[str, any] | None:
    """
    Query YGOProDeck API for Yu-Gi-Oh card.
    
    Note: YGOProDeck primarily supports English, but may have multilingual data.
    """
    if not HAS_REQUESTS:
        return None
    
    try:
        time.sleep(MIN_DELAY)
        
        # YGOProDeck search
        url = f"{YGOPRODECK_API}/cardinfo.php"
        params = {
            "name": card_name,
        }
        
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                card = data["data"][0]
                return {
                    "name": card.get("name"),  # English name
                    "id": card.get("id"),
                }
        
        return None
    except Exception as e:
        logger.debug(f"YGOProDeck API query failed for '{card_name}': {e}")
        return None


def fix_yugioh_multilingual(
    graph_db: Path,
    min_decks: int = 100,
    limit: int = 100,
) -> dict[str, int]:
    """
    Fix Yu-Gi-Oh card names in multiple languages.
    
    Note: YGOProDeck API primarily supports English.
    Multilingual support may require additional research.
    """
    logger.info("Fixing Yu-Gi-Oh multilingual cards...")
    
    if not HAS_REQUESTS:
        logger.error("requests library not available")
        return {"fixed": 0, "api_queries": 0}
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Get Yu-Gi-Oh cards that are unknown or might be multilingual
    yugioh_unknown = conn.execute("""
        SELECT name, total_decks
        FROM nodes
        WHERE (game IS NULL OR game = 'Unknown' OR game = 'YGO')
        AND total_decks >= ?
        ORDER BY total_decks DESC
        LIMIT ?
    """, (min_decks, limit)).fetchall()
    
    logger.info(f"Found {len(yugioh_unknown)} Yu-Gi-Oh candidates")
    
    card_db = get_card_database()
    card_db.load()
    
    fixed = 0
    api_queries = 0
    updates = []
    by_language = {}
    
    cursor = conn.cursor()
    
    for i, row in enumerate(yugioh_unknown):
        card_name = row["name"]
        current_game = row.get("game") if hasattr(row, "get") else row[2] if len(row) > 2 else None
        
        # Detect language
        detected_lang = detect_language(card_name)
        if not detected_lang:
            continue
        
        # Track by language
        if detected_lang not in by_language:
            by_language[detected_lang] = 0
        
        # Strategy 1: Dictionary lookup (fast, reliable for known cards)
        english_name = translate_yugioh_card_name(card_name)
        if english_name:
            # Verify it's a Yu-Gi-Oh card
            game = card_db.get_game(english_name, fuzzy=True)
            if game and game.lower() == "yugioh":
                # Update if not already YGO
                if current_game != "YGO":
                    updates.append(("YGO", card_name))
                    fixed += 1
                    by_language[detected_lang] += 1
                    if fixed <= 10:
                        logger.info(f"  ✓ {card_name} ({detected_lang}) -> {english_name} -> YGO (dictionary)")
                continue
        
        # Strategy 2: Query YGOProDeck API with detected language
        api_queries += 1
        card_data = query_ygoprodeck(card_name, detected_lang)
        
        if card_data:
            english_name = card_data.get("name")
            if english_name:
                # Verify it's a Yu-Gi-Oh card
                game = card_db.get_game(english_name, fuzzy=True)
                if game and game.lower() == "yugioh":
                    updates.append(("YGO", card_name))
                    fixed += 1
                    by_language[detected_lang] += 1
                    if fixed <= 10:
                        logger.info(f"  ✓ {card_name} ({detected_lang}) -> {english_name} -> YGO (API)")
                else:
                    # If translation found but game doesn't match, still might be YGO
                    # (card database might be incomplete)
                    # Use heuristic: if we got a translation from YGOProDeck, it's likely YGO
                    if detected_lang in ["fr", "de", "it", "pt"]:  # Languages YGOProDeck supports
                        updates.append(("YGO", card_name))
                        fixed += 1
                        by_language[detected_lang] += 1
                        if fixed <= 10:
                            logger.info(f"  ✓ {card_name} ({detected_lang}) -> {english_name} -> YGO (assumed)")
        
        if (i + 1) % 10 == 0:
            if updates:
                cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", updates)
                conn.commit()
                updates = []
            logger.info(f"  Processed {i + 1}/{len(yugioh_unknown)}... (fixed: {fixed})")
    
    if updates:
        cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", updates)
        conn.commit()
    
    conn.close()
    
    logger.info(f"Fixed {fixed} Yu-Gi-Oh multilingual cards using {api_queries} API queries")
    if by_language:
        logger.info("Fixed by language:")
        for lang, count in sorted(by_language.items(), key=lambda x: -x[1]):
            logger.info(f"  {lang}: {count}")
    
    return {"fixed": fixed, "api_queries": api_queries, "by_language": by_language}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix Yu-Gi-Oh multilingual cards")
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
        help="Maximum number of cards to query",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Fix Yu-Gi-Oh Multilingual Cards")
    logger.info("=" * 70)
    
    results = fix_yugioh_multilingual(args.graph_db, args.min_decks, args.limit)
    
    logger.info(f"\n✓ Results: {results}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

