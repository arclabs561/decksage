#!/usr/bin/env python3
"""
Smart fix for mismatched edges using edge context.

When edges have mismatched game labels, use the edge's game label
and the majority of edges for a card to determine the correct game.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path

from ..data.card_database import get_card_database
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def fix_mismatched_edges_smart(graph_db: Path) -> dict[str, int]:
    """Fix mismatched edges using edge context and card database."""
    logger.info("Fixing mismatched edges using smart context...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Find all mismatched edges
    mismatched = conn.execute("""
        SELECT e.card1, e.card2, e.game as edge_game, n1.game as node1_game, n2.game as node2_game
        FROM edges e
        JOIN nodes n1 ON e.card1 = n1.name
        JOIN nodes n2 ON e.card2 = n2.name
        WHERE e.game IS NOT NULL 
          AND n1.game IS NOT NULL 
          AND n2.game IS NOT NULL
          AND (e.game != n1.game OR e.game != n2.game)
    """).fetchall()
    
    logger.info(f"Found {len(mismatched)} mismatched edges")
    
    if len(mismatched) == 0:
        conn.close()
        return {"fixed_edges": 0, "fixed_nodes": 0}
    
    # Load card database
    card_db = get_card_database()
    card_db.load()
    
    # For each card, count what games its edges say it belongs to
    card_edge_games: dict[str, Counter] = {}
    
    for row in mismatched:
        card1 = row["card1"]
        card2 = row["card2"]
        edge_game = row["edge_game"]
        
        if card1 not in card_edge_games:
            card_edge_games[card1] = Counter()
        if card2 not in card_edge_games:
            card_edge_games[card2] = Counter()
        
        card_edge_games[card1][edge_game] += 1
        card_edge_games[card2][edge_game] += 1
    
    # Determine correct game for each card based on:
    # 1. Card database lookup (most reliable)
    # 2. Majority of edge games (context-based)
    # 3. Current node game (if consistent)
    
    game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO", "digimon": "DIG", "onepiece": "OP", "riftbound": "RFT"}
    
    card_correct_games: dict[str, str] = {}
    
    for card_name, edge_games in card_edge_games.items():
        # Method 1: Card database (most reliable)
        db_game = card_db.get_game(card_name, fuzzy=True)
        if db_game:
            db_game_code = game_map.get(db_game.lower())
            if db_game_code:
                card_correct_games[card_name] = db_game_code
                continue
        
        # Method 2: Majority of edge games
        if edge_games:
            most_common_game, count = edge_games.most_common(1)[0]
            total_edges = sum(edge_games.values())
            # If >70% of edges agree, use that
            if count / total_edges > 0.7:
                card_correct_games[card_name] = most_common_game
                continue
        
        # Method 3: Keep current if it's one of the edge games
        current_node = conn.execute(
            "SELECT game FROM nodes WHERE name = ?", (card_name,)
        ).fetchone()
        if current_node and current_node["game"] in edge_games:
            card_correct_games[card_name] = current_node["game"]
    
    logger.info(f"Determined correct games for {len(card_correct_games)} cards")
    
    # Now fix nodes and edges
    node_updates = []
    edge_updates = []
    
    for row in mismatched:
        card1 = row["card1"]
        card2 = row["card2"]
        edge_game = row["edge_game"]
        node1_game = row["node1_game"]
        node2_game = row["node2_game"]
        
        # Get correct games
        card1_correct = card_correct_games.get(card1)
        card2_correct = card_correct_games.get(card2)
        
        # Fix nodes
        if card1_correct and node1_game != card1_correct:
            node_updates.append((card1_correct, card1))
        if card2_correct and node2_game != card2_correct:
            node_updates.append((card2_correct, card2))
        
        # Fix edge - use the game that matches the nodes
        if card1_correct and card2_correct:
            if card1_correct == card2_correct:
                correct_edge_game = card1_correct
            else:
                # Cross-game edge - remove game label
                correct_edge_game = None
        elif card1_correct:
            correct_edge_game = card1_correct
        elif card2_correct:
            correct_edge_game = card2_correct
        else:
            continue  # Can't determine
        
        if edge_game != correct_edge_game:
            if correct_edge_game:
                edge_updates.append((correct_edge_game, card1, card2))
            else:
                edge_updates.append((None, card1, card2))
    
    # Batch update
    cursor = conn.cursor()
    
    if node_updates:
        logger.info(f"Updating {len(set(node_updates))} unique nodes...")
        cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", node_updates)
    
    if edge_updates:
        logger.info(f"Updating {len(edge_updates)} edges...")
        # Handle NULL updates separately
        null_updates = [(card1, card2) for game, card1, card2 in edge_updates if game is None]
        non_null_updates = [(game, card1, card2) for game, card1, card2 in edge_updates if game is not None]
        
        if null_updates:
            cursor.executemany(
                "UPDATE edges SET game = NULL WHERE card1 = ? AND card2 = ?",
                null_updates,
            )
        if non_null_updates:
            cursor.executemany(
                "UPDATE edges SET game = ? WHERE card1 = ? AND card2 = ?",
                non_null_updates,
            )
    
    conn.commit()
    conn.close()
    
    fixed_nodes = len(set(node_updates))
    fixed_edges = len(edge_updates)
    
    logger.info(f"Fixed {fixed_nodes} nodes and {fixed_edges} edges")
    
    return {"fixed_edges": fixed_edges, "fixed_nodes": fixed_nodes}


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Smart fix for mismatched edges")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Smart Fix for Mismatched Edges")
    logger.info("=" * 70)
    
    results = fix_mismatched_edges_smart(args.graph_db)
    
    logger.info(f"\n✓ Fixed {results['fixed_nodes']} nodes and {results['fixed_edges']} edges")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

