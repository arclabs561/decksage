#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "requests>=2.31.0",
# ]
# ///
"""
Re-enrich cards to populate enhanced fields (power, toughness, set, oracle_text, keywords).

Only re-enriches cards that are missing enhanced fields to avoid unnecessary API calls.
"""

from __future__ import annotations

import argparse
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
MIN_DELAY = 0.05
ADAPTIVE_DELAY = 0.1


def get_card_from_scryfall(card_name: str, delay: float = ADAPTIVE_DELAY) -> tuple[dict[str, Any] | None, float]:
    """Get card data from Scryfall API."""
    time.sleep(delay)
    
    try:
        url = f"{SCRYFALL_API}/cards/named"
        params = {"exact": card_name, "format": "json"}
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            return response.json(), delay
        elif response.status_code == 404:
            # Try fuzzy
            time.sleep(delay * 0.5)
            params = {"fuzzy": card_name, "format": "json"}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json(), delay
        
        return None, delay
    except Exception as e:
        logger.debug(f"Error fetching {card_name}: {e}")
        return None, delay


def extract_all_attributes(card_data: dict[str, Any]) -> dict[str, Any]:
    """Extract all attributes including enhanced fields."""
    colors = "".join(card_data.get("colors", []))
    mana_cost = card_data.get("mana_cost", "")
    cmc = float(card_data.get("cmc", 0.0))
    type_line = card_data.get("type_line", "")
    rarity = card_data.get("rarity", "").lower()
    power = card_data.get("power", "")
    toughness = card_data.get("toughness", "")
    set_code = card_data.get("set", "")
    set_name = card_data.get("set_name", "")
    oracle_text = card_data.get("oracle_text", "")
    keywords = card_data.get("keywords", [])
    
    return {
        "type": type_line,
        "colors": colors,
        "mana_cost": mana_cost,
        "cmc": cmc,
        "rarity": rarity,
        "power": power,
        "toughness": toughness,
        "set": set_code,
        "set_name": set_name,
        "oracle_text": oracle_text,
        "keywords": ",".join(keywords) if keywords else "",
    }


def re_enrich_for_enhanced_fields(
    input_csv: Path,
    output_csv: Path,
    batch_size: int = 100,
) -> None:
    """Re-enrich cards missing enhanced fields."""
    logger.info(f"Loading from {input_csv}...")
    
    df = pd.read_csv(input_csv, dtype=str)
    
    # Find cards that need enhanced fields
    # Cards that are enriched (have type) but missing enhanced fields
    needs_enhancement = []
    
    for idx, row in df.iterrows():
        # Must be enriched
        if not row.get('type') or str(row.get('type', '')).strip() == '' or str(row.get('type', '')) == 'nan':
            continue
        
        # Check if missing enhanced fields
        missing_fields = []
        enhanced_fields = ['power', 'toughness', 'set', 'set_name', 'oracle_text', 'keywords']
        
        for field in enhanced_fields:
            if field in df.columns:
                val = row.get(field, '')
                if not val or str(val).strip() == '' or str(val) == 'nan':
                    missing_fields.append(field)
        
        if missing_fields:
            needs_enhancement.append((idx, row['name'], missing_fields))
    
    logger.info(f"Found {len(needs_enhancement)} cards needing enhanced fields")
    
    if not needs_enhancement:
        logger.info("✅ All cards already have enhanced fields!")
        return
    
    enriched = 0
    failed = 0
    current_delay = ADAPTIVE_DELAY
    
    for idx, card_name, missing_fields in needs_enhancement:
        logger.info(f"Re-enriching: {card_name} (missing: {', '.join(missing_fields)})")
        
        card_data, current_delay = get_card_from_scryfall(card_name, current_delay)
        
        if card_data:
            attrs = extract_all_attributes(card_data)
            
            # Update enhanced fields
            if 'power' in df.columns:
                df.at[idx, 'power'] = attrs.get('power', '')
            if 'toughness' in df.columns:
                df.at[idx, 'toughness'] = attrs.get('toughness', '')
            if 'set' in df.columns:
                df.at[idx, 'set'] = attrs.get('set', '')
            if 'set_name' in df.columns:
                df.at[idx, 'set_name'] = attrs.get('set_name', '')
            if 'oracle_text' in df.columns:
                df.at[idx, 'oracle_text'] = attrs.get('oracle_text', '')
            if 'keywords' in df.columns:
                df.at[idx, 'keywords'] = attrs.get('keywords', '')
            
            enriched += 1
            logger.info(f"  ✅ Enhanced: {card_name}")
        else:
            failed += 1
            logger.warning(f"  ❌ Failed: {card_name}")
        
        # Save periodically
        if enriched % batch_size == 0:
            df.to_csv(output_csv, index=False)
            logger.info(f"  💾 Progress saved ({enriched} enhanced)")
    
    # Final save
    df.to_csv(output_csv, index=False)
    
    logger.info(f"✅ Re-enrichment complete!")
    logger.info(f"   Enhanced: {enriched}")
    logger.info(f"   Failed: {failed}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-enrich cards for enhanced fields")
    parser.add_argument("--input", type=str, required=True, help="Input CSV")
    parser.add_argument("--output", type=str, help="Output CSV (default: same as input)")
    parser.add_argument("--batch-size", type=int, default=100, help="Save checkpoint every N cards")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        logger.error("Missing dependencies")
        return 1
    
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path
    
    re_enrich_for_enhanced_fields(input_path, output_path, args.batch_size)
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

