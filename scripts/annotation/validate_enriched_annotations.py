#!/usr/bin/env python3
"""Validate enriched annotations against graph data.

Checks consistency between LLM judgments and graph evidence.
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.enriched_annotation_utils import (
    get_enrichment_summary,
    validate_annotation_against_graph,
)
from ml.utils.annotation_utils import load_similarity_annotations


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate enriched annotations against graph data"
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
        help="Output validation report (JSON)",
    )

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1

    print(f"Loading annotations from: {args.input}")
    annotations = load_similarity_annotations(args.input)

    print(f"Loaded {len(annotations)} annotations")
    print()

    # Get enrichment summary
    summary = get_enrichment_summary(annotations)
    print("Enrichment Summary:")
    print(f"  Total annotations: {summary['total']}")
    print(f"  With graph features: {summary['with_graph_features']} ({summary['enrichment_rate']['graph']:.1%})")
    print(f"  With card attributes: {summary['with_card_attributes']} ({summary['enrichment_rate']['attributes']:.1%})")
    print(f"  With contextual analysis: {summary['with_contextual_analysis']} ({summary['enrichment_rate']['context']:.1%})")
    
    if "jaccard_stats" in summary:
        print(f"\nJaccard Statistics:")
        print(f"  Mean: {summary['jaccard_stats']['mean']:.3f}")
        print(f"  Range: {summary['jaccard_stats']['min']:.3f} - {summary['jaccard_stats']['max']:.3f}")
    
    if "cooccurrence_stats" in summary:
        print(f"\nCo-occurrence Statistics:")
        print(f"  Mean: {summary['cooccurrence_stats']['mean']:.1f}")
        print(f"  Range: {summary['cooccurrence_stats']['min']} - {summary['cooccurrence_stats']['max']}")
    
    print()

    # Validate each annotation
    print("Validating annotations...")
    valid_count = 0
    invalid_count = 0
    warnings_count = 0
    
    validation_results = []
    
    for i, ann in enumerate(annotations, 1):
        if i % 100 == 0:
            print(f"  Validated {i}/{len(annotations)}...")
        
        validation = validate_annotation_against_graph(ann)
        validation_results.append({
            "annotation": {
                "card1": ann.get("card1"),
                "card2": ann.get("card2"),
                "similarity_score": ann.get("similarity_score"),
            },
            "validation": validation,
        })
        
        if validation["is_valid"]:
            valid_count += 1
        else:
            invalid_count += 1
        
        warnings_count += len(validation.get("warnings", []))

    print(f"\nValidation Results:")
    print(f"  Valid: {valid_count}")
    print(f"  Invalid: {invalid_count}")
    print(f"  Total warnings: {warnings_count}")

    # Save report if requested
    if args.output:
        report = {
            "summary": summary,
            "validation_results": validation_results,
            "stats": {
                "valid": valid_count,
                "invalid": invalid_count,
                "warnings": warnings_count,
            },
        }
        
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp_file = args.output.with_suffix(args.output.suffix + ".tmp")
        
        with open(temp_file, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        temp_file.replace(args.output)
        print(f"\nReport saved to: {args.output}")

    return 0 if invalid_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


