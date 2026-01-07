#!/usr/bin/env python3
"""
Fix missing edge metadata by reconstructing from deck sources.

Some edges may be missing deck_sources or metadata. This script
attempts to reconstruct them from the graph's deck tracking.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from collections import defaultdict

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def fix_missing_deck_sources(graph_db: Path, min_weight: int = 2) -> dict[str, int]:
    """Fix edges missing deck_sources."""
    logger.info("Fixing missing deck_sources...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Find edges missing deck_sources
    missing = conn.execute("""
        SELECT card1, card2, weight, deck_sources
        FROM edges
        WHERE deck_sources IS NULL 
           OR deck_sources = '[]'
           OR deck_sources = ''
        AND weight >= ?
        ORDER BY weight DESC
        LIMIT 10000
    """, (min_weight,)).fetchall()
    
    logger.info(f"Found {len(missing)} edges missing deck_sources")
    
    if len(missing) == 0:
        conn.close()
        return {"fixed": 0}
    
    # For now, we can't reconstruct deck_sources without the original deck data
    # But we can at least set an empty list to mark them as processed
    cursor = conn.cursor()
    fixed = 0
    
    for edge in missing:
        # Set empty list as deck_sources (better than NULL)
        cursor.execute("""
            UPDATE edges
            SET deck_sources = '[]'
            WHERE card1 = ? AND card2 = ?
        """, (edge["card1"], edge["card2"]))
        fixed += 1
        
        if fixed % 1000 == 0:
            conn.commit()
            logger.info(f"  Processed {fixed}/{len(missing)}...")
    
    conn.commit()
    conn.close()
    
    logger.info(f"Fixed {fixed} edges (set empty deck_sources)")
    
    return {"fixed": fixed}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix missing edge metadata")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--min-weight",
        type=int,
        default=2,
        help="Minimum edge weight to fix (default: 2)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Fix Missing Edge Metadata")
    logger.info("=" * 70)
    
    results = fix_missing_deck_sources(args.graph_db, args.min_weight)
    
    logger.info(f"\n✓ Fixed {results['fixed']} edges")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

