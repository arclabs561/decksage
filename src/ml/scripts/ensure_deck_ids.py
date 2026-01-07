#!/usr/bin/env python3
"""
Ensure all decks have proper deck_id for deck_sources tracking.

This script can be used to retroactively add deck_ids to decks before
adding them to the graph, ensuring proper deck_sources tracking.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def ensure_deck_ids(decks_file: Path, output_file: Path | None = None) -> dict[str, int]:
    """
    Ensure all decks have proper deck_id.
    
    Args:
        decks_file: Path to JSONL file with decks
        output_file: Optional output file (default: overwrite input)
        
    Returns:
        Dictionary with statistics
    """
    logger.info(f"Ensuring deck_ids in {decks_file}...")
    
    if output_file is None:
        output_file = decks_file
    
    decks_with_ids = []
    decks_fixed = 0
    decks_skipped = 0
    
    with open(decks_file) as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            
            try:
                deck = json.loads(line)
                
                # Check if deck_id exists and is valid
                deck_id = deck.get("deck_id") or deck.get("id")
                
                if not deck_id or deck_id.startswith("deck_"):
                    # Generate proper deck_id
                    deck_str = json.dumps(deck, sort_keys=True)
                    deck_hash = hashlib.md5(deck_str.encode()).hexdigest()[:12]
                    
                    # Try to use existing identifiers
                    if deck.get("deck_id"):
                        base_id = deck["deck_id"]
                    elif deck.get("id"):
                        base_id = deck["id"]
                    else:
                        # Use source file name or other metadata
                        source = deck.get("source") or deck.get("file") or "unknown"
                        base_id = f"{source}_{i}"
                    
                    deck_id = f"{base_id}_{deck_hash}"
                    deck["deck_id"] = deck_id
                    decks_fixed += 1
                else:
                    decks_skipped += 1
                
                decks_with_ids.append(deck)
                
                if (i + 1) % 1000 == 0:
                    logger.info(f"  Processed {i + 1} decks... (fixed: {decks_fixed})")
            
            except Exception as e:
                logger.warning(f"Error processing deck {i}: {e}")
                continue
    
    # Write updated decks
    logger.info(f"Writing {len(decks_with_ids)} decks to {output_file}...")
    with open(output_file, "w") as f:
        for deck in decks_with_ids:
            f.write(json.dumps(deck) + "\n")
    
    logger.info(f"Fixed {decks_fixed} decks, skipped {decks_skipped} (already had IDs)")
    
    return {
        "total": len(decks_with_ids),
        "fixed": decks_fixed,
        "skipped": decks_skipped,
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Ensure all decks have proper deck_id")
    parser.add_argument(
        "--decks-file",
        type=Path,
        required=True,
        help="Path to JSONL file with decks",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (default: overwrite input)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Ensure Deck IDs")
    logger.info("=" * 70)
    
    results = ensure_deck_ids(args.decks_file, args.output)
    
    logger.info(f"\n✓ Processed {results['total']} decks")
    logger.info(f"  Fixed: {results['fixed']}")
    logger.info(f"  Skipped: {results['skipped']}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

