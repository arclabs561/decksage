#!/usr/bin/env python3
"""
Improve translation dictionaries by researching actual card names.

Queries Scryfall API to find common cards in each language and builds
comprehensive translation dictionaries automatically.
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


def research_common_cards(
    language: str,
    output_file: Path,
    limit: int = 1000,
    min_rarity: str | None = None,
) -> dict[str, str]:
    """
    Research common cards in a language to build translation dictionary.
    
    Args:
        language: Language code (es, fr, de, it, pt, ja, zhs, zht, ko, ru)
        output_file: Output file for translations
        limit: Maximum number of cards to research
        min_rarity: Minimum rarity to include (common, uncommon, rare, mythic)
        
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
    
    logger.info(f"Researching common {lang_code} cards from Scryfall...")
    
    translations = {}
    
    # Build query - focus on common/played cards
    query_parts = [f"lang:{language}"]
    if min_rarity:
        query_parts.append(f"r>={min_rarity}")
    
    # Search for cards in specific language, ordered by popularity
    url = f"{SCRYFALL_API}/cards/search"
    params = {
        "q": " ".join(query_parts),
        "format": "json",
        "order": "released",  # Get recent cards first
        "dir": "desc",
    }
    
    page = 1
    cards_found = 0
    
    while cards_found < limit:
        try:
            time.sleep(MIN_DELAY)
            params["page"] = page
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                logger.warning(f"API returned status {response.status_code}")
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
                    english_lower = english_name.lower().strip()
                    
                    # Only add if not already present (avoid overwriting)
                    if foreign_lower not in translations:
                        translations[foreign_lower] = english_lower
                        cards_found += 1
                        
                        if cards_found % 100 == 0:
                            logger.info(f"  Found {cards_found} {lang_code} cards...")
            
            # Check if there are more pages
            if not data.get("has_more"):
                break
            
            page += 1
            
        except Exception as e:
            logger.warning(f"Error fetching page {page}: {e}")
            break
    
    logger.info(f"Found {len(translations)} {lang_code} card translations")
    
    # Merge with existing dictionary if file exists
    existing = {}
    if output_file.exists():
        try:
            with open(output_file) as f:
                existing = json.load(f)
            logger.info(f"Loaded {len(existing)} existing translations")
        except Exception:
            pass
    
    # Merge (new translations take precedence for conflicts)
    merged = {**existing, **translations}
    logger.info(f"Total translations after merge: {len(merged)}")
    
    # Save to file
    if output_file:
        with open(output_file, "w") as f:
            json.dump(merged, f, indent=2, sort_keys=True)
        logger.info(f"Saved {len(merged)} translations to {output_file}")
    
    return merged


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Improve translation dictionaries")
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
        default=1000,
        help="Maximum number of cards to research (default: 1000)",
    )
    parser.add_argument(
        "--min-rarity",
        type=str,
        choices=["common", "uncommon", "rare", "mythic"],
        help="Minimum rarity to include",
    )
    
    args = parser.parse_args()
    
    if args.output is None:
        args.output = Path(f"data/{args.language}_translations.json")
    
    logger.info("=" * 70)
    logger.info(f"Improve {SCRYFALL_LANG_CODES.get(args.language, args.language)} Translation Dictionary")
    logger.info("=" * 70)
    
    translations = research_common_cards(
        args.language,
        args.output,
        args.limit,
        args.min_rarity,
    )
    
    logger.info(f"\n✓ Found {len(translations)} translations")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

