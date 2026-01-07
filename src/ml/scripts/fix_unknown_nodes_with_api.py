#!/usr/bin/env python3
"""
Fix unknown nodes using Scryfall API fallback.

For high-frequency unknown cards, query Scryfall API to determine if they're Magic cards.
This helps identify cards that aren't in our local database but exist in Scryfall.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path
from typing import Any

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
MIN_DELAY = 0.1  # 100ms between requests (Scryfall rate limit)


def query_scryfall_api(card_name: str) -> dict[str, Any] | None:
    """Query Scryfall API for a card."""
    if not HAS_REQUESTS:
        logger.warning("requests not available, skipping API lookup")
        return None
    
    try:
        time.sleep(MIN_DELAY)  # Respect rate limits
        url = f"{SCRYFALL_API}/cards/named"
        params = {"exact": card_name, "format": "json"}
        response = requests.get(url, params=params, timeout=5)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            # Try fuzzy search
            params = {"fuzzy": card_name, "format": "json"}
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                return response.json()
        return None
    except Exception as e:
        logger.debug(f"API query failed for '{card_name}': {e}")
        return None


def fix_unknown_nodes_with_api(
    graph_db: Path, min_decks: int = 100, limit: int = 100
) -> dict[str, int]:
    """Fix unknown nodes using API fallback for high-frequency cards."""
    logger.info("Fixing unknown nodes with API fallback...")
    
    if not HAS_REQUESTS:
        logger.error("requests library not available. Install with: uv pip install requests")
        return {"fixed": 0, "api_queries": 0, "errors": 0}
    
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
    
    logger.info(f"Found {len(unknown_nodes)} high-frequency unknown nodes (>= {min_decks} decks)")
    
    card_db = get_card_database()
    card_db.load()
    
    game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO", "digimon": "DIG", "onepiece": "OP", "riftbound": "RFT"}
    
    fixed = 0
    api_queries = 0
    errors = 0
    node_updates = []
    
    cursor = conn.cursor()
    for i, row in enumerate(unknown_nodes):
        card_name = row["name"]
        total_decks = row["total_decks"]
        
        if i % 10 == 0 and i > 0:
            logger.info(f"  Processing {i}/{len(unknown_nodes)}... (fixed: {fixed})")
        
        # Try local database first (with fuzzy matching)
        game = card_db.get_game(card_name, fuzzy=True)
        
        if not game:
            # Try API fallback for Magic cards
            api_queries += 1
            card_data = query_scryfall_api(card_name)
            
            if card_data:
                # Verify it's a valid Magic card
                if card_data.get("oracle_id") or card_data.get("name"):
                    game = "magic"
                    logger.debug(f"API found: '{card_name}' -> magic")
        
        if game:
            game_code = game_map.get(game.lower())
            if game_code:
                node_updates.append((game_code, card_name))
                fixed += 1
            else:
                errors += 1
        else:
            # Still unknown - that's OK
            pass
    
    # Batch update
    if node_updates:
        logger.info(f"  Updating {len(node_updates)} nodes...")
        cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", node_updates)
        conn.commit()
    
    conn.close()
    
    logger.info(f"Fixed {fixed} unknown nodes")
    logger.info(f"API queries: {api_queries}")
    logger.info(f"Errors: {errors}")
    
    return {"fixed": fixed, "api_queries": api_queries, "errors": errors}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix unknown nodes using API fallback")
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
        help="Minimum deck count to query API (default: 100)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of cards to query (default: 100)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Fix Unknown Nodes with API Fallback")
    logger.info("=" * 70)
    
    results = fix_unknown_nodes_with_api(args.graph_db, args.min_decks, args.limit)
    
    logger.info(f"\n✓ Fixed {results['fixed']} nodes using {results['api_queries']} API queries")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

