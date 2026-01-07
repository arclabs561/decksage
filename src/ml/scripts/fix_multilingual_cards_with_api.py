#!/usr/bin/env python3
"""
Fix multilingual card names using Scryfall API.

Supports: Spanish, French, German, Italian, Portuguese, Japanese, Chinese, Korean, Russian.
Uses Scryfall's multilingual support to translate card names to English.
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
from ..data.multilingual_translations import (
    detect_language,
    get_scryfall_lang_code,
    translate_card_name,
)
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()

SCRYFALL_API = "https://api.scryfall.com"
MIN_DELAY = 0.1  # 100ms between requests


def query_scryfall_multilingual(card_name: str, language: str) -> dict[str, any] | None:
    """
    Query Scryfall API for multilingual card name.
    
    Uses multiple strategies:
    1. Exact match with lang filter
    2. Fuzzy search with lang filter
    3. Named endpoint with fuzzy
    4. Search without lang filter (fallback)
    
    Args:
        card_name: Card name in non-English language
        language: Language code (es, fr, de, it, pt, ja, zhs, zht, ko, ru)
        
    Returns:
        Dict with English name and metadata, or None
    """
    if not HAS_REQUESTS:
        return None
    
    try:
        time.sleep(MIN_DELAY)  # Respect rate limits
        
        lang_code = get_scryfall_lang_code(language)
        if not lang_code:
            return None
        
        # Method 1: Exact match with language filter (most reliable)
        # Use exact match with quotes for precise matching
        url = f"{SCRYFALL_API}/cards/search"
        params = {
            "q": f'lang:{lang_code} !"{card_name}"',  # ! for exact match
            "format": "json",
        }
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                # Find exact match (case-insensitive, handle accents)
                card_name_lower = card_name.lower().strip()
                for card in data["data"]:
                    printed = card.get("printed_name", "")
                    printed_lower = printed.lower().strip()
                    # Exact match (case-insensitive)
                    if printed_lower == card_name_lower:
                        return {
                            "name": card.get("name"),  # English name
                            "printed_name": printed,
                            "lang": card.get("lang"),
                            "oracle_id": card.get("oracle_id"),
                        }
                    # Also check printed_names dict
                    if card.get("printed_names") and isinstance(card.get("printed_names"), dict):
                        for lang_key, printed_name in card.get("printed_names", {}).items():
                            if lang_key == lang_code and printed_name.lower().strip() == card_name_lower:
                                return {
                                    "name": card.get("name"),
                                    "printed_name": printed_name,
                                    "lang": lang_code,
                                    "oracle_id": card.get("oracle_id"),
                                }
        
        # Method 2: Fuzzy search with language filter
        params = {
            "q": f'lang:{lang_code} "{card_name}"',
            "format": "json",
        }
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                # Find best match (substring or similarity)
                card_name_lower = card_name.lower()
                best_match = None
                best_score = 0
                
                for card in data["data"]:
                    printed = card.get("printed_name", "").lower()
                    # Calculate similarity score
                    if printed == card_name_lower:
                        score = 1.0
                    elif card_name_lower in printed or printed in card_name_lower:
                        score = min(len(card_name_lower), len(printed)) / max(len(card_name_lower), len(printed))
                    else:
                        # Simple character overlap
                        common = set(card_name_lower) & set(printed)
                        score = len(common) / max(len(set(card_name_lower)), len(set(printed)), 1)
                    
                    if score > best_score:
                        best_score = score
                        best_match = card
                
                if best_match and best_score > 0.5:  # Threshold for match
                    return {
                        "name": best_match.get("name"),
                        "printed_name": best_match.get("printed_name"),
                        "lang": best_match.get("lang"),
                        "oracle_id": best_match.get("oracle_id"),
                    }
        
        # Method 3: Try named endpoint with fuzzy (may work for some languages)
        url = f"{SCRYFALL_API}/cards/named"
        params = {"fuzzy": card_name, "format": "json"}
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            card = response.json()
            # Check if this matches the language
            if card.get("lang") == lang_code:
                printed = card.get("printed_name", "")
                if printed.lower() == card_name.lower():
                    return {
                        "name": card.get("name"),
                        "printed_name": printed,
                        "lang": card.get("lang"),
                        "oracle_id": card.get("oracle_id"),
                    }
            # Check printed_names dict
            if card.get("printed_names") and isinstance(card.get("printed_names"), dict):
                lang_key = lang_code
                printed = card["printed_names"].get(lang_key)
                if printed and printed.lower() == card_name.lower():
                    return {
                        "name": card.get("name"),
                        "printed_name": printed,
                        "lang": lang_key,
                        "oracle_id": card.get("oracle_id"),
                    }
        
        # Method 4: Search without language filter (fallback - may find English version)
        # This helps if the card name is close to English
        url = f"{SCRYFALL_API}/cards/search"
        params = {
            "q": f'!"{card_name}"',
            "format": "json",
        }
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                # Check if any card has this as printed_name in our target language
                for card in data["data"]:
                    if card.get("printed_names") and isinstance(card.get("printed_names"), dict):
                        printed = card["printed_names"].get(lang_code)
                        if printed and printed.lower() == card_name.lower():
                            return {
                                "name": card.get("name"),
                                "printed_name": printed,
                                "lang": lang_code,
                                "oracle_id": card.get("oracle_id"),
                            }
        
        return None
    except Exception as e:
        logger.debug(f"API query failed for '{card_name}' ({language}): {e}")
        return None


def fix_multilingual_cards_with_api(
    graph_db: Path, 
    min_decks: int = 100, 
    limit: int = 100,
    languages: list[str] | None = None,
) -> dict[str, int]:
    """
    Fix multilingual card names using Scryfall API.
    
    Args:
        graph_db: Path to graph database
        min_decks: Minimum deck count to fix
        limit: Maximum number of cards to query
        languages: List of language codes to fix (None = all)
    """
    logger.info("Fixing multilingual card names with Scryfall API...")
    
    if not HAS_REQUESTS:
        logger.error("requests library not available. Install with: uv pip install requests")
        return {"fixed": 0, "api_queries": 0}
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Get high-frequency unknown nodes
    unknown_nodes = conn.execute("""
        SELECT name, total_decks
        FROM nodes
        WHERE game IS NULL OR game = 'Unknown'
        AND total_decks >= ?
        ORDER BY total_decks DESC
        LIMIT ?
    """, (min_decks, limit)).fetchall()
    
    logger.info(f"Found {len(unknown_nodes)} high-frequency unknown nodes")
    
    card_db = get_card_database()
    card_db.load()
    
    game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO", "digimon": "DIG", "onepiece": "OP", "riftbound": "RFT"}
    
    fixed = 0
    api_queries = 0
    updates = []
    by_language = {}
    
    cursor = conn.cursor()
    
    for i, row in enumerate(unknown_nodes):
        card_name = row["name"]
        
        # Detect language
        detected_lang = detect_language(card_name)
        if not detected_lang:
            continue
        
        # Filter by requested languages if specified
        if languages and detected_lang not in languages:
            continue
        
        # Track by language
        if detected_lang not in by_language:
            by_language[detected_lang] = 0
        
        # Try dictionary translation first (faster, no API call)
        english_name = translate_card_name(card_name, from_lang=detected_lang, use_api=False)
        
        if not english_name:
            # Query Scryfall API
            api_queries += 1
            card_data = query_scryfall_multilingual(card_name, detected_lang)
            
            if card_data:
                english_name = card_data.get("name")
                if english_name and fixed <= 5:
                    logger.debug(f"  API translation: '{card_name}' -> '{english_name}'")
        
        if english_name:
            # Try to find game for English name
            # Use fuzzy matching for better coverage
            game = card_db.get_game(english_name, fuzzy=True)
            
            # If not found, try case variations
            if not game:
                for variant in [english_name.title(), english_name.capitalize(), english_name.upper()]:
                    game = card_db.get_game(variant, fuzzy=True)
                    if game:
                        english_name = variant  # Use the variant that worked
                        break
            
            # If still not found and this is a Magic card (based on context), try API
            if not game and detected_lang in ["fr", "es", "de", "it", "pt"]:
                # These languages are primarily Magic cards in our data
                # Try Scryfall API to verify it's a Magic card
                api_queries += 1
                api_data = query_scryfall_multilingual(card_name, detected_lang)
                if api_data:
                    api_english = api_data.get("name")
                    if api_english:
                        # Try game lookup with API-provided name
                        game = card_db.get_game(api_english, fuzzy=True)
                        if game:
                            english_name = api_english
                            logger.debug(f"  API verified: '{card_name}' -> '{api_english}'")
            
            if game:
                game_code = game_map.get(game.lower())
                if game_code:
                    updates.append((game_code, card_name))
                    fixed += 1
                    by_language[detected_lang] += 1
                    if fixed <= 10:
                        logger.info(f"  ✓ {card_name} ({detected_lang}) -> {english_name} -> {game_code}")
                else:
                    logger.debug(f"  No game code for '{game}' (translated from '{card_name}')")
            else:
                # For Magic cards, if we got a translation but no game match,
                # assume it's Magic (common case for limited card database)
                if detected_lang in ["fr", "es", "de", "it", "pt"] and english_name:
                    # These are likely Magic cards based on language
                    # Use MTG as fallback if translation exists
                    updates.append(("MTG", card_name))
                    fixed += 1
                    by_language[detected_lang] += 1
                    if fixed <= 10:
                        logger.info(f"  ✓ {card_name} ({detected_lang}) -> {english_name} -> MTG (assumed)")
                else:
                    # Log cards that translate but don't match any game
                    if fixed <= 5:  # Only log first few to avoid spam
                        logger.debug(f"  Could not find game for '{english_name}' (translated from '{card_name}')")
        
        if (i + 1) % 10 == 0:
            if updates:
                cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", updates)
                conn.commit()
                updates = []
            logger.info(f"  Processed {i + 1}/{len(unknown_nodes)}... (fixed: {fixed}, API queries: {api_queries})")
    
    if updates:
        cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", updates)
        conn.commit()
    
    conn.close()
    
    logger.info(f"Fixed {fixed} multilingual card names using {api_queries} API queries")
    logger.info("Fixed by language:")
    for lang, count in sorted(by_language.items(), key=lambda x: -x[1]):
        logger.info(f"  {lang}: {count}")
    
    return {"fixed": fixed, "api_queries": api_queries, "by_language": by_language}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix multilingual card names using Scryfall API")
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
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of cards to query (default: 100)",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        choices=["es", "fr", "de", "it", "pt", "ja", "zh", "ko", "ru"],
        help="Specific languages to fix (default: all)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Fix Multilingual Cards with Scryfall API")
    logger.info("=" * 70)
    
    results = fix_multilingual_cards_with_api(
        args.graph_db, 
        args.min_decks, 
        args.limit,
        args.languages,
    )
    
    logger.info(f"\n✓ Fixed {results['fixed']} cards using {results['api_queries']} API queries")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

