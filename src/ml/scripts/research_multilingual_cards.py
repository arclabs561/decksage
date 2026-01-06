#!/usr/bin/env python3
"""
Research multilingual card names from Scryfall to build comprehensive translation dictionaries.

Queries Scryfall API to find cards in various languages and their English equivalents,
then builds translation dictionaries for all supported languages.
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

from ..data.multilingual_translations import SCRYFALL_LANG_CODES
from ..utils.logging_config import setup_script_logging

logger = setup_script_logging()

SCRYFALL_API = "https://api.scryfall.com"
MIN_DELAY = 0.1


def research_language_cards(
    language: str, 
    output_file: Path, 
    limit: int = 500
) -> dict[str, str]:
    """
    Research cards in a specific language from Scryfall.
    
    Args:
        language: Language code (es, fr, de, it, pt, ja, zhs, zht, ko, ru)
        output_file: Output file for translations
        limit: Maximum number of cards to research
        
    Returns:
        Dictionary mapping foreign names to English names
    """
    if not HAS_REQUESTS:
        logger.error("requests library not available")
        return {}
    
    lang_code = SCRYFALL_LANG_CODES.get(language)
    if not lang_code:
        logger.error(f"Unknown language code: {language}")
        return {}
    
    logger.info(f"Researching {lang_code} cards from Scryfall...")
    
    translations = {}
    
    # Search for cards in specific language
    url = f"{SCRYFALL_API}/cards/search"
    params = {
        "q": f"lang:{language}",
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
                
                foreign_name = card.get("printed_name")
                english_name = card.get("name")
                
                if foreign_name and english_name and foreign_name != english_name:
                    foreign_lower = foreign_name.lower().strip()
                    translations[foreign_lower] = english_name.lower().strip()
                    cards_found += 1
                    
                    if cards_found % 50 == 0:
                        logger.info(f"  Found {cards_found} {lang_code} cards...")
            
            # Check if there are more pages
            if not data.get("has_more"):
                break
            
            page += 1
            
        except Exception as e:
            logger.warning(f"Error fetching page {page}: {e}")
            break
    
    logger.info(f"Found {len(translations)} {lang_code} card translations")
    
    # Save to file
    if output_file:
        with open(output_file, "w") as f:
            json.dump(translations, f, indent=2, sort_keys=True)
        logger.info(f"Saved translations to {output_file}")
    
    return translations


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Research multilingual card names")
    parser.add_argument(
        "--language",
        type=str,
        required=True,
        choices=["es", "fr", "de", "it", "pt", "ja", "zhs", "zht", "ko", "ru"],
        help="Language code to research",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (default: data/{language}_translations.json)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of cards to research (default: 500)",
    )
    
    args = parser.parse_args()
    
    if args.output is None:
        args.output = Path(f"data/{args.language}_translations.json")
    
    logger.info("=" * 70)
    logger.info(f"Research {SCRYFALL_LANG_CODES.get(args.language, args.language)} Cards")
    logger.info("=" * 70)
    
    translations = research_language_cards(args.language, args.output, args.limit)
    
    logger.info(f"\n✓ Found {len(translations)} translations")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

