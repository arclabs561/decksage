#!/usr/bin/env python3
"""
Fix game label mismatches between edges and nodes.

Some edges have game labels that don't match their connected nodes.
This script fixes these inconsistencies.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def fix_game_label_mismatches(graph_db: Path) -> dict[str, int]:
    """Fix game label mismatches between edges and nodes."""
    logger.info("Fixing game label mismatches...")
    
    # Load card database for validation
    from ..data.card_database import get_card_database
    card_db = get_card_database()
    card_db.load()
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Find mismatched edges (edge game doesn't match both nodes)
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
    
    fixed_edges = 0
    fixed_nodes = 0
    ambiguous = 0
    
    cursor = conn.cursor()
    for row in mismatched:
        edge_game = row["edge_game"]
        node1_game = row["node1_game"]
        node2_game = row["node2_game"]
        card1 = row["card1"]
        card2 = row["card2"]
        
        # Use card database to determine correct game for each card
        card1_game = card_db.get_game(card1, fuzzy=True)
        card2_game = card_db.get_game(card2, fuzzy=True)
        
        # Map to uppercase codes
        game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO", "digimon": "DIG", "onepiece": "OP", "riftbound": "RFT"}
        card1_game_code = game_map.get(card1_game.lower()) if card1_game else None
        card2_game_code = game_map.get(card2_game.lower()) if card2_game else None
        
        # Determine correct game for edge (should match both nodes)
        if node1_game == node2_game:
            # Both nodes agree - use that
            correct_edge_game = node1_game
            # But verify with card database
            if card1_game_code and card1_game_code != node1_game:
                # Node might be wrong - fix node
                cursor.execute("UPDATE nodes SET game = ? WHERE name = ?", (card1_game_code, card1))
                fixed_nodes += 1
            if card2_game_code and card2_game_code != node2_game:
                cursor.execute("UPDATE nodes SET game = ? WHERE name = ?", (card2_game_code, card2))
                fixed_nodes += 1
        elif node1_game != node2_game:
            # Nodes disagree - use card database to determine correct game
            if card1_game_code == card2_game_code and card1_game_code:
                # Cards are from same game - use that
                correct_edge_game = card1_game_code
                # Fix both nodes
                if node1_game != card1_game_code:
                    cursor.execute("UPDATE nodes SET game = ? WHERE name = ?", (card1_game_code, card1))
                    fixed_nodes += 1
                if node2_game != card2_game_code:
                    cursor.execute("UPDATE nodes SET game = ? WHERE name = ?", (card2_game_code, card2))
                    fixed_nodes += 1
            elif card1_game_code:
                # Use card1's game
                correct_edge_game = card1_game_code
                if node1_game != card1_game_code:
                    cursor.execute("UPDATE nodes SET game = ? WHERE name = ?", (card1_game_code, card1))
                    fixed_nodes += 1
            elif card2_game_code:
                # Use card2's game
                correct_edge_game = card2_game_code
                if node2_game != card2_game_code:
                    cursor.execute("UPDATE nodes SET game = ? WHERE name = ?", (card2_game_code, card2))
                    fixed_nodes += 1
            else:
                # Can't determine - mark as ambiguous
                ambiguous += 1
                continue
        else:
            ambiguous += 1
            continue
        
        # Update edge if different
        if edge_game != correct_edge_game and correct_edge_game:
            cursor.execute(
                "UPDATE edges SET game = ? WHERE card1 = ? AND card2 = ?",
                (correct_edge_game, card1, card2),
            )
            fixed_edges += 1
    
    conn.commit()
    conn.close()
    
    logger.info(f"Fixed {fixed_edges} edge game labels")
    logger.info(f"Fixed {fixed_nodes} node game labels")
    logger.info(f"Ambiguous (could not determine): {ambiguous}")
    
    return {"fixed_edges": fixed_edges, "fixed_nodes": fixed_nodes, "ambiguous": ambiguous}


def remove_zero_weight_edges(graph_db: Path) -> int:
    """Remove edges with zero weight."""
    logger.info("Removing zero-weight edges...")
    
    conn = sqlite3.connect(str(graph_db))
    
    count = conn.execute("SELECT COUNT(*) FROM edges WHERE weight = 0").fetchone()[0]
    
    if count > 0:
        conn.execute("DELETE FROM edges WHERE weight = 0")
        conn.commit()
        logger.info(f"Removed {count} zero-weight edges")
    else:
        logger.info("No zero-weight edges found")
    
    conn.close()
    return count


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix game label mismatches")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--remove-zero-weights",
        action="store_true",
        help="Remove zero-weight edges",
    )
    
    args = parser.parse_args()
    
    # Fix mismatches
    results = fix_game_label_mismatches(args.graph_db)
    
    # Remove zero-weight edges if requested
    if args.remove_zero_weights:
        removed = remove_zero_weight_edges(args.graph_db)
        results["zero_weight_removed"] = removed
    
    logger.info("=" * 70)
    logger.info("Fix Complete")
    logger.info("=" * 70)
    logger.info(f"Fixed: {results['fixed_edges']} edge game labels")
    logger.info(f"Fixed: {results['fixed_nodes']} node game labels")
    logger.info(f"Ambiguous: {results['ambiguous']}")
    if "zero_weight_removed" in results:
        logger.info(f"Removed: {results['zero_weight_removed']} zero-weight edges")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

