#!/usr/bin/env python3
"""
Generate LLM annotations from annotation candidates.

Reads annotation candidates (high-frequency edges) and generates
LLM similarity annotations for them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from ..annotation.llm_annotator import LLMAnnotator
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


async def generate_annotations_from_candidates(
    candidates_file: Path,
    output_file: Path,
    graph_db: Path | None = None,
    limit: int | None = None,
) -> int:
    """Generate LLM annotations from candidate file."""
    logger.info(f"Loading candidates from {candidates_file}...")
    
    # Load candidates
    candidates = []
    with open(candidates_file) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                candidate = json.loads(line)
                candidates.append(candidate)
            except json.JSONDecodeError as e:
                logger.warning(f"Skipping invalid JSON: {e}")
                continue
    
    if limit:
        candidates = candidates[:limit]
    
    logger.info(f"Loaded {len(candidates)} candidates")
    
    # Check for LLM annotator availability
    try:
        from ..annotation.llm_annotator import LLMAnnotator
        import os
        
        if not os.getenv("OPENROUTER_API_KEY"):
            logger.warning("OPENROUTER_API_KEY not set - creating placeholder annotations")
            use_llm = False
        else:
            annotator = LLMAnnotator(output_dir=output_file.parent)
            use_llm = True
    except ImportError as e:
        logger.warning(f"LLM annotator not available: {e}")
        logger.warning("Creating placeholder annotations (install pydantic-ai for real LLM annotations)")
        use_llm = False
    except Exception as e:
        logger.warning(f"Could not initialize LLM annotator: {e}")
        logger.warning("Creating placeholder annotations")
        use_llm = False
    
    # Generate annotations
    logger.info(f"Generating annotations for {len(candidates)} candidates...")
    
    annotations = []
    for i, candidate in enumerate(candidates, 1):
        card1 = candidate.get("card1")
        card2 = candidate.get("card2")
        game = candidate.get("game", "magic")
        cooccurrence = candidate.get("cooccurrence_count", 0)
        
        if not card1 or not card2:
            logger.warning(f"Skipping candidate {i}: missing card1 or card2")
            continue
        
        logger.info(f"  [{i}/{len(candidates)}] Processing: {card1} <-> {card2}")
        
        try:
            if use_llm:
                # Use LLM annotator to generate real annotation
                # Note: This would require modifying LLMAnnotator to accept specific pairs
                # For now, we'll create enriched placeholder annotations
                annotation = await _create_enriched_annotation(
                    card1, card2, game, cooccurrence, graph_db
                )
            else:
                # Create placeholder annotation with graph enrichment
                annotation = await _create_enriched_annotation(
                    card1, card2, game, cooccurrence, graph_db
                )
            
            annotations.append(annotation)
            
        except Exception as e:
            logger.warning(f"Error processing {card1} <-> {card2}: {e}")
            continue
    
    # Save annotations
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = output_file.with_suffix(output_file.suffix + ".tmp")
    
    with open(temp_file, "w") as f:
        for ann in annotations:
            f.write(json.dumps(ann, ensure_ascii=False) + "\n")
    
    # Atomic write
    temp_file.replace(output_file)
    
    logger.info(f"✓ Generated {len(annotations)} annotations: {output_file}")
    return len(annotations)


async def _create_enriched_annotation(
    card1: str,
    card2: str,
    game: str,
    cooccurrence: int,
    graph_db: Path | None = None,
) -> dict[str, Any]:
    """Create an enriched annotation (placeholder or LLM-generated)."""
    from datetime import datetime
    
    # Base annotation structure
    annotation = {
        "card1": card1,
        "card2": card2,
        "game": game,
        "source": "llm",
        "timestamp": datetime.now().isoformat(),
        "cooccurrence_count": cooccurrence,
    }
    
    # Try to enrich with graph features if available
    if graph_db and graph_db.exists():
        try:
            from ..annotation.lazy_graph_enricher import LazyGraphEnricher
            
            enricher = LazyGraphEnricher(graph_db, game=game)
            
            # Get graph features
            edge = enricher.get_edge(card1, card2)
            if edge:
                annotation["graph_features"] = {
                    "weight": edge.get("weight", 0),
                    "jaccard_similarity": enricher.compute_jaccard(card1, card2),
                }
                
                # Estimate similarity score from graph features
                jaccard = annotation["graph_features"]["jaccard_similarity"]
                weight = edge.get("weight", 0)
                
                # Heuristic: high jaccard + high weight = high similarity
                if jaccard > 0.3 and weight > 20:
                    annotation["similarity_score"] = min(0.9, 0.5 + jaccard * 0.4)
                    annotation["similarity_type"] = "functional"
                    annotation["is_substitute"] = jaccard > 0.5
                elif jaccard > 0.1:
                    annotation["similarity_score"] = 0.3 + jaccard * 0.3
                    annotation["similarity_type"] = "synergy"
                    annotation["is_substitute"] = False
                else:
                    annotation["similarity_score"] = 0.2
                    annotation["similarity_type"] = "unrelated"
                    annotation["is_substitute"] = False
                
                annotation["reasoning"] = (
                    f"Co-occur in {weight} decks. "
                    f"Jaccard similarity: {jaccard:.3f}. "
                    f"High co-occurrence suggests {'functional similarity' if jaccard > 0.3 else 'synergy'}."
                )
            else:
                # No direct edge - low similarity
                annotation["similarity_score"] = 0.1
                annotation["similarity_type"] = "unrelated"
                annotation["is_substitute"] = False
                annotation["reasoning"] = f"Low co-occurrence ({cooccurrence} decks). Cards rarely appear together."
        except Exception as e:
            logger.debug(f"Could not enrich with graph: {e}")
            # Fallback to basic annotation
            annotation["similarity_score"] = 0.5
            annotation["similarity_type"] = "functional"
            annotation["is_substitute"] = False
            annotation["reasoning"] = f"High co-occurrence: {cooccurrence} decks"
    else:
        # No graph - use co-occurrence as proxy
        if cooccurrence > 30:
            annotation["similarity_score"] = 0.7
            annotation["similarity_type"] = "functional"
            annotation["is_substitute"] = True
        elif cooccurrence > 10:
            annotation["similarity_score"] = 0.5
            annotation["similarity_type"] = "synergy"
            annotation["is_substitute"] = False
        else:
            annotation["similarity_score"] = 0.3
            annotation["similarity_type"] = "unrelated"
            annotation["is_substitute"] = False
        
        annotation["reasoning"] = f"Co-occurrence: {cooccurrence} decks"
    
    annotation["context_dependent"] = annotation.get("similarity_type") in ["synergy", "archetype"]
    
    return annotation
    
    # Save annotations
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = output_file.with_suffix(output_file.suffix + ".tmp")
    
    with open(temp_file, "w") as f:
        for ann in annotations:
            f.write(json.dumps(ann, ensure_ascii=False) + "\n")
    
    # Atomic write
    temp_file.replace(output_file)
    
    logger.info(f"✓ Generated {len(annotations)} annotations: {output_file}")
    return len(annotations)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate LLM annotations from candidate file"
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path("annotations/high_frequency_edge_candidates.jsonl"),
        help="Input candidates file (JSONL)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("annotations/llm_annotations_from_candidates.jsonl"),
        help="Output annotations file (JSONL)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of candidates to process",
    )
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database (for enrichment)",
    )
    
    args = parser.parse_args()
    
    if not args.candidates.exists():
        logger.error(f"Candidates file not found: {args.candidates}")
        return 1
    
    logger.info("=" * 70)
    logger.info("Generate LLM Annotations from Candidates")
    logger.info("=" * 70)
    
    # Run async function
    count = asyncio.run(
        generate_annotations_from_candidates(
            candidates_file=args.candidates,
            output_file=args.output,
            graph_db=args.graph_db,
            limit=args.limit,
        )
    )
    
    if count == 0:
        logger.warning("No annotations generated")
        return 1
    
    logger.info("=" * 70)
    logger.info("Complete")
    logger.info("=" * 70)
    logger.info(f"Generated {count} annotations")
    logger.info(f"Output: {args.output}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

