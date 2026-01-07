#!/usr/bin/env python3
"""
Fix corrupted edge weights in graph database.

Some edge weights appear to be corrupted (very large numbers).
This script identifies and fixes them by capping at reasonable values
or recalculating from deck sources.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def analyze_corrupted_weights(graph_db: Path) -> dict[str, int]:
    """Analyze corrupted weights in database."""
    conn = sqlite3.connect(str(graph_db))
    
    # Count corrupted edges (weight > 1M seems unreasonable)
    max_reasonable_weight = 1000000
    
    stats = {}
    stats["total_edges"] = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    stats["corrupted"] = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE weight > ?", (max_reasonable_weight,)
    ).fetchone()[0]
    stats["valid"] = stats["total_edges"] - stats["corrupted"]
    
    # Get sample of corrupted edges
    corrupted_sample = conn.execute(
        "SELECT card1, card2, weight FROM edges WHERE weight > ? ORDER BY weight DESC LIMIT 10",
        (max_reasonable_weight,),
    ).fetchall()
    
    conn.close()
    
    logger.info(f"Total edges: {stats['total_edges']:,}")
    logger.info(f"Corrupted (weight > {max_reasonable_weight:,}): {stats['corrupted']:,}")
    logger.info(f"Valid: {stats['valid']:,}")
    
    if corrupted_sample:
        logger.info("\nSample corrupted edges:")
        for card1, card2, weight in corrupted_sample:
            logger.info(f"  {card1} <-> {card2}: weight={weight}")
    
    return stats


def fix_corrupted_weights(
    graph_db: Path,
    max_weight: int = 1000000,
    fix_strategy: str = "cap",
) -> int:
    """
    Fix corrupted edge weights.
    
    Args:
        graph_db: Path to graph database
        max_weight: Maximum reasonable weight (edges above this are corrupted)
        fix_strategy: "cap" (cap at max_weight) or "recalculate" (recalculate from deck_sources)
    
    Returns:
        Number of edges fixed
    """
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Find corrupted edges
    corrupted = conn.execute(
        "SELECT card1, card2, weight, deck_sources FROM edges WHERE weight > ?",
        (max_weight,),
    ).fetchall()
    
    logger.info(f"Found {len(corrupted):,} corrupted edges")
    
    fixed_count = 0
    
    if fix_strategy == "cap":
        # Cap weights at max_weight
        logger.info(f"Capping weights at {max_weight:,}...")
        cursor = conn.cursor()
        for row in corrupted:
            cursor.execute(
                "UPDATE edges SET weight = ? WHERE card1 = ? AND card2 = ?",
                (max_weight, row["card1"], row["card2"]),
            )
            fixed_count += 1
        conn.commit()
        logger.info(f"Fixed {fixed_count:,} edges by capping weights")
    
    elif fix_strategy == "recalculate":
        # Recalculate from deck_sources count
        logger.info("Recalculating weights from deck_sources...")
        cursor = conn.cursor()
        for row in corrupted:
            import json
            
            deck_sources = row["deck_sources"]
            if deck_sources:
                try:
                    sources = json.loads(deck_sources) if isinstance(deck_sources, str) else deck_sources
                    new_weight = len(sources) if isinstance(sources, list) else 1
                    # Cap at reasonable value
                    new_weight = min(new_weight, max_weight)
                except Exception:
                    new_weight = 1
            else:
                new_weight = 1
            
            cursor.execute(
                "UPDATE edges SET weight = ? WHERE card1 = ? AND card2 = ?",
                (new_weight, row["card1"], row["card2"]),
            )
            fixed_count += 1
        conn.commit()
        logger.info(f"Fixed {fixed_count:,} edges by recalculating weights")
    
    conn.close()
    return fixed_count


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix corrupted edge weights in graph")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--max-weight",
        type=int,
        default=1000000,
        help="Maximum reasonable weight (edges above this are corrupted)",
    )
    parser.add_argument(
        "--strategy",
        choices=["cap", "recalculate"],
        default="cap",
        help="Fix strategy: cap (cap at max_weight) or recalculate (from deck_sources)",
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Only analyze, don't fix",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Edge Weight Corruption Analysis")
    logger.info("=" * 70)
    
    # Analyze
    stats = analyze_corrupted_weights(args.graph_db)
    
    if args.analyze_only:
        logger.info("\nAnalysis complete (--analyze-only, no fixes applied)")
        return 0
    
    if stats["corrupted"] == 0:
        logger.info("\nNo corrupted edges found. Nothing to fix.")
        return 0
    
    # Fix
    logger.info("\n" + "=" * 70)
    logger.info("Fixing Corrupted Edge Weights")
    logger.info("=" * 70)
    
    fixed = fix_corrupted_weights(
        graph_db=args.graph_db,
        max_weight=args.max_weight,
        fix_strategy=args.strategy,
    )
    
    logger.info("\n" + "=" * 70)
    logger.info("Fix Complete")
    logger.info("=" * 70)
    logger.info(f"Fixed {fixed:,} corrupted edges")
    
    # Verify
    logger.info("\nVerifying fix...")
    stats_after = analyze_corrupted_weights(args.graph_db)
    if stats_after["corrupted"] == 0:
        logger.info("✓ All corrupted edges fixed!")
    else:
        logger.warning(f"Still {stats_after['corrupted']:,} corrupted edges remaining")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


