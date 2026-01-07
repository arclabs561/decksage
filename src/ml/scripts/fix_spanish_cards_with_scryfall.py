#!/usr/bin/env python3
"""
Fix Spanish card names using Scryfall API.

Queries Scryfall API for Spanish card names and translates them to English.
More comprehensive than dictionary-based translation.
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
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()

SCRYFALL_API = "https://api.scryfall.com"
MIN_DELAY = 0.1  # 100ms between requests


def query_scryfall_spanish(card_name: str) -> dict[str, any] | None:
    """
    Query Scryfall API for Spanish card name.
    
    Uses Scryfall's multilingual support:
    - Search with lang:es to find Spanish cards
    - Match by printed_name
    - Return English name from card object
    """
    if not HAS_REQUESTS:
        return None
    
    try:
        time.sleep(MIN_DELAY)  # Respect rate limits
        
        # Method 1: Search for Spanish cards with lang:es filter
        url = f"{SCRYFALL_API}/cards/search"
        # Search for cards where printed_name matches (Spanish cards)
        params = {"q": f'lang:es printed:"{card_name}"', "format": "json"}
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                # Find exact match
                for card in data["data"]:
                    if card.get("printed_name") == card_name:
                        return {
                            "name": card.get("name"),  # English name
                            "printed_name": card.get("printed_name"),  # Spanish name
                            "lang": card.get("lang"),
                            "oracle_id": card.get("oracle_id"),
                        }
        
        # Method 2: Try fuzzy search with Spanish name
        url = f"{SCRYFALL_API}/cards/search"
        params = {"q": f'lang:es "{card_name}"', "format": "json"}
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                # Find best match
                for card in data["data"]:
                    printed = card.get("printed_name", "").lower()
                    if card_name.lower() in printed or printed in card_name.lower():
                        return {
                            "name": card.get("name"),
                            "printed_name": card.get("printed_name"),
                            "lang": card.get("lang"),
                            "oracle_id": card.get("oracle_id"),
                        }
        
        # Method 3: Try named endpoint with fuzzy (may work for some Spanish names)
        url = f"{SCRYFALL_API}/cards/named"
        params = {"fuzzy": card_name, "format": "json"}
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            card = response.json()
            # Check if this is a Spanish printing
            if card.get("lang") == "es" and card.get("printed_name") == card_name:
                return {
                    "name": card.get("name"),
                    "printed_name": card.get("printed_name"),
                    "lang": card.get("lang"),
                    "oracle_id": card.get("oracle_id"),
                }
            # If we got a card but it's English, check if it has Spanish printed_name
            if card.get("printed_names") and isinstance(card.get("printed_names"), dict):
                if card["printed_names"].get("es") == card_name:
                    return {
                        "name": card.get("name"),
                        "printed_name": card_name,
                        "lang": "es",
                        "oracle_id": card.get("oracle_id"),
                    }
        
        return None
    except Exception as e:
        logger.debug(f"API query failed for '{card_name}': {e}")
        return None


def fix_spanish_cards_with_scryfall(
    graph_db: Path, min_decks: int = 100, limit: int = 100
) -> dict[str, int]:
    """Fix Spanish card names using Scryfall API."""
    logger.info("Fixing Spanish card names with Scryfall API...")
    
    if not HAS_REQUESTS:
        logger.error("requests library not available. Install with: uv pip install requests")
        return {"fixed": 0, "api_queries": 0}
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Get high-frequency unknown nodes that look Spanish
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
    
    cursor = conn.cursor()
    
    for i, row in enumerate(unknown_nodes):
        card_name = row["name"]
        
        # Check if it looks Spanish
        has_spanish_chars = any(c in card_name.lower() for c in 'áéíóúñü')
        has_spanish_words = any(word in card_name.lower() for word in ['de', 'del', 'la', 'el', 'los', 'las'])
        is_spanish = has_spanish_chars or (has_spanish_words and len(card_name.split()) > 1)
        
        if not is_spanish:
            continue
        
        # Query Scryfall API
        api_queries += 1
        card_data = query_scryfall_spanish(card_name)
        
        if card_data:
            english_name = card_data.get("name")
            if english_name:
                # Try to find game for English name
                game = card_db.get_game(english_name, fuzzy=True)
                if game:
                    game_code = game_map.get(game.lower())
                    if game_code:
                        updates.append((game_code, card_name))
                        fixed += 1
                        if fixed <= 10:
                            logger.debug(f"  {card_name} -> {english_name} -> {game_code}")
        
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
    
    logger.info(f"Fixed {fixed} Spanish card names using {api_queries} API queries")
    
    return {"fixed": fixed, "api_queries": api_queries}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix Spanish card names using Scryfall API")
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
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Fix Spanish Cards with Scryfall API")
    logger.info("=" * 70)
    
    results = fix_spanish_cards_with_scryfall(args.graph_db, args.min_decks, args.limit)
    
    logger.info(f"\n✓ Fixed {results['fixed']} cards using {results['api_queries']} API queries")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

