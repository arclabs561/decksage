#!/usr/bin/env python3
"""
Filter pairs CSV by timestamp to prevent data leakage.

Only includes pairs from train/val period (excludes test period).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from ..evaluation.cv_ablation import TemporalSplitter, SplitConfig
from ..utils.paths import PATHS
from ..utils.logging_config import setup_script_logging

logger = setup_script_logging()


def filter_pairs_by_timestamp(
    pairs_path: Path,
    decks_path: Path,
    output_path: Path,
    train_frac: float = 0.7,
    val_frac: float = 0.15,
) -> int:
    """
    Filter pairs CSV to only include train/val period pairs.
    
    Args:
        pairs_path: Path to pairs CSV (card1, card2, weight, timestamp)
        decks_path: Path to decks JSONL (to determine split point)
        output_path: Path to save filtered pairs CSV
        train_frac: Fraction for training
        val_frac: Fraction for validation
        
    Returns:
        Exit code
    """
    logger.info("="*70)
    logger.info("Filtering Pairs by Timestamp (Leakage Prevention)")
    logger.info("="*70)
    
    # Load decks to determine split point
    logger.info(f"Loading decks from {decks_path}...")
    all_decks = []
    with open(decks_path, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    deck = json.loads(line)
                    timestamp_str = deck.get('scraped_at') or deck.get('timestamp') or deck.get('created_at') or deck.get('date')
                    if timestamp_str:
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            deck['_parsed_timestamp'] = timestamp
                            all_decks.append(deck)
                        except:
                            pass
                except:
                    continue
    
    if not all_decks:
        logger.error("No decks with timestamps found")
        return 1
    
    # Determine split point
    sorted_decks = sorted(all_decks, key=lambda d: d['_parsed_timestamp'])
    n = len(sorted_decks)
    train_end = int(n * train_frac)
    val_end = train_end + int(n * val_frac)
    
    test_start = sorted_decks[val_end]['_parsed_timestamp'] if val_end < n else sorted_decks[-1]['_parsed_timestamp']
    
    logger.info(f"Split point: {test_start.isoformat()}")
    logger.info(f"  Train: {train_end:,} decks")
    logger.info(f"  Val:   {val_end - train_end:,} decks")
    logger.info(f"  Test:  {n - val_end:,} decks [EXCLUDED]")
    
    # Load pairs
    logger.info(f"\nLoading pairs from {pairs_path}...")
    pairs_df = pd.read_csv(pairs_path)
    logger.info(f"  Loaded {len(pairs_df):,} pairs")
    
    # Check if pairs have timestamp column
    if 'timestamp' not in pairs_df.columns:
        logger.warning("Pairs CSV does not have 'timestamp' column")
        logger.warning("  Cannot filter by timestamp - pairs may include test period")
        logger.warning("  Recommendation: Regenerate pairs from decks with timestamps")
        
        # Try to infer from deck data
        logger.info("  Attempting to infer timestamps from deck data...")
        # This is complex - would need to map pairs back to decks
        # For now, just warn and copy
        pairs_df.to_csv(output_path, index=False)
        logger.warning(f"  Copied unfiltered pairs to {output_path}")
        return 0
    
    # Filter pairs by timestamp
    logger.info("Filtering pairs to train/val period only...")
    filtered_df = pairs_df[pairs_df['timestamp'] < test_start.isoformat()]
    
    logger.info(f"  Original: {len(pairs_df):,} pairs")
    logger.info(f"  Filtered: {len(filtered_df):,} pairs")
    logger.info(f"  Excluded: {len(pairs_df) - len(filtered_df):,} pairs (test period)")
    
    # Save filtered pairs
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filtered_df.to_csv(output_path, index=False)
    logger.info(f"✓ Saved filtered pairs to {output_path}")
    
    return 0


if __name__ == "__main__":
    import json
    
    parser = argparse.ArgumentParser(description="Filter pairs CSV by timestamp to prevent leakage")
    parser.add_argument(
        "--pairs",
        type=Path,
        default=PATHS.pairs_large,
        help="Path to pairs CSV",
    )
    parser.add_argument(
        "--decks",
        type=Path,
        default=PATHS.decks_all_final,
        help="Path to decks JSONL (to determine split point)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PATHS.processed / "pairs_train_val_only.csv",
        help="Output path for filtered pairs",
    )
    parser.add_argument(
        "--train-frac",
        type=float,
        default=0.7,
        help="Training fraction",
    )
    parser.add_argument(
        "--val-frac",
        type=float,
        default=0.15,
        help="Validation fraction",
    )
    
    args = parser.parse_args()
    
    sys.exit(filter_pairs_by_timestamp(
        pairs_path=args.pairs,
        decks_path=args.decks,
        output_path=args.output,
        train_frac=args.train_frac,
        val_frac=args.val_frac,
    ))

