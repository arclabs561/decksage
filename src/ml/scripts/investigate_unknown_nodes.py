#!/usr/bin/env python3
"""
Investigate unknown nodes in graph to understand what cards are unlabeled.

Helps identify:
- Typos or name variations
- Cards from unsupported games
- Cards that need better normalization
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
from collections import Counter
from pathlib import Path

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS
from ..data.card_database import get_card_database
from ..qa.agentic_qa_agent import AgenticQAAgent

logger = setup_script_logging()


def investigate_unknown_nodes(
    graph_db: Path,
    limit: int = 100,
    show_edges: bool = False,
) -> None:
    """Investigate unknown nodes in graph."""
    logger.info(f"Investigating unknown nodes in {graph_db}...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Get unknown nodes with their stats
    query = """
        SELECT name, first_seen, last_seen, total_decks, attributes
        FROM nodes
        WHERE game IS NULL OR game = 'Unknown'
        ORDER BY total_decks DESC
        LIMIT ?
    """
    
    rows = conn.execute(query, (limit,)).fetchall()
    
    logger.info(f"Found {len(rows)} unknown nodes (showing top {limit} by deck count)")
    
    # Load card database for comparison
    card_db = get_card_database()
    card_db.load()
    
    # Analyze patterns
    patterns = {
        "likely_typos": [],
        "likely_other_game": [],
        "name_variations": [],
        "high_frequency": [],
    }
    
    for row in rows:
        name = row["name"]
        total_decks = row["total_decks"]
        
        # Try to find similar names in card database
        found_game = None
        try:
            found_game = card_db.get_game(name)
        except Exception:
            pass
        
        if found_game:
            patterns["name_variations"].append((name, found_game, total_decks))
        elif total_decks > 10:
            patterns["high_frequency"].append((name, total_decks))
        else:
            patterns["likely_typos"].append((name, total_decks))
    
    # Print analysis
    print("\n" + "=" * 80)
    print("UNKNOWN NODES ANALYSIS")
    print("=" * 80)
    
    if patterns["name_variations"]:
        print(f"\n📝 Name Variations (found in card DB): {len(patterns['name_variations'])}")
        for name, game, decks in patterns["name_variations"][:20]:
            print(f"  {name:40s} -> {game:5s} ({decks:5d} decks)")
    
    if patterns["high_frequency"]:
        print(f"\n🔥 High Frequency Unknown (>{10} decks): {len(patterns['high_frequency'])}")
        for name, decks in patterns["high_frequency"][:20]:
            print(f"  {name:40s} ({decks:5d} decks)")
    
    if patterns["likely_typos"]:
        print(f"\n❓ Low Frequency Unknown (<{10} decks): {len(patterns['likely_typos'])}")
        for name, decks in patterns["likely_typos"][:20]:
            print(f"  {name:40s} ({decks:5d} decks)")
    
    # Show edge statistics for unknown nodes
    if show_edges:
        print(f"\n📊 Edge Statistics for Unknown Nodes:")
        edge_query = """
            SELECT COUNT(*) as edge_count, SUM(weight) as total_weight
            FROM edges
            WHERE (card1 IN (
                SELECT name FROM nodes WHERE game IS NULL OR game = 'Unknown'
            ) OR card2 IN (
                SELECT name FROM nodes WHERE game IS NULL OR game = 'Unknown'
            ))
        """
        edge_row = conn.execute(edge_query).fetchone()
        if edge_row:
            print(f"  Total edges involving unknown nodes: {edge_row['edge_count']:,}")
            print(f"  Total weight: {edge_row['total_weight']:,}")
    
    # Show sample of unknown nodes
    print(f"\n📋 Sample Unknown Nodes (top {min(limit, 50)}):")
    for i, row in enumerate(rows[:50], 1):
        attrs = row["attributes"]
        attrs_str = ""
        if attrs:
            try:
                import json
                attrs_dict = json.loads(attrs) if isinstance(attrs, str) else attrs
                if attrs_dict:
                    attrs_str = f" | {', '.join(f'{k}={v}' for k, v in list(attrs_dict.items())[:2])}"
            except Exception:
                pass
        
        print(f"  {i:3d}. {row['name']:40s} | {row['total_decks']:5d} decks{attrs_str}")
    
    # Summary (before closing connection)
    total_unknown = conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE game IS NULL OR game = 'Unknown'"
    ).fetchone()[0]
    
    conn.close()
    
    print(f"\n📈 Summary:")
    print(f"  Total unknown nodes: {total_unknown:,}")
    print(f"  Name variations found: {len(patterns['name_variations']):,}")
    print(f"  High frequency unknown: {len(patterns['high_frequency']):,}")
    print(f"  Low frequency unknown: {len(patterns['likely_typos']):,}")


def main():
    parser = argparse.ArgumentParser(description="Investigate unknown nodes in graph")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=Path("data/graphs/incremental_graph.db"),
        help="Path to graph database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Number of unknown nodes to show",
    )
    parser.add_argument(
        "--show-edges",
        action="store_true",
        help="Show edge statistics for unknown nodes",
    )
    
    args = parser.parse_args()
    
    investigate_unknown_nodes(
        graph_db=args.graph_db,
        limit=args.limit,
        show_edges=args.show_edges,
    )


if __name__ == "__main__":
    main()

