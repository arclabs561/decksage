#!/usr/bin/env python3
"""
Investigate remaining graph issues to understand what can be fixed.

Analyzes:
1. Mismatched edges - why they exist
2. Unknown nodes - what types of cards they are
3. Patterns that might help fix them
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from ..data.card_database import get_card_database
from ..qa.agentic_qa_agent import AgenticQAAgent
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def analyze_mismatched_edges(graph_db: Path, limit: int = 100) -> dict[str, Any]:
    """Analyze mismatched edges to understand patterns."""
    logger.info("Analyzing mismatched edges...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    mismatched = conn.execute("""
        SELECT e.card1, e.card2, e.game as edge_game, n1.game as node1_game, n2.game as node2_game
        FROM edges e
        JOIN nodes n1 ON e.card1 = n1.name
        JOIN nodes n2 ON e.card2 = n2.name
        WHERE e.game IS NOT NULL 
          AND n1.game IS NOT NULL 
          AND n2.game IS NOT NULL
          AND (e.game != n1.game OR e.game != n2.game)
        LIMIT ?
    """, (limit,)).fetchall()
    
    logger.info(f"Analyzing {len(mismatched)} mismatched edges...")
    
    patterns: dict[str, Any] = {
        "edge_vs_node1": Counter(),
        "edge_vs_node2": Counter(),
        "node1_vs_node2": Counter(),
        "both_nodes_same": 0,
        "nodes_differ": 0,
    }
    
    examples: list[dict[str, Any]] = []
    
    for row in mismatched:
        edge_game = row["edge_game"]
        node1_game = row["node1_game"]
        node2_game = row["node2_game"]
        
        patterns["edge_vs_node1"][f"{edge_game} vs {node1_game}"] += 1
        patterns["edge_vs_node2"][f"{edge_game} vs {node2_game}"] += 1
        patterns["node1_vs_node2"][f"{node1_game} vs {node2_game}"] += 1
        
        if node1_game == node2_game:
            patterns["both_nodes_same"] += 1
        else:
            patterns["nodes_differ"] += 1
        
        if len(examples) < 10:
            examples.append({
                "card1": row["card1"],
                "card2": row["card2"],
                "edge_game": edge_game,
                "node1_game": node1_game,
                "node2_game": node2_game,
            })
    
    conn.close()
    
    logger.info("Mismatch patterns:")
    logger.info(f"  Edge vs Node1: {dict(patterns['edge_vs_node1'].most_common(5))}")
    logger.info(f"  Edge vs Node2: {dict(patterns['edge_vs_node2'].most_common(5))}")
    logger.info(f"  Node1 vs Node2: {dict(patterns['node1_vs_node2'].most_common(5))}")
    logger.info(f"  Both nodes same: {patterns['both_nodes_same']}")
    logger.info(f"  Nodes differ: {patterns['nodes_differ']}")
    logger.info(f"\nExamples:")
    for ex in examples:
        logger.info(f"  {ex['card1']} <-> {ex['card2']}: edge={ex['edge_game']}, n1={ex['node1_game']}, n2={ex['node2_game']}")
    
    return {"patterns": patterns, "examples": examples}


def analyze_unknown_nodes(graph_db: Path, limit: int = 100) -> dict[str, Any]:
    """Analyze unknown nodes to understand what they are."""
    logger.info("Analyzing unknown nodes...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    unknown = conn.execute("""
        SELECT name, total_decks, attributes
        FROM nodes
        WHERE game IS NULL OR game = 'Unknown'
        ORDER BY total_decks DESC
        LIMIT ?
    """, (limit,)).fetchall()
    
    logger.info(f"Analyzing {len(unknown)} unknown nodes...")
    
    # Get card database (singleton, cached globally)
    # Only loads on first use - subsequent calls reuse cached instance
    card_db = get_card_database()
    # Explicit load with timing
    import time
    load_start = time.time()
    card_db.load()
    load_time = time.time() - load_start
    if load_time > 10:
        logger.warning(f"Card database loading took {load_time:.1f}s - consider optimizing")
    else:
        logger.debug(f"Card database loaded in {load_time:.2f}s")
    
    patterns: dict[str, int] = {
        "has_slash": 0,
        "has_spanish": 0,
        "has_numbers": 0,
        "short_names": 0,
        "long_names": 0,
        "found_in_db": 0,
        "not_found": 0,
    }
    
    examples: list[dict[str, Any]] = []
    
    for row in unknown:
        name = row["name"]
        total_decks = row["total_decks"]
        
        # Pattern detection
        if "//" in name:
            patterns["has_slash"] += 1
        if any(c in name.lower() for c in "áéíóúñ"):
            patterns["has_spanish"] += 1
        if any(c.isdigit() for c in name):
            patterns["has_numbers"] += 1
        if len(name) < 5:
            patterns["short_names"] += 1
        if len(name) > 30:
            patterns["long_names"] += 1
        
        # Try to find in database
        game = card_db.get_game(name, fuzzy=True)
        if game:
            patterns["found_in_db"] += 1
        else:
            patterns["not_found"] += 1
        
        if len(examples) < 20:
            examples.append({
                "name": name,
                "total_decks": total_decks,
                "found": game is not None,
                "game": game,
            })
    
    conn.close()
    
    logger.info("Unknown node patterns:")
    for key, value in patterns.items():
        logger.info(f"  {key}: {value}")
    logger.info(f"\nTop examples:")
    for ex in examples[:10]:
        status = f"found={ex['game']}" if ex["found"] else "not found"
        logger.info(f"  {ex['name']} (decks={ex['total_decks']}, {status})")
    
    return {"patterns": patterns, "examples": examples}


async def agentic_analysis(edge_analysis: dict[str, Any], node_analysis: dict[str, Any], graph_db: Path) -> None:
    """Use agentic tools to analyze findings and provide recommendations."""
    logger.info("\n[3/3] Running agentic analysis...")
    
    # Build issue description from findings
    issues = []
    details = []
    
    nodes_differ = edge_analysis.get("patterns", {}).get("nodes_differ", 0)
    if nodes_differ > 0:
        issues.append(f"Mismatched edges: {nodes_differ} edges have nodes with different games")
        # Get example pattern
        node1_vs_node2 = edge_analysis.get("patterns", {}).get("node1_vs_node2", {})
        if node1_vs_node2:
            pattern = list(node1_vs_node2.keys())[0] if isinstance(node1_vs_node2, dict) else str(node1_vs_node2)
            details.append(f"Pattern: {pattern} (e.g., MTG card connected to YGO card)")
    
    not_found = node_analysis.get("patterns", {}).get("not_found", 0)
    has_slash = node_analysis.get("patterns", {}).get("has_slash", 0)
    if not_found > 0:
        issues.append(f"Unknown nodes: {not_found} nodes not found in card database")
        if has_slash > 0:
            details.append(f"Note: {has_slash} of these have '//' in name (likely split cards)")
    
    if not issues:
        logger.info("  ✓ No issues detected in sample")
        return
    
    issue_description = "; ".join(issues)
    if details:
        issue_description += ". " + ". ".join(details)
    
    try:
        agent = AgenticQAAgent(graph_db=graph_db)
        
        logger.debug(f"Issue description: {issue_description}")
        analysis = await agent.analyze_quality_issue(issue_description)
        
        logger.info("\n" + "=" * 70)
        logger.info("Agentic Analysis & Recommendations")
        logger.info("=" * 70)
        logger.info(f"Severity: {analysis.severity}")
        logger.info(f"Root Cause: {analysis.root_cause}")
        logger.info(f"Impact: {analysis.impact}")
        logger.info(f"Recommended Fix: {analysis.recommended_fix}")
        logger.info(f"Confidence: {analysis.confidence:.1%}")
        
        agent.close()
    except ImportError:
        logger.warning("pydantic-ai not available, providing basic recommendations")
        # Provide basic recommendations even without LLM
        logger.info("\n" + "=" * 70)
        logger.info("Basic Recommendations (Non-Agentic)")
        logger.info("=" * 70)
        
        if nodes_differ > 0:
            logger.info("Issue: Mismatched game labels in edges")
            # Get specific examples
            examples = edge_analysis.get("examples", [])[:3]
            if examples:
                logger.info("Examples found:")
                for ex in examples:
                    logger.info(f"  - {ex['card1']} (MTG) <-> {ex['card2']} (YGO)")
                    if "//" in ex['card2']:
                        logger.info(f"    → '{ex['card2']}' is a split card, likely mislabeled as YGO")
            
            logger.info("Root Cause: Cards from different games connected (likely name collision or split card mislabeling)")
            logger.info("Recommended Fix:")
            logger.info("  1. Split cards (with '//') are being mislabeled - check normalization")
            # Check if scripts exist
            from pathlib import Path
            validate_script = Path("src/ml/scripts/validate_labels.py")
            update_script = Path("src/ml/scripts/update_graph_incremental.py")
            
            if validate_script.exists():
                logger.info("  2. Run: python -m src.ml.scripts.validate_labels --fix")
            else:
                logger.info("  2. Validate game labels (script: validate_labels.py)")
            
            if update_script.exists():
                logger.info("  3. Rebuild graph: python -m src.ml.scripts.update_graph_incremental")
            else:
                logger.info("  3. Rebuild graph after fixing labels")
        
        if not_found > 0:
            logger.info("\nIssue: Unknown nodes (not in card database)")
            # Get specific examples
            examples = node_analysis.get("examples", [])[:3]
            if examples:
                logger.info("Examples found:")
                for ex in examples:
                    logger.info(f"  - '{ex['name']}' (decks={ex['total_decks']}, not found)")
                    if "//" in ex['name']:
                        logger.info(f"    → Split card - may need special normalization")
                    elif len(ex['name']) < 5:
                        logger.info(f"    → Very short name - may be abbreviation or typo")
            
            logger.info("Root Cause: Card names not matching database (normalization, abbreviations, or new cards)")
            logger.info("Recommended Fix:")
            if has_slash > 0:
                logger.info("  1. Split cards (with '//') need special handling in normalization")
                logger.info("  2. Check if split card names are being parsed correctly")
            if any(len(ex.get('name', '')) < 5 for ex in node_analysis.get("examples", [])):
                logger.info("  3. Short names may be abbreviations - check if they're valid cards")
            logger.info("  4. Update card database or improve name normalization")
            logger.info("  5. For split cards: Ensure both halves are checked (e.g., 'Fire // Ice' → check 'Fire' and 'Ice')")
        
        if nodes_differ > 0 and not_found > 0:
            logger.info("\n⚠️  CRITICAL: These issues are likely related:")
            logger.info("   Pattern: Cards with '//' (split cards) are causing:")
            logger.info("     - Game label mismatches (split card mislabeled as wrong game)")
            logger.info("     - 'Not found' errors (split card name not in database)")
            logger.info("   Root cause: Split card normalization is broken")
            logger.info("   Priority fix: Handle split cards properly in name normalization")
            logger.info("   Impact: High - affects card matching and game labeling")
    except Exception as e:
        logger.error(f"Agentic analysis failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Investigate remaining graph issues")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Limit for analysis samples",
    )
    parser.add_argument(
        "--use-agentic",
        action="store_true",
        default=True,
        help="Use agentic analysis for recommendations",
    )
    
    args = parser.parse_args()
    
    import time
    total_start = time.time()
    
    logger.info("=" * 70)
    logger.info("Investigating Remaining Issues")
    logger.info("=" * 70)
    
    # Analyze mismatched edges
    logger.info("\n[1/3] Analyzing mismatched edges...")
    step_start = time.time()
    edge_analysis = analyze_mismatched_edges(args.graph_db, args.limit)
    step_time = time.time() - step_start
    logger.debug(f"Edge analysis took {step_time:.2f}s")
    
    # Analyze unknown nodes
    logger.info("\n[2/3] Analyzing unknown nodes...")
    step_start = time.time()
    node_analysis = analyze_unknown_nodes(args.graph_db, args.limit)
    step_time = time.time() - step_start
    logger.debug(f"Unknown node analysis took {step_time:.2f}s")
    
    # Agentic analysis if enabled
    if args.use_agentic:
        asyncio.run(agentic_analysis(edge_analysis, node_analysis, args.graph_db))
    else:
        logger.info("\n[3/3] Agentic analysis skipped")
    
    total_time = time.time() - total_start
    
    logger.info("\n" + "=" * 70)
    logger.info("Summary")
    logger.info("=" * 70)
    
    # Count issues found
    nodes_differ = edge_analysis.get("patterns", {}).get("nodes_differ", 0)
    not_found = node_analysis.get("patterns", {}).get("not_found", 0)
    
    if nodes_differ > 0 or not_found > 0:
        logger.info(f"Issues found: {nodes_differ} mismatched edges, {not_found} unknown nodes")
        logger.info("See recommendations above for specific fixes.")
    else:
        logger.info("✓ No issues detected in sample")
    
    logger.info(f"\nTotal analysis time: {total_time:.1f}s")
    if total_time > 60:
        logger.warning(f"Analysis took {total_time:.1f}s - consider optimizing card database loading")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

