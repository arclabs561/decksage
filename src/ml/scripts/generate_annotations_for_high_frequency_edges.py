#!/usr/bin/env python3
"""
Generate annotations for high-frequency edges in the graph.

Selects edges with high co-occurrence counts and generates LLM annotations
for them to improve training data quality.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from ..data.incremental_graph import IncrementalCardGraph
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


def get_high_frequency_edges(
    graph_db: Path,
    min_weight: int = 10,
    limit: int = 100,
    game: str | None = None,
) -> list[dict[str, Any]]:
    """Get high-frequency edges from graph database."""
    logger.info(f"Querying high-frequency edges from {graph_db}...")
    
    conn = sqlite3.connect(str(graph_db))
    conn.row_factory = sqlite3.Row
    
    query = """
        SELECT card1, card2, game, weight, metadata
        FROM edges
        WHERE weight >= ?
    """
    params = [min_weight]
    
    if game:
        query += " AND game = ?"
        params.append(game)
    
    query += " ORDER BY weight DESC LIMIT ?"
    params.append(limit)
    
    rows = conn.execute(query, params).fetchall()
    
    edges = []
    for row in rows:
        # Ensure weight is an integer (handle potential type issues)
        weight = int(row["weight"]) if row["weight"] is not None else 0
        edge = {
            "card1": row["card1"],
            "card2": row["card2"],
            "game": row["game"] or game or "magic",
            "weight": weight,
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
        }
        edges.append(edge)
    
    conn.close()
    
    logger.info(f"Found {len(edges)} high-frequency edges (weight >= {min_weight})")
    return edges


def create_annotation_candidates(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create annotation candidates from high-frequency edges."""
    candidates = []
    
    for edge in edges:
        # Skip if already annotated
        if edge["metadata"].get("similarity_score") is not None:
            continue
        
        candidate = {
            "card1": edge["card1"],
            "card2": edge["card2"],
            "game": edge["game"],
            "cooccurrence_count": edge["weight"],
            "reason": f"High co-occurrence: {edge['weight']} decks",
        }
        candidates.append(candidate)
    
    logger.info(f"Created {len(candidates)} annotation candidates")
    return candidates


def save_annotation_candidates(
    candidates: list[dict[str, Any]],
    output_file: Path,
) -> None:
    """Save annotation candidates to JSONL file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w") as f:
        for candidate in candidates:
            f.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    
    logger.info(f"Saved {len(candidates)} candidates to {output_file}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate annotation candidates for high-frequency edges"
    )
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("annotations/high_frequency_edge_candidates.jsonl"),
        help="Output file for annotation candidates",
    )
    parser.add_argument(
        "--min-weight",
        type=int,
        default=10,
        help="Minimum edge weight to consider",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of candidates to generate",
    )
    parser.add_argument(
        "--game",
        type=str,
        default=None,
        help="Filter by game (MTG, PKM, YGO, etc.)",
    )
    
    args = parser.parse_args()
    
    # Get high-frequency edges
    edges = get_high_frequency_edges(
        graph_db=args.graph_db,
        min_weight=args.min_weight,
        limit=args.limit,
        game=args.game,
    )
    
    if not edges:
        logger.warning("No high-frequency edges found")
        return 1
    
    # Create annotation candidates
    candidates = create_annotation_candidates(edges)
    
    if not candidates:
        logger.warning("No annotation candidates created (all may already be annotated)")
        return 1
    
    # Save candidates
    save_annotation_candidates(candidates, args.output)
    
    logger.info("=" * 70)
    logger.info("Annotation Candidates Generated")
    logger.info("=" * 70)
    logger.info(f"Total candidates: {len(candidates)}")
    logger.info(f"Output file: {args.output}")
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Review candidates: cat annotations/high_frequency_edge_candidates.jsonl")
    logger.info("  2. Generate LLM annotations: python -m ml.annotation.llm_annotator")
    logger.info("  3. Or manually annotate using annotation tools")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

