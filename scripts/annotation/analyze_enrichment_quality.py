#!/usr/bin/env python3
"""Analyze quality of annotation enrichment.

Compares LLM judgments with graph evidence to identify:
- High-confidence annotations (LLM + graph agree)
- Low-confidence annotations (LLM + graph disagree)
- Missing enrichment opportunities
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.enriched_annotation_utils import (
    get_enrichment_summary,
    get_jaccard_similarity,
    validate_annotation_against_graph,
)
from ml.utils.annotation_utils import load_similarity_annotations


def analyze_enrichment_quality(annotations: list[dict]) -> dict:
    """Analyze quality of annotation enrichment."""
    analysis = {
        "total": len(annotations),
        "enrichment_coverage": {},
        "consistency_analysis": {
            "high_confidence": [],
            "low_confidence": [],
            "disagreements": [],
        },
        "missing_enrichment": [],
    }

    enriched_count = 0
    high_confidence = 0
    low_confidence = 0
    disagreements = 0

    for ann in annotations:
        # Check enrichment
        has_graph = bool(ann.get("graph_features"))
        has_attributes = bool(ann.get("card_comparison"))
        has_context = bool(ann.get("contextual_analysis"))
        
        if has_graph or has_attributes or has_context:
            enriched_count += 1

        # Validate against graph
        validation = validate_annotation_against_graph(ann)
        
        similarity_score = ann.get("similarity_score", 0.0)
        graph_features = ann.get("graph_features", {})
        jaccard = graph_features.get("jaccard_similarity", 0.0) if graph_features else 0.0

        # High confidence: LLM and graph agree (within 0.2)
        if has_graph and abs(similarity_score - jaccard) < 0.2:
            high_confidence += 1
            analysis["consistency_analysis"]["high_confidence"].append({
                "card1": ann.get("card1"),
                "card2": ann.get("card2"),
                "llm_score": similarity_score,
                "jaccard": jaccard,
                "difference": abs(similarity_score - jaccard),
            })

        # Low confidence: LLM and graph disagree (difference > 0.3)
        elif has_graph and abs(similarity_score - jaccard) > 0.3:
            low_confidence += 1
            disagreements += 1
            analysis["consistency_analysis"]["low_confidence"].append({
                "card1": ann.get("card1"),
                "card2": ann.get("card2"),
                "llm_score": similarity_score,
                "jaccard": jaccard,
                "difference": abs(similarity_score - jaccard),
            })

        # Missing enrichment: No graph features but should have them
        elif not has_graph:
            analysis["missing_enrichment"].append({
                "card1": ann.get("card1"),
                "card2": ann.get("card2"),
                "similarity_score": similarity_score,
            })

    analysis["enrichment_coverage"] = {
        "total_enriched": enriched_count,
        "enrichment_rate": enriched_count / len(annotations) if annotations else 0.0,
    }

    analysis["consistency_analysis"]["stats"] = {
        "high_confidence": high_confidence,
        "low_confidence": low_confidence,
        "disagreements": disagreements,
        "agreement_rate": high_confidence / enriched_count if enriched_count > 0 else 0.0,
    }

    return analysis


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze quality of annotation enrichment"
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input annotation file (JSONL)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output analysis report (JSON)",
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1

    print(f"Loading annotations from: {args.input}")
    annotations = load_similarity_annotations(args.input)

    print(f"Loaded {len(annotations)} annotations")
    print()

    # Analyze enrichment quality
    analysis = analyze_enrichment_quality(annotations)

    print("Enrichment Quality Analysis:")
    print(f"  Total annotations: {analysis['total']}")
    print(f"  Enriched: {analysis['enrichment_coverage']['total_enriched']} ({analysis['enrichment_coverage']['enrichment_rate']:.1%})")
    print()
    print("Consistency Analysis:")
    stats = analysis["consistency_analysis"]["stats"]
    print(f"  High confidence (LLM + graph agree): {stats['high_confidence']}")
    print(f"  Low confidence (LLM + graph disagree): {stats['low_confidence']}")
    print(f"  Agreement rate: {stats['agreement_rate']:.1%}")
    print()
    print(f"Missing enrichment: {len(analysis['missing_enrichment'])} annotations")
    
    if analysis["missing_enrichment"]:
        print("\nTop 10 annotations missing enrichment:")
        for ann in analysis["missing_enrichment"][:10]:
            print(f"  {ann['card1']} ↔ {ann['card2']} (score: {ann['similarity_score']:.2f})")

    # Save report if requested
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp_file = args.output.with_suffix(args.output.suffix + ".tmp")
        
        with open(temp_file, "w") as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
        
        temp_file.replace(args.output)
        print(f"\nAnalysis report saved to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())


