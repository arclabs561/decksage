#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "requests>=2.31.0",
# ]
# ///
"""
Enrich card attributes using Scryfall API.

Scryfall provides free, comprehensive card data including:
- Type line
- Mana cost
- Colors
- CMC
- Rarity
- And more

This script enriches the minimal attributes CSV with real data.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    import requests
    
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"Missing dependencies: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCRYFALL_API = "https://api.scryfall.com"


def get_card_from_scryfall(card_name: str) -> dict[str, Any] | None:
    """Get card data from Scryfall API."""
    # Scryfall rate limit: 50-100ms between requests
    time.sleep(0.1)
    
    try:
        # Use exact name search
        url = f"{SCRYFALL_API}/cards/named"
        params = {"exact": card_name, "format": "json"}
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            # Try fuzzy search
            params = {"fuzzy": card_name, "format": "json"}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
        
        return None
    except Exception as e:
        logger.debug(f"Error fetching {card_name}: {e}")
        return None


def extract_attributes_from_scryfall(card_data: dict[str, Any]) -> dict[str, Any]:
    """Extract attributes from Scryfall card data."""
    # Get colors
    colors = "".join(card_data.get("colors", []))
    
    # Get mana cost
    mana_cost = card_data.get("mana_cost", "")
    
    # Get CMC
    cmc = card_data.get("cmc", 0.0)
    if isinstance(cmc, int):
        cmc = float(cmc)
    
    # Get type line
    type_line = card_data.get("type_line", "")
    
    # Get rarity
    rarity = card_data.get("rarity", "").lower()
    
    return {
        "type": type_line,
        "colors": colors,
        "mana_cost": mana_cost,
        "cmc": cmc,
        "rarity": rarity,
    }


def enrich_attributes_csv(
    input_csv: Path,
    output_csv: Path,
    batch_size: int = 100,
    max_cards: int | None = None,
) -> None:
    """Enrich attributes CSV with Scryfall data."""
    logger.info(f"Loading attributes from {input_csv}...")
    df = pd.read_csv(input_csv)
    
    if max_cards:
        df = df.head(max_cards)
        logger.info(f"Limiting to {max_cards} cards for testing")
    
    logger.info(f"Enriching {len(df):,} cards with Scryfall API...")
    logger.info("Note: This will take time due to rate limits (~0.1s per card)")
    
    enriched = 0
    failed = 0
    
    for idx, row in df.iterrows():
        card_name = row["name"]
        
        # Skip if already enriched
        if pd.notna(row.get("type")) and row.get("type"):
            continue
        
        # Get from Scryfall
        card_data = get_card_from_scryfall(card_name)
        
        if card_data:
            attrs = extract_attributes_from_scryfall(card_data)
            # Convert to proper dtypes to avoid warnings
            df.at[idx, "type"] = str(attrs["type"])
            df.at[idx, "colors"] = str(attrs["colors"])
            df.at[idx, "mana_cost"] = str(attrs["mana_cost"])
            df.at[idx, "cmc"] = float(attrs["cmc"])
            df.at[idx, "rarity"] = str(attrs["rarity"])
            enriched += 1
        else:
            failed += 1
        
        # Progress update
        if (idx + 1) % batch_size == 0:
            logger.info(f"Progress: {idx + 1}/{len(df)} (enriched: {enriched}, failed: {failed})")
            # Save intermediate results
            df.to_csv(output_csv, index=False)
    
    # Final save
    df.to_csv(output_csv, index=False)
    
    logger.info(f"✅ Enrichment complete!")
    logger.info(f"   Enriched: {enriched}")
    logger.info(f"   Failed: {failed}")
    logger.info(f"   Saved to {output_csv}")


def main() -> int:
    """Enrich card attributes with Scryfall."""
    parser = argparse.ArgumentParser(description="Enrich card attributes with Scryfall API")
    parser.add_argument("--input", type=str, required=True, help="Input attributes CSV")
    parser.add_argument("--output", type=str, help="Output CSV (default: input + _enriched)")
    parser.add_argument("--batch-size", type=int, default=100, help="Progress update interval")
    parser.add_argument("--max-cards", type=int, help="Limit number of cards (for testing)")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        logger.error("Missing dependencies")
        return 1
    
    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / f"{input_path.stem}_enriched.csv"
    
    enrich_attributes_csv(input_path, output_path, args.batch_size, args.max_cards)
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

