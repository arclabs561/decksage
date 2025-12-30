#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "requests>=2.31.0",
# ]
# ///
"""
Optimized Scryfall enrichment with:
- Adaptive rate limiting
- Checkpoint/resume capability
- Better progress tracking
- Skip already enriched cards efficiently
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
MIN_DELAY = 0.05  # 50ms minimum
MAX_DELAY = 0.2   # 200ms maximum
ADAPTIVE_DELAY = 0.1  # Start with 100ms


def get_card_from_scryfall(
    card_name: str,
    delay: float = ADAPTIVE_DELAY,
) -> tuple[dict[str, Any] | None, float]:
    """Get card data from Scryfall API with adaptive rate limiting.
    
    Returns: (card_data, new_delay)
    """
    time.sleep(delay)
    
    try:
        # Use exact name search first (most reliable)
        url = f"{SCRYFALL_API}/cards/named"
        params = {"exact": card_name, "format": "json"}
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            # Success - can potentially reduce delay slightly (but be conservative)
            new_delay = max(MIN_DELAY, delay * 0.98)  # Very gradual reduction
            return response.json(), new_delay
        elif response.status_code == 404:
            # Try fuzzy search (but only if exact fails)
            time.sleep(delay * 0.5)  # Shorter delay for second attempt
            params = {"fuzzy": card_name, "format": "json"}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                new_delay = max(MIN_DELAY, delay * 0.98)
                return response.json(), new_delay
        
        # Rate limited or error - increase delay
        if response.status_code == 429:
            # Check Retry-After header if available
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    new_delay = float(retry_after) + 0.1  # Add small buffer
                    logger.warning(f"Rate limited, waiting {new_delay:.3f}s (from Retry-After header)")
                except ValueError:
                    new_delay = min(MAX_DELAY, delay * 2.0)  # Double delay
            else:
                new_delay = min(MAX_DELAY, delay * 1.5)
            logger.warning(f"Rate limited for {card_name}, increasing delay to {new_delay:.3f}s")
        else:
            new_delay = delay
        
        return None, new_delay
    except requests.exceptions.Timeout:
        # Timeout - increase delay moderately
        new_delay = min(MAX_DELAY, delay * 1.2)
        logger.debug(f"Timeout for {card_name}, increasing delay to {new_delay:.3f}s")
        return None, new_delay
    except requests.exceptions.RequestException as e:
        logger.debug(f"Request error for {card_name}: {e}")
        return None, delay
    except Exception as e:
        logger.debug(f"Error fetching {card_name}: {e}")
        return None, delay


def extract_attributes_from_scryfall(card_data: dict[str, Any]) -> dict[str, Any]:
    """Extract attributes from Scryfall card data."""
    colors = "".join(card_data.get("colors", []))
    mana_cost = card_data.get("mana_cost", "")
    cmc = float(card_data.get("cmc", 0.0))
    type_line = card_data.get("type_line", "")
    rarity = card_data.get("rarity", "").lower()
    
    # Extract power/toughness for creatures
    power = card_data.get("power")
    toughness = card_data.get("toughness")
    
    # Extract set information
    set_code = card_data.get("set", "")
    set_name = card_data.get("set_name", "")
    
    # Extract additional useful fields
    oracle_text = card_data.get("oracle_text", "")
    keywords = card_data.get("keywords", [])
    
    return {
        "type": type_line,
        "colors": colors,
        "mana_cost": mana_cost,
        "cmc": cmc,
        "rarity": rarity,
        "power": str(power) if power else "",
        "toughness": str(toughness) if toughness else "",
        "set": set_code,
        "set_name": set_name,
        "oracle_text": oracle_text,
        "keywords": ",".join(keywords) if keywords else "",
    }


def enrich_attributes_csv_optimized(
    input_csv: Path,
    output_csv: Path,
    batch_size: int = 100,
    checkpoint_interval: int = 50,
    max_cards: int | None = None,
) -> None:
    """Enrich attributes CSV with optimized processing."""
    logger.info(f"Loading attributes from {input_csv}...")
    
    # Load with explicit dtypes to avoid warnings
    # Include all possible columns
    df = pd.read_csv(input_csv, dtype={
        "name": str,
        "type": str,
        "colors": str,
        "mana_cost": str,
        "cmc": float,
        "rarity": str,
        "power": str,
        "toughness": str,
        "set": str,
        "set_name": str,
        "oracle_text": str,
        "keywords": str,
    })
    
    if max_cards:
        df = df.head(max_cards)
        logger.info(f"Limiting to {max_cards} cards for testing")
    
    # Count already enriched
    already_enriched = df["type"].notna() & (df["type"] != "")
    num_enriched = already_enriched.sum()
    num_needing = len(df) - num_enriched
    
    logger.info(f"Found {num_enriched:,} already enriched, {num_needing:,} needing enrichment")
    logger.info(f"Enriching {num_needing:,} cards with Scryfall API...")
    
    enriched = 0
    failed = 0
    current_delay = ADAPTIVE_DELAY
    last_checkpoint = num_enriched
    
    # Process only rows that need enrichment
    for idx, row in df.iterrows():
        # Skip if already enriched
        if pd.notna(row.get("type")) and row.get("type"):
            continue
        
        card_name = row["name"]
        
        # Get from Scryfall with adaptive delay
        card_data, current_delay = get_card_from_scryfall(card_name, current_delay)
        
        if card_data:
            attrs = extract_attributes_from_scryfall(card_data)
            # Update all available fields
            df.at[idx, "type"] = str(attrs["type"])
            df.at[idx, "colors"] = str(attrs["colors"])
            df.at[idx, "mana_cost"] = str(attrs["mana_cost"])
            df.at[idx, "cmc"] = float(attrs["cmc"])
            df.at[idx, "rarity"] = str(attrs["rarity"])
            
            # Update optional fields if they exist in DataFrame
            if "power" in df.columns:
                df.at[idx, "power"] = attrs.get("power", "")
            if "toughness" in df.columns:
                df.at[idx, "toughness"] = attrs.get("toughness", "")
            if "set" in df.columns:
                df.at[idx, "set"] = attrs.get("set", "")
            if "set_name" in df.columns:
                df.at[idx, "set_name"] = attrs.get("set_name", "")
            if "oracle_text" in df.columns:
                df.at[idx, "oracle_text"] = attrs.get("oracle_text", "")
            if "keywords" in df.columns:
                df.at[idx, "keywords"] = attrs.get("keywords", "")
            
            enriched += 1
        else:
            failed += 1
        
        # Progress update and checkpoint
        total_processed = enriched + failed
        if total_processed % batch_size == 0:
            logger.info(
                f"Progress: {total_processed}/{num_needing} "
                f"(enriched: {enriched}, failed: {failed}, "
                f"delay: {current_delay:.3f}s)"
            )
        
        # Checkpoint periodically (optimized: only save if significant progress)
        if enriched - last_checkpoint >= checkpoint_interval:
            try:
                # Use faster CSV writing with minimal overhead
                df.to_csv(output_csv, index=False, mode='w')
                logger.info(f"  💾 Checkpoint saved ({enriched} enriched so far)")
                last_checkpoint = enriched
            except Exception as e:
                logger.warning(f"  ⚠️  Checkpoint save failed: {e}, will retry next interval")
    
    # Final save
    df.to_csv(output_csv, index=False)
    
    logger.info(f"✅ Enrichment complete!")
    logger.info(f"   Enriched: {enriched}")
    logger.info(f"   Failed: {failed}")
    logger.info(f"   Total: {num_enriched + enriched}/{len(df)}")
    logger.info(f"   Saved to {output_csv}")


def main() -> int:
    """Enrich card attributes with optimizations."""
    parser = argparse.ArgumentParser(description="Enrich card attributes with Scryfall API (optimized)")
    parser.add_argument("--input", type=str, required=True, help="Input attributes CSV")
    parser.add_argument("--output", type=str, help="Output CSV (default: input + _enriched)")
    parser.add_argument("--batch-size", type=int, default=100, help="Progress update interval")
    parser.add_argument("--checkpoint-interval", type=int, default=50, help="Save checkpoint every N enriched cards")
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
    
    enrich_attributes_csv_optimized(
        input_path,
        output_path,
        args.batch_size,
        args.checkpoint_interval,
        args.max_cards,
    )
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

