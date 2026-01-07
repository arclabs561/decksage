#!/usr/bin/env python3
"""
Rebuild graph from all deck files with proper game detection.

Processes all deck JSONL files, infers game from file names,
and rebuilds graph with complete metadata.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..data.incremental_graph import IncrementalCardGraph
from ..data.card_database import get_card_database
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def infer_game_from_path(file_path: Path) -> str | None:
    """Infer game from file path."""
    path_str = str(file_path).lower()
    
    if "pokemon" in path_str or "pkm" in path_str:
        return "pokemon"
    elif "yugioh" in path_str or "ygo" in path_str:
        return "yugioh"
    elif "magic" in path_str or "mtg" in path_str:
        return "magic"
    elif "digimon" in path_str or "dig" in path_str:
        return "digimon"
    elif "onepiece" in path_str or "op" in path_str:
        return "onepiece"
    elif "riftbound" in path_str or "rift" in path_str:
        return "riftbound"
    
    return None


def load_card_attributes(attrs_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load card attributes from CSV (uses canonical implementation)."""
    from ml.utils.data_loading import load_card_attributes as load_attrs_canonical
    return load_attrs_canonical(attrs_path=attrs_path)


def find_all_deck_files(decks_dir: Path) -> list[tuple[Path, str]]:
    """Find all deck JSONL files and infer their games."""
    deck_files = []
    seen_files = set()
    
    # Check multiple directories
    search_dirs = [
        decks_dir,
        PATHS.processed,
        PATHS.data / "decks",
        PATHS.data,
    ]
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        # Look for game-specific files
        for pattern in ["decks_*.jsonl", "*_decks.jsonl", "**/decks_*.jsonl", "**/*_decks.jsonl"]:
            for file_path in search_dir.glob(pattern):
                if file_path.is_file() and file_path not in seen_files:
                    seen_files.add(file_path)
                    game = infer_game_from_path(file_path)
                    if game:
                        deck_files.append((file_path, game))
                    else:
                        logger.debug(f"Could not infer game from path: {file_path}")
    
    # Check for unified deck file (decks_all_final.jsonl)
    unified_file = PATHS.decks_all_final
    if unified_file.exists() and unified_file not in seen_files:
        # For unified file, we'll need to detect game per-deck
        deck_files.append((unified_file, None))  # None means detect per-deck
    
    return deck_files


def load_decks_from_file(file_path: Path, game: str | None) -> list[dict[str, Any]]:
    """Load decks from JSONL file and add game field."""
    decks = []
    
    try:
        with open(file_path) as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                
                try:
                    deck = json.loads(line)
                    # Add game field if not present
                    if "game" not in deck and game:
                        deck["game"] = game
                    # If game is None, try to infer from deck metadata or path
                    elif "game" not in deck:
                        inferred = infer_game_from_path(file_path)
                        if inferred:
                            deck["game"] = inferred
                    decks.append(deck)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in {file_path} line {line_num}: {e}")
                    continue
    except Exception as e:
        logger.error(f"Error reading {file_path}: {e}")
    
    return decks


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Rebuild graph from all deck files")
    parser.add_argument(
        "--graph-path",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--decks-dir",
        type=Path,
        default=PATHS.processed,
        help="Directory containing deck JSONL files",
    )
    parser.add_argument(
        "--card-attributes",
        type=Path,
        default=PATHS.card_attributes,
        help="Path to card attributes CSV",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Create backup before rebuilding",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Rebuilding Graph from All Deck Files")
    logger.info("=" * 70)
    
    # Find all deck files
    logger.info(f"Searching for deck files in {args.decks_dir}...")
    deck_files = find_all_deck_files(args.decks_dir)
    
    if not deck_files:
        logger.error("No deck files found!")
        return 1
    
    logger.info(f"Found {len(deck_files)} deck files:")
    for file_path, game in deck_files:
        logger.info(f"  {file_path.name} -> {game}")
    
    # Backup existing graph
    if args.backup and args.graph_path.exists():
        backup_path = args.graph_path.with_suffix(".db.backup")
        logger.info(f"Creating backup: {backup_path}")
        import shutil
        shutil.copy2(args.graph_path, backup_path)
    
    # Load card attributes
    card_attributes = load_card_attributes(args.card_attributes)
    
    # Initialize new graph
    logger.info(f"Initializing new graph at {args.graph_path}...")
    graph = IncrementalCardGraph(
        graph_path=args.graph_path,  # Set path so SQLite initializes
        use_sqlite=True,
        card_attributes=card_attributes if card_attributes else None,
    )
    
    # Load card database for game detection
    try:
        card_db = get_card_database()
        card_db.load()
        logger.info("Card database loaded")
    except Exception as e:
        logger.warning(f"Could not load card database: {e}")
    
    # Process all deck files
    total_decks = 0
    for file_path, game in deck_files:
        logger.info(f"\nProcessing {file_path.name} ({game or 'auto-detect'})...")
        
        # For unified files, load without game (will detect per-deck)
        if game is None:
            decks = load_decks_from_file(file_path, None)
        else:
            decks = load_decks_from_file(file_path, game)
        
        logger.info(f"  Loaded {len(decks)} decks")
        
        for i, deck in enumerate(decks):
            deck_id = deck.get("deck_id") or deck.get("id") or f"{game}_{i}"
            
            # Extract timestamp
            timestamp_str = (
                deck.get("timestamp")
                or deck.get("date")
                or deck.get("scraped_at")
                or deck.get("event_date")
            )
            from datetime import datetime
            if timestamp_str:
                try:
                    if isinstance(timestamp_str, str):
                        timestamp_str = timestamp_str.replace("Z", "+00:00")
                    timestamp = datetime.fromisoformat(timestamp_str)
                except Exception:
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()
            
            # Add deck to graph
            graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)
            total_decks += 1
            
            if (i + 1) % 1000 == 0:
                logger.info(f"  Processed {i + 1}/{len(decks)} decks...")
    
    logger.info(f"\n✓ Processed {total_decks:,} total decks")
    
    # Save graph
    logger.info(f"Saving graph to {args.graph_path}...")
    graph.save(args.graph_path)
    logger.info("✓ Graph saved")
    
    # Final statistics
    stats = graph.get_statistics()
    logger.info("\nFinal Statistics:")
    logger.info(f"  Nodes: {stats['num_nodes']:,}")
    logger.info(f"  Edges: {stats['num_edges']:,}")
    logger.info(f"  Total decks: {stats['total_decks_processed']:,}")
    logger.info(f"  Game distribution: {stats['game_distribution']}")
    logger.info(f"  Avg degree: {stats['avg_degree']:.2f}")
    logger.info(f"  Avg edge weight: {stats['avg_edge_weight']:.2f}")
    
    return 0


if __name__ == "__main__":
    exit(main())

