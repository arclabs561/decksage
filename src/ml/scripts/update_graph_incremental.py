#!/usr/bin/env python3
"""
Incremental Graph Update Pipeline

Updates the card co-occurrence graph with new deck data.
Supports daily incremental updates, weekly retraining, monthly rebuilds.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from ..data.incremental_graph import IncrementalCardGraph
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS


logger = setup_script_logging()


def load_decks_from_jsonl(file_path: Path) -> list[dict]:
    """Load decks from JSONL file."""
    decks = []
    with open(file_path) as f:
        for line in f:
            if line.strip():
                decks.append(json.loads(line))
    return decks


def update_graph_incremental(
    graph_path: Path,
    new_decks_path: Path | None = None,
    decks: list[dict] | None = None,
    use_sqlite: bool = True,
) -> IncrementalCardGraph:
    """
    Update graph incrementally with new decks.

    Args:
        graph_path: Path to graph database
        new_decks_path: Path to new decks JSONL file
        decks: List of deck dicts (alternative to file path)

    Returns:
        Updated graph
    """
    # Load existing graph (auto-detect SQLite from extension)
    if graph_path:
        use_sqlite = (
            use_sqlite if graph_path.suffix == ".db" else (not graph_path.suffix == ".json")
        )
    graph = IncrementalCardGraph(graph_path, use_sqlite=use_sqlite)

    logger.info(f"Loaded graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    # Load new decks
    if new_decks_path:
        logger.info(f"Loading new decks from: {new_decks_path}")
        new_decks = load_decks_from_jsonl(new_decks_path)
    elif decks:
        new_decks = decks
    else:
        raise ValueError("Must provide either new_decks_path or decks")

    logger.info(f"Processing {len(new_decks)} new decks...")

    # Add decks incrementally
    for i, deck in enumerate(new_decks):
        deck_id = deck.get("deck_id") or deck.get("id") or f"deck_{i}"

        # Extract timestamp
        timestamp_str = (
            deck.get("timestamp")
            or deck.get("date")
            or deck.get("scraped_at")
            or deck.get("event_date")
        )
        if timestamp_str:
            try:
                # Handle various timestamp formats
                if isinstance(timestamp_str, str):
                    # Remove timezone Z and convert to datetime
                    timestamp_str = timestamp_str.replace("Z", "+00:00")
                timestamp = datetime.fromisoformat(timestamp_str)
            except Exception:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()

        # Extract format from deck structure (multiple possible locations)
        format_value = None
        if "format" in deck:
            format_value = deck["format"]
        elif "type" in deck and isinstance(deck["type"], dict):
            inner = deck["type"].get("inner")
            if isinstance(inner, dict) and "format" in inner:
                format_value = inner["format"]

        # Extract other metadata
        event_date = (
            deck.get("event_date")
            or deck.get("eventDate")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("eventDate")
        )
        placement = deck.get("placement") or (
            deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
        ).get("placement")
        archetype = deck.get("archetype") or (
            deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
        ).get("archetype")

        # Extract enhanced tournament metadata
        tournament_type = (
            deck.get("tournament_type")
            or deck.get("tournamentType")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("tournamentType")
        )
        tournament_size = (
            deck.get("tournament_size")
            or deck.get("tournamentSize")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("tournamentSize")
        )
        location = deck.get("location") or (
            deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
        ).get("location")
        region = deck.get("region") or (
            deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
        ).get("region")
        tournament_id = (
            deck.get("tournament_id")
            or deck.get("tournamentId")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("tournamentId")
        )
        days_since_rotation = (
            deck.get("days_since_rotation")
            or deck.get("daysSinceRotation")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("daysSinceRotation")
        )
        days_since_ban = (
            deck.get("days_since_ban_update")
            or deck.get("daysSinceBanUpdate")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("daysSinceBanUpdate")
        )
        meta_share = (
            deck.get("meta_share")
            or deck.get("metaShare")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("metaShare")
        )

        # Set deck metadata before adding deck (so format is available for temporal tracking)
        deck_metadata = {}
        if format_value:
            deck_metadata["format"] = format_value
        if event_date:
            deck_metadata["event_date"] = event_date
        if placement:
            deck_metadata["placement"] = placement
        if archetype:
            deck_metadata["archetype"] = archetype
        if tournament_type:
            deck_metadata["tournament_type"] = tournament_type
        if tournament_size:
            deck_metadata["tournament_size"] = tournament_size
        if location:
            deck_metadata["location"] = location
        if region:
            deck_metadata["region"] = region
        if tournament_id:
            deck_metadata["tournament_id"] = tournament_id
        if days_since_rotation is not None:
            deck_metadata["days_since_rotation"] = days_since_rotation
        if days_since_ban is not None:
            deck_metadata["days_since_ban_update"] = days_since_ban
        if meta_share is not None:
            deck_metadata["meta_share"] = meta_share

        # Extract round results if available
        round_results = (
            deck.get("roundResults")
            or deck.get("round_results")
            or (
                deck.get("type", {}).get("inner", {}) if isinstance(deck.get("type"), dict) else {}
            ).get("roundResults")
        )
        if round_results:
            deck_metadata["round_results"] = round_results

        if deck_metadata:
            graph.set_deck_metadata(deck_id, deck_metadata)

        # Add deck to graph (will use metadata for temporal tracking)
        graph.add_deck(deck, timestamp=timestamp, deck_id=deck_id)

        if (i + 1) % 1000 == 0:
            logger.info(f"  Processed {i + 1}/{len(new_decks)} decks...")

    # Save updated graph
    graph.save(graph_path)

    stats = graph.get_statistics()
    logger.info(f"✓ Graph updated: {stats['num_nodes']} nodes, {stats['num_edges']} edges")
    logger.info(f"  Total decks processed: {stats['total_decks_processed']}")

    return graph


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Update card co-occurrence graph incrementally")
    parser.add_argument(
        "--graph-path",
        type=Path,
        default=PATHS.data / "graphs" / "incremental_graph.db",
        help="Path to graph database (SQLite .db or JSON .json)",
    )
    parser.add_argument(
        "--use-sqlite",
        action="store_true",
        default=True,
        help="Use SQLite storage (default: True, set to False for JSON)",
    )
    parser.add_argument(
        "--no-sqlite",
        dest="use_sqlite",
        action="store_false",
        help="Use JSON storage instead of SQLite",
    )
    parser.add_argument(
        "--new-decks",
        type=Path,
        help="Path to new decks JSONL file",
    )
    parser.add_argument(
        "--decks-file",
        type=Path,
        default=PATHS.processed / "decks_all_final.jsonl",
        help="Path to all decks file (for full rebuild)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild graph from scratch",
    )
    parser.add_argument(
        "--export-edgelist",
        type=Path,
        help="Export edgelist for GNN training",
    )
    parser.add_argument(
        "--min-weight",
        type=int,
        default=2,
        help="Minimum edge weight for export",
    )

    args = parser.parse_args()

    if args.rebuild:
        logger.info("Rebuilding graph from scratch...")
        all_decks = load_decks_from_jsonl(args.decks_file)
        graph = IncrementalCardGraph(graph_path=args.graph_path, use_sqlite=args.use_sqlite)
        graph.rebuild_from_decks(all_decks)
        graph.save(args.graph_path)
        logger.info("✓ Graph rebuilt")
    else:
        if not args.new_decks:
            logger.error("Must provide --new-decks for incremental update (or use --rebuild)")
            return 1

        graph = update_graph_incremental(
            graph_path=args.graph_path,
            new_decks_path=args.new_decks,
            use_sqlite=args.use_sqlite,
        )

    # Export edgelist if requested
    if args.export_edgelist:
        logger.info(f"Exporting edgelist to: {args.export_edgelist}")
        graph.export_edgelist(args.export_edgelist, min_weight=args.min_weight)
        logger.info("✓ Edgelist exported")

    # Print statistics
    stats = graph.get_statistics()
    logger.info("\nGraph Statistics:")
    logger.info(f"  Nodes: {stats['num_nodes']:,}")
    logger.info(f"  Edges: {stats['num_edges']:,}")
    logger.info(f"  Avg degree: {stats['avg_degree']:.2f}")
    logger.info(f"  Avg edge weight: {stats['avg_edge_weight']:.2f}")
    logger.info(f"  Total decks: {stats['total_decks_processed']:,}")

    return 0


if __name__ == "__main__":
    exit(main())
