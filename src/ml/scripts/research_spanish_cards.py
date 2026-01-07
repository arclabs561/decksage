#!/usr/bin/env python3
"""
Research Spanish card names to build comprehensive translation dictionary.

Queries Scryfall API to find Spanish card names and their English equivalents,
then builds a comprehensive translation dictionary.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from ..utils.logging_config import setup_script_logging

logger = setup_script_logging()

SCRYFALL_API = "https://api.scryfall.com"
MIN_DELAY = 0.1


def research_spanish_cards(output_file: Path, limit: int = 500) -> dict[str, str]:
    """
    Research Spanish card names from Scryfall.
    
    Uses Scryfall's bulk data or search API to find Spanish cards
    and build translation dictionary.
    """
    if not HAS_REQUESTS:
        logger.error("requests library not available")
        return {}
    
    logger.info("Researching Spanish cards from Scryfall...")
    
    translations = {}
    
    # Method 1: Search for Spanish cards using lang:es
    # Get a sample of Spanish cards
    url = f"{SCRYFALL_API}/cards/search"
    params = {
        "q": "lang:es",
        "format": "json",
        "order": "name",
        "dir": "asc",
    }
    
    page = 1
    cards_found = 0
    
    while cards_found < limit:
        try:
            time.sleep(MIN_DELAY)
            params["page"] = page
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                break
            
            data = response.json()
            if not data.get("data"):
                break
            
            for card in data["data"]:
                if cards_found >= limit:
                    break
                
                spanish_name = card.get("printed_name")
                english_name = card.get("name")
                
                if spanish_name and english_name and spanish_name != english_name:
                    spanish_lower = spanish_name.lower().strip()
                    translations[spanish_lower] = english_name.lower().strip()
                    cards_found += 1
                    
                    if cards_found % 50 == 0:
                        logger.info(f"  Found {cards_found} Spanish cards...")
            
            # Check if there are more pages
            if not data.get("has_more"):
                break
            
            page += 1
            
        except Exception as e:
            logger.warning(f"Error fetching page {page}: {e}")
            break
    
    logger.info(f"Found {len(translations)} Spanish card translations")
    
    # Save to file
    if output_file:
        with open(output_file, "w") as f:
            json.dump(translations, f, indent=2, sort_keys=True)
        logger.info(f"Saved translations to {output_file}")
    
    return translations


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Research Spanish card names")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/spanish_translations.json"),
        help="Output file for translations",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of cards to research (default: 500)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Research Spanish Cards")
    logger.info("=" * 70)
    
    translations = research_spanish_cards(args.output, args.limit)
    
    logger.info(f"\n✓ Found {len(translations)} translations")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

