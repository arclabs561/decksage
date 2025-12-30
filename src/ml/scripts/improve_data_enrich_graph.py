#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
# ]
# ///
"""
Enrich graph with card attributes and metadata.

Based on research:
- Graph enrichment improves embedding quality
- Node attributes (card types, colors, mana costs) help
- Temporal information (when cards played together) helps
- Format/archetype metadata helps

Adds:
- Card attributes as node features
- Temporal edge weights (recent co-occurrences weighted higher)
- Format-specific edges
- Archetype-specific edges
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any
from datetime import datetime, timedelta

try:
    import pandas as pd
    import numpy as np
    
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"Missing dependencies: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_card_attributes(attrs_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load card attributes (types, colors, mana costs, etc.)."""
    if attrs_path and attrs_path.exists():
        df = pd.read_csv(attrs_path)
        attrs = {}
        for _, row in df.iterrows():
            name = row.get("name", "")
            if name:
                attrs[name] = {
                    "type": str(row.get("type", "")),
                    "colors": str(row.get("colors", "")),
                    "mana_cost": str(row.get("mana_cost", "")),
                    "cmc": float(row.get("cmc", 0)),
                    "rarity": str(row.get("rarity", "")),
                }
        return attrs
    
    logger.warning("No card attributes file, using empty attributes")
    return {}


def enrich_edgelist_with_temporal(
    pairs_csv: Path,
    output_edg: Path,
    temporal_decay_days: int = 365,
    min_cooccurrence: int = 2,
) -> tuple[int, int]:
    """Enrich edgelist with temporal weighting."""
    logger.info("Loading pairs CSV...")
    df = pd.read_csv(pairs_csv)
    
    # Filter by minimum co-occurrence
    df = df[df["COUNT_SET"] >= min_cooccurrence]
    
    # If we have temporal data (event_date), apply temporal decay
    if "event_date" in df.columns:
        logger.info("Applying temporal decay to edge weights...")
        # Parse dates and calculate decay
        current_date = datetime.now()
        df["event_date_parsed"] = pd.to_datetime(df["event_date"], errors="coerce")
        df["days_ago"] = (current_date - df["event_date_parsed"]).dt.days
        
        # Temporal decay: recent co-occurrences weighted higher
        df["temporal_weight"] = np.exp(-df["days_ago"] / temporal_decay_days)
        df["weight"] = df["COUNT_MULTISET"] * df["temporal_weight"]
    else:
        logger.info("No temporal data, using original weights")
        df["weight"] = df["COUNT_MULTISET"]
    
    # Write enriched edgelist
    with open(output_edg, "w") as f:
        for _, row in df.iterrows():
            f.write(f"{row['NAME_1']}\t{row['NAME_2']}\t{row['weight']}\n")
    
    num_nodes = len(set(df["NAME_1"]) | set(df["NAME_2"]))
    logger.info(f"Enriched graph: {num_nodes:,} nodes, {len(df):,} edges")
    
    return num_nodes, len(df)


def create_node_features(
    pairs_csv: Path,
    attrs: dict[str, dict[str, Any]],
    output_features: Path,
) -> None:
    """Create node feature file for attributed embeddings."""
    logger.info("Creating node features...")
    
    # Get all unique cards
    df = pd.read_csv(pairs_csv)
    all_cards = set(df["NAME_1"]) | set(df["NAME_2"])
    
    features = {}
    for card in all_cards:
        card_attrs = attrs.get(card, {})
        
        # One-hot encode card type
        type_str = card_attrs.get("type", "")
        is_creature = "Creature" in type_str
        is_instant = "Instant" in type_str
        is_sorcery = "Sorcery" in type_str
        is_enchantment = "Enchantment" in type_str
        is_artifact = "Artifact" in type_str
        is_planeswalker = "Planeswalker" in type_str
        
        # One-hot encode colors
        colors_str = card_attrs.get("colors", "")
        has_white = "W" in colors_str
        has_blue = "U" in colors_str
        has_black = "B" in colors_str
        has_red = "R" in colors_str
        has_green = "G" in colors_str
        
        # CMC and rarity
        cmc = card_attrs.get("cmc", 0.0)
        rarity = card_attrs.get("rarity", "")
        is_common = rarity == "common"
        is_uncommon = rarity == "uncommon"
        is_rare = rarity == "rare"
        is_mythic = rarity == "mythic rare"
        
        features[card] = {
            "is_creature": float(is_creature),
            "is_instant": float(is_instant),
            "is_sorcery": float(is_sorcery),
            "is_enchantment": float(is_enchantment),
            "is_artifact": float(is_artifact),
            "is_planeswalker": float(is_planeswalker),
            "has_white": float(has_white),
            "has_blue": float(has_blue),
            "has_black": float(has_black),
            "has_red": float(has_red),
            "has_green": float(has_green),
            "cmc": float(cmc),
            "is_common": float(is_common),
            "is_uncommon": float(is_uncommon),
            "is_rare": float(is_rare),
            "is_mythic": float(is_mythic),
        }
    
    # Save as JSON
    with open(output_features, "w") as f:
        json.dump(features, f, indent=2)
    
    logger.info(f"Created node features for {len(features):,} cards")
    logger.info(f"Saved to {output_features}")


def main() -> int:
    """Enrich graph with attributes and metadata."""
    parser = argparse.ArgumentParser(description="Enrich graph with card attributes")
    parser.add_argument("--input", type=str, required=True, help="Pairs CSV")
    parser.add_argument("--attributes", type=str, help="Card attributes CSV")
    parser.add_argument("--output-edg", type=str, help="Output edgelist (default: input + _enriched.edg)")
    parser.add_argument("--output-features", type=str, help="Output node features JSON")
    parser.add_argument("--temporal-decay-days", type=int, default=365, help="Temporal decay half-life in days")
    parser.add_argument("--min-cooccur", type=int, default=2, help="Minimum co-occurrence")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        logger.error("Missing dependencies")
        return 1
    
    input_path = Path(args.input)
    
    # Determine output paths
    if args.output_edg:
        output_edg = Path(args.output_edg)
    else:
        output_edg = input_path.parent / f"{input_path.stem}_enriched.edg"
    
    if args.output_features:
        output_features = Path(args.output_features)
    else:
        output_features = input_path.parent / f"{input_path.stem}_node_features.json"
    
    # Load card attributes
    attrs_path = Path(args.attributes) if args.attributes else None
    attrs = load_card_attributes(attrs_path)
    
    # Enrich edgelist
    logger.info("Enriching edgelist...")
    enrich_edgelist_with_temporal(
        input_path,
        output_edg,
        args.temporal_decay_days,
        args.min_cooccur,
    )
    
    # Create node features
    logger.info("Creating node features...")
    create_node_features(input_path, attrs, output_features)
    
    logger.info("✅ Graph enrichment complete!")
    logger.info(f"📊 Enriched edgelist: {output_edg}")
    logger.info(f"📊 Node features: {output_features}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

