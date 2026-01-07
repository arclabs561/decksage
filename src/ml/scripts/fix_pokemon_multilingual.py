#!/usr/bin/env python3
"""
Fix Pokemon card names in multiple languages.

Uses TCGdex API or Pokemon TCG API for translations.
Pokemon cards are printed in 12 languages.
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
from ..data.multilingual_translations import detect_language
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()

# Pokemon APIs
# TCGdx API v2: https://tcgdx.dev/docs
# Endpoint structure: api.tcgdx.net/v2/{lang}/cards
TCGDEX_API_BASE = "https://api.tcgdx.net/v2"
POKEMON_TCG_API = "https://api.pokemontcg.io/v2"

MIN_DELAY = 0.1

# Language code mapping (detected -> TCGdx)
TCGDX_LANG_MAP = {
    "fr": "fr",
    "es": "es",
    "it": "it",
    "de": "de",
    "pt": "pt",
    "ja": "ja",
    "ko": "ko",
    "zh": "zh-Hans",  # Simplified Chinese
    "id": "id",
    "th": "th",
    "en": "en",
}


def query_tcgdex_pokemon(card_name: str, language: str) -> dict[str, any] | None:
    """
    Query TCGdx API for Pokemon card in specific language.
    
    TCGdx supports: en, fr, es, it, de, pt, ja, ko, zh-Hans, zh-Hant, id, th
    """
    if not HAS_REQUESTS:
        return None
    
    try:
        time.sleep(MIN_DELAY)
        
        # Map detected language to TCGdx language code
        tcgdx_lang = TCGDX_LANG_MAP.get(language, "en")
        
        # TCGdx API v2 endpoint structure
        # Note: TCGdx v2 returns ALL cards, so we need to search through them
        url = f"{TCGDEX_API_BASE}/{tcgdx_lang}/cards"
        
        # For efficiency, we'll limit the search to first 1000 cards
        # In production, might want to cache or use a more efficient approach
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # TCGdx v2 returns a list of cards
            if isinstance(data, list):
                card_name_lower = card_name.lower()
                
                # First pass: exact match
                for card in data[:1000]:  # Limit search for performance
                    # Check localizedName (in the query language)
                    localized = card.get("localizedName") or card.get("name", "")
                    if localized.lower() == card_name_lower:
                        # Get English name - TCGdx cards have "name" field which is English
                        english_name = card.get("name")
                        
                        # If name field is the localized name, try to get English version
                        if not english_name or english_name == localized:
                            # Try to find English version by ID
                            card_id = card.get("id") or card.get("localId")
                            if card_id:
                                try:
                                    en_response = requests.get(f"{TCGDEX_API_BASE}/en/cards", timeout=5)
                                    if en_response.status_code == 200:
                                        en_data = en_response.json()
                                        if isinstance(en_data, list):
                                            for en_card in en_data[:500]:  # Limit search
                                                if (en_card.get("id") == card_id or 
                                                    en_card.get("localId") == card_id):
                                                    english_name = en_card.get("name")
                                                    break
                                except Exception:
                                    pass
                        
                        return {
                            "name": english_name or card.get("name"),
                            "localized_name": localized,
                            "language": language,
                            "id": card.get("id") or card.get("localId"),
                        }
                
                # Second pass: substring match (fuzzy)
                for card in data[:500]:  # Limit for performance
                    localized = card.get("localizedName") or card.get("name", "")
                    localized_lower = localized.lower()
                    if (card_name_lower in localized_lower or 
                        localized_lower in card_name_lower):
                        return {
                            "name": card.get("name"),
                            "localized_name": localized,
                            "language": language,
                            "id": card.get("id") or card.get("localId"),
                        }
        
        return None
    except Exception as e:
        logger.debug(f"TCGdx API query failed for '{card_name}': {e}")
        return None


def fix_pokemon_multilingual(
    graph_db: Path,
    min_decks: int = 100,
    limit: int = 100,
) -> dict[str, int]:
    """
    Fix Pokemon card names in multiple languages using TCGdx API.
    
    TCGdx supports: en, fr, es, it, de, pt, ja, ko, zh-Hans, zh-Hant, id, th
    """
    logger.info("Fixing Pokemon multilingual cards with TCGdx API...")
    
    if not HAS_REQUESTS:
        logger.error("requests library not available")
        return {"fixed": 0, "api_queries": 0}
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Get Pokemon cards that are unknown or might be multilingual
    pokemon_unknown = conn.execute("""
        SELECT name, total_decks
        FROM nodes
        WHERE (game IS NULL OR game = 'Unknown' OR game = 'PKM')
        AND total_decks >= ?
        ORDER BY total_decks DESC
        LIMIT ?
    """, (min_decks, limit)).fetchall()
    
    logger.info(f"Found {len(pokemon_unknown)} Pokemon candidates")
    
    card_db = get_card_database()
    card_db.load()
    
    fixed = 0
    api_queries = 0
    updates = []
    by_language = {}
    
    cursor = conn.cursor()
    
    for i, row in enumerate(pokemon_unknown):
        card_name = row["name"]
        current_game = row.get("game") if hasattr(row, "get") else row[2] if len(row) > 2 else None
        
        # Detect language
        detected_lang = detect_language(card_name)
        if not detected_lang:
            continue
        
        # Track by language
        if detected_lang not in by_language:
            by_language[detected_lang] = 0
        
        # Strategy 1: Many Pokemon card names are the same across languages
        # (e.g., "Pokégear 3.0" is the same in French and English)
        # Check if the name is already valid in our card database
        game = card_db.get_game(card_name, fuzzy=True)
        if game and game.lower() == "pokemon":
            # Already identified as Pokemon, but might need game label update
            if current_game != "PKM":
                updates.append(("PKM", card_name))
                fixed += 1
                by_language[detected_lang] += 1
                if fixed <= 10:
                    logger.info(f"  ✓ {card_name} ({detected_lang}) -> PKM (already in DB)")
                continue
        
        # Strategy 2: Query APIs
        api_queries += 1
        card_data = query_tcgdex_pokemon(card_name, detected_lang)
        
        if card_data:
            english_name = card_data.get("name")
            if english_name:
                # Verify it's a Pokemon card
                game = card_db.get_game(english_name, fuzzy=True)
                if game and game.lower() == "pokemon":
                    updates.append(("PKM", card_name))
                    fixed += 1
                    by_language[detected_lang] += 1
                    if fixed <= 10:
                        logger.info(f"  ✓ {card_name} ({detected_lang}) -> {english_name} -> PKM (API)")
                else:
                    # If translation found but game doesn't match, still might be Pokemon
                    # (card database might be incomplete)
                    # Use heuristic: if we got a translation from Pokemon API, it's likely Pokemon
                    if detected_lang in ["fr", "es", "it", "de", "pt", "ja", "ko", "zh", "id", "th"]:
                        updates.append(("PKM", card_name))
                        fixed += 1
                        by_language[detected_lang] += 1
                        if fixed <= 10:
                            logger.info(f"  ✓ {card_name} ({detected_lang}) -> {english_name} -> PKM (assumed)")
        
        if (i + 1) % 10 == 0:
            if updates:
                cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", updates)
                conn.commit()
                updates = []
            logger.info(f"  Processed {i + 1}/{len(pokemon_unknown)}... (fixed: {fixed})")
    
    if updates:
        cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", updates)
        conn.commit()
    
    conn.close()
    
    logger.info(f"Fixed {fixed} Pokemon multilingual cards using {api_queries} API queries")
    if by_language:
        logger.info("Fixed by language:")
        for lang, count in sorted(by_language.items(), key=lambda x: -x[1]):
            logger.info(f"  {lang}: {count}")
    
    return {"fixed": fixed, "api_queries": api_queries, "by_language": by_language}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix Pokemon multilingual cards")
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
    logger.info("Fix Pokemon Multilingual Cards")
    logger.info("=" * 70)
    
    results = fix_pokemon_multilingual(args.graph_db, args.min_decks, args.limit)
    
    logger.info(f"\n✓ Results: {results}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

