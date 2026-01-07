#!/usr/bin/env python3
"""
Fix all remaining graph quality issues.

Comprehensive fix script that:
1. Fixes remaining game label mismatches
2. Attempts to fix unknown nodes using all available methods
3. Validates fixes
4. Generates final QA report
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

from ..data.card_database import get_card_database
from ..data.spanish_card_translations import translate_spanish_name, normalize_split_card_name
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def fix_remaining_mismatches(graph_db: Path) -> dict[str, int]:
    """Fix remaining game label mismatches using card database."""
    logger.info("Fixing remaining game label mismatches...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Find mismatched edges
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
    
    logger.info(f"Found {len(mismatched)} remaining mismatched edges")
    
    if len(mismatched) == 0:
        conn.close()
        return {"fixed_edges": 0, "fixed_nodes": 0, "cross_game": 0}
    
    # Load card database only if needed
    card_db = get_card_database()
    card_db.load()
    
    game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO", "digimon": "DIG", "onepiece": "OP", "riftbound": "RFT"}
    
    fixed_edges = 0
    fixed_nodes = 0
    cross_game_edges = 0  # Legitimate cross-game edges
    
    # Batch updates
    edge_updates = []
    node_updates = []
    cross_game_edges_list = []
    
    cursor = conn.cursor()
    for i, row in enumerate(mismatched):
        if i % 100 == 0 and i > 0:
            logger.info(f"  Processing {i}/{len(mismatched)} mismatches...")
        
        card1 = row["card1"]
        card2 = row["card2"]
        edge_game = row["edge_game"]
        node1_game = row["node1_game"]
        node2_game = row["node2_game"]
        
        # Check if cards are actually from different games (legitimate cross-game edge)
        card1_game = card_db.get_game(card1, fuzzy=True)
        card2_game = card_db.get_game(card2, fuzzy=True)
        
        card1_game_code = game_map.get(card1_game.lower()) if card1_game else None
        card2_game_code = game_map.get(card2_game.lower()) if card2_game else None
        
        # If cards are from different games, this is legitimate - mark edge as None/Unknown
        if card1_game_code and card2_game_code and card1_game_code != card2_game_code:
            cross_game_edges_list.append((card1, card2))
            cross_game_edges += 1
            continue
        
        # Otherwise, determine correct game
        if node1_game == node2_game:
            correct_game = node1_game
        elif card1_game_code and card1_game_code == card2_game_code:
            correct_game = card1_game_code
            # Fix nodes if needed
            if node1_game != card1_game_code:
                node_updates.append((card1_game_code, card1))
            if node2_game != card2_game_code:
                node_updates.append((card2_game_code, card2))
        elif card1_game_code:
            correct_game = card1_game_code
            if node1_game != card1_game_code:
                node_updates.append((card1_game_code, card1))
        elif card2_game_code:
            correct_game = card2_game_code
            if node2_game != card2_game_code:
                node_updates.append((card2_game_code, card2))
        else:
            # Can't determine - skip
            continue
        
        # Update edge
        if edge_game != correct_game:
            edge_updates.append((correct_game, card1, card2))
            fixed_edges += 1
    
    # Batch execute updates
    if cross_game_edges_list:
        logger.info(f"  Marking {len(cross_game_edges_list)} cross-game edges...")
        cursor.executemany(
            "UPDATE edges SET game = NULL WHERE card1 = ? AND card2 = ?",
            cross_game_edges_list,
        )
    
    if node_updates:
        logger.info(f"  Updating {len(node_updates)} node game labels...")
        cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", node_updates)
        fixed_nodes = len(set(node_updates))  # Count unique nodes
    
    if edge_updates:
        logger.info(f"  Updating {len(edge_updates)} edge game labels...")
        cursor.executemany(
            "UPDATE edges SET game = ? WHERE card1 = ? AND card2 = ?",
            edge_updates,
        )
    
    conn.commit()
    conn.close()
    
    logger.info(f"Fixed {fixed_edges} edge game labels")
    logger.info(f"Fixed {fixed_nodes} node game labels")
    logger.info(f"Marked {cross_game_edges} as cross-game edges (legitimate)")
    
    return {"fixed_edges": fixed_edges, "fixed_nodes": fixed_nodes, "cross_game": cross_game_edges}


def fix_unknown_nodes_aggressive(graph_db: Path) -> dict[str, int]:
    """Aggressively fix unknown nodes using all available methods."""
    logger.info("Fixing unknown nodes (aggressive mode)...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    # Get unknown nodes
    unknown_nodes = conn.execute("""
        SELECT name, total_decks, attributes
        FROM nodes
        WHERE game IS NULL OR game = 'Unknown'
        ORDER BY total_decks DESC
    """).fetchall()
    
    logger.info(f"Found {len(unknown_nodes)} unknown nodes")
    
    if len(unknown_nodes) == 0:
        conn.close()
        return {"fixed": 0, "not_found": 0}
    
    # Load card database
    card_db = get_card_database()
    card_db.load()
    
    game_map = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO", "digimon": "DIG", "onepiece": "OP", "riftbound": "RFT"}
    
    # Cache for name variants
    from ..data.card_name_normalizer import get_name_variants
    
    fixed = 0
    not_found = 0
    node_updates = []
    
    for i, row in enumerate(unknown_nodes):
        if i % 100 == 0 and i > 0:
            logger.info(f"  Processing {i}/{len(unknown_nodes)} unknown nodes...")
        
        card_name = row["name"]
        
        # Try multiple methods
        game = None
        
        # Method 1: Direct lookup
        game = card_db.get_game(card_name, fuzzy=True)
        
        # Method 2: Spanish translation
        if not game:
            normalized = normalize_split_card_name(card_name)
            english_name = translate_spanish_name(normalized)
            if english_name and english_name != normalized:
                game = card_db.get_game(english_name, fuzzy=True)
        
        # Method 3: Try name variants
        if not game:
            variants = get_name_variants(card_name)
            for variant in variants:
                if variant == card_name:
                    continue  # Skip original
                game = card_db.get_game(variant, fuzzy=True)
                if game:
                    break
        
        if game:
            game_code = game_map.get(game.lower())
            if game_code:
                node_updates.append((game_code, card_name))
                fixed += 1
            else:
                not_found += 1
        else:
            not_found += 1
    
    # Batch update
    if node_updates:
        logger.info(f"  Updating {len(node_updates)} nodes...")
        cursor = conn.cursor()
        cursor.executemany("UPDATE nodes SET game = ? WHERE name = ?", node_updates)
        conn.commit()
    
    conn.close()
    
    logger.info(f"Fixed {fixed} unknown nodes")
    logger.info(f"Still unknown: {not_found}")
    
    return {"fixed": fixed, "not_found": not_found}


def validate_fixes(graph_db: Path) -> dict[str, Any]:
    """Validate that fixes were successful."""
    logger.info("Validating fixes...")
    
    conn = sqlite3.connect(str(graph_db))
    
    validation = {}
    
    # Check mismatches
    mismatched = conn.execute("""
        SELECT COUNT(*) 
        FROM edges e
        JOIN nodes n1 ON e.card1 = n1.name
        JOIN nodes n2 ON e.card2 = n2.name
        WHERE e.game IS NOT NULL 
          AND n1.game IS NOT NULL 
          AND n2.game IS NOT NULL
          AND (e.game != n1.game OR e.game != n2.game)
    """).fetchone()[0]
    
    # Check unknown nodes
    unknown = conn.execute("""
        SELECT COUNT(*) 
        FROM nodes 
        WHERE game IS NULL OR game = 'Unknown'
    """).fetchone()[0]
    
    # Check zero weights
    zero_weight = conn.execute("""
        SELECT COUNT(*) 
        FROM edges 
        WHERE weight = 0
    """).fetchone()[0]
    
    # Check corrupted weights
    corrupted = conn.execute("""
        SELECT COUNT(*) 
        FROM edges 
        WHERE weight > 100000
    """).fetchone()[0]
    
    conn.close()
    
    validation = {
        "mismatched_edges": mismatched,
        "unknown_nodes": unknown,
        "zero_weight_edges": zero_weight,
        "corrupted_weights": corrupted,
        "all_fixed": mismatched == 0 and unknown == 0 and zero_weight == 0 and corrupted == 0,
    }
    
    logger.info(f"Validation results:")
    logger.info(f"  Mismatched edges: {mismatched}")
    logger.info(f"  Unknown nodes: {unknown}")
    logger.info(f"  Zero-weight edges: {zero_weight}")
    logger.info(f"  Corrupted weights: {corrupted}")
    
    return validation


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix all remaining graph issues")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validation after fixes",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("Fixing All Remaining Issues")
    logger.info("=" * 70)
    
    # 1. Fix remaining mismatches
    logger.info("\n[1/3] Fixing remaining game label mismatches...")
    mismatch_results = fix_remaining_mismatches(args.graph_db)
    
    # 2. Fix unknown nodes
    logger.info("\n[2/3] Fixing unknown nodes (aggressive mode)...")
    unknown_results = fix_unknown_nodes_aggressive(args.graph_db)
    
    # 3. Validate fixes
    if not args.skip_validation:
        logger.info("\n[3/3] Validating fixes...")
        validation = validate_fixes(args.graph_db)
        
        logger.info("\n" + "=" * 70)
        logger.info("Fix Summary")
        logger.info("=" * 70)
        logger.info(f"Mismatches fixed: {mismatch_results['fixed_edges']} edges, {mismatch_results['fixed_nodes']} nodes")
        logger.info(f"Cross-game edges: {mismatch_results['cross_game']} (legitimate)")
        logger.info(f"Unknown nodes fixed: {unknown_results['fixed']}")
        logger.info(f"Remaining unknown: {unknown_results['not_found']}")
        logger.info(f"\nValidation:")
        logger.info(f"  Mismatched edges: {validation['mismatched_edges']}")
        logger.info(f"  Unknown nodes: {validation['unknown_nodes']}")
        logger.info(f"  Zero-weight edges: {validation['zero_weight_edges']}")
        logger.info(f"  Corrupted weights: {validation['corrupted_weights']}")
        
        if validation["all_fixed"]:
            logger.info("\n✓ All issues fixed!")
        else:
            logger.info("\n⚠ Some issues remain (may be legitimate edge cases)")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


