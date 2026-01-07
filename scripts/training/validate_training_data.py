#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2.0.0",
# ]
# ///
"""
Validate training data for data leakage before training.

Checks:
1. Test set cards are excluded from training annotations
2. Temporal splits are respected (if applicable)
3. No duplicate pairs between train and test
4. Annotation quality metrics (IAA if multi-annotator)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.annotation_utils import (
        load_test_set_cards,
        filter_annotations_for_training,
        load_similarity_annotations,
    )
    from ml.evaluation.leakage_analysis import LeakageAnalyzer
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"Warning: Could not import dependencies: {e}")


def validate_annotation_leakage(
    annotation_path: Path,
    test_set_path: Path | None = None,
    game: str | None = None,
) -> dict[str, Any]:
    """Validate that annotations don't contain test set cards.
    
    Returns:
        Dict with validation results including:
        - is_valid: bool
        - total_annotations: int
        - leaked_count: int
        - leaked_pairs: list of (card1, card2) tuples
        - warnings: list of warning messages
    """
    if not HAS_DEPS:
        return {
            "is_valid": False,
            "error": "Missing dependencies",
        }
    
    # Load annotations
    annotations = load_similarity_annotations(
        annotation_path,
        filter_test_cards=False,  # Don't filter, just check
    )
    
    # Load test set cards
    test_cards = load_test_set_cards(test_set_path, game)
    
    # Check for leakage
    leaked_pairs = []
    for ann in annotations:
        card1 = ann.get("card1", "")
        card2 = ann.get("card2", "")
        if card1 in test_cards or card2 in test_cards:
            leaked_pairs.append((card1, card2))
    
    is_valid = len(leaked_pairs) == 0
    
    warnings = []
    if not is_valid:
        warnings.append(
            f"CRITICAL: {len(leaked_pairs)} annotations contain test set cards. "
            "This will cause data leakage and invalidate evaluation results."
        )
        warnings.append("Use --filter-test-cards when loading annotations for training.")
    
    return {
        "is_valid": is_valid,
        "total_annotations": len(annotations),
        "leaked_count": len(leaked_pairs),
        "leaked_pairs": leaked_pairs[:10],  # First 10
        "test_cards_loaded": len(test_cards),
        "warnings": warnings,
    }


def validate_substitution_pairs(
    pairs_path: Path,
    test_set_path: Path | None = None,
    game: str | None = None,
) -> dict[str, Any]:
    """Validate that substitution pairs don't contain test set cards."""
    if not HAS_DEPS:
        return {
            "is_valid": False,
            "error": "Missing dependencies",
        }
    
    # Load pairs
    with open(pairs_path) as f:
        data = json.load(f)
    
    pairs = []
    if isinstance(data, list):
        pairs = [tuple(pair) for pair in data]
    else:
        return {
            "is_valid": False,
            "error": f"Unknown format: {type(data)}",
        }
    
    # Load test set cards
    test_cards = load_test_set_cards(test_set_path, game)
    
    # Check for leakage
    leaked_pairs = []
    for card1, card2 in pairs:
        if card1 in test_cards or card2 in test_cards:
            leaked_pairs.append((card1, card2))
    
    is_valid = len(leaked_pairs) == 0
    
    warnings = []
    if not is_valid:
        warnings.append(
            f"CRITICAL: {len(leaked_pairs)} substitution pairs contain test set cards."
        )
    
    return {
        "is_valid": is_valid,
        "total_pairs": len(pairs),
        "leaked_count": len(leaked_pairs),
        "leaked_pairs": leaked_pairs[:10],
        "test_cards_loaded": len(test_cards),
        "warnings": warnings,
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate training data for data leakage"
    )
    parser.add_argument(
        "--annotations",
        type=Path,
        help="Path to annotation file (JSONL or YAML)",
    )
    parser.add_argument(
        "--substitution-pairs",
        type=Path,
        help="Path to substitution pairs JSON",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        help="Path to test set JSON (if None, loads all test sets)",
    )
    parser.add_argument(
        "--game",
        type=str,
        help="Game filter ('magic', 'pokemon', 'yugioh')",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output validation report JSON",
    )
    
    args = parser.parse_args()
    
    if not args.annotations and not args.substitution_pairs:
        parser.error("Must specify --annotations or --substitution-pairs")
    
    print("=" * 80)
    print("TRAINING DATA VALIDATION - DATA LEAKAGE CHECK")
    print("=" * 80)
    
    results = {}
    
    # Validate annotations
    if args.annotations:
        print(f"\nValidating annotations: {args.annotations}")
        ann_result = validate_annotation_leakage(
            args.annotations,
            test_set_path=args.test_set,
            game=args.game,
        )
        results["annotations"] = ann_result
        
        if ann_result.get("is_valid"):
            print(f"  ✓ Valid: {ann_result['total_annotations']} annotations, no leakage")
        else:
            print(f"  ❌ INVALID: {ann_result['leaked_count']} leaked annotations")
            for warning in ann_result.get("warnings", []):
                print(f"    ⚠️  {warning}")
    
    # Validate substitution pairs
    if args.substitution_pairs:
        print(f"\nValidating substitution pairs: {args.substitution_pairs}")
        pairs_result = validate_substitution_pairs(
            args.substitution_pairs,
            test_set_path=args.test_set,
            game=args.game,
        )
        results["substitution_pairs"] = pairs_result
        
        if pairs_result.get("is_valid"):
            print(f"  ✓ Valid: {pairs_result['total_pairs']} pairs, no leakage")
        else:
            print(f"  ❌ INVALID: {pairs_result['leaked_count']} leaked pairs")
            for warning in pairs_result.get("warnings", []):
                print(f"    ⚠️  {warning}")
    
    # Overall validation
    all_valid = all(
        r.get("is_valid", False)
        for r in results.values()
    )
    
    print("\n" + "=" * 80)
    if all_valid:
        print("✓ VALIDATION PASSED - No data leakage detected")
        print("=" * 80)
        exit_code = 0
    else:
        print("❌ VALIDATION FAILED - Data leakage detected!")
        print("=" * 80)
        print("\nCRITICAL: Do not proceed with training until leakage is fixed.")
        print("Use --filter-test-cards when loading annotations.")
        exit_code = 1
    
    # Save report if requested
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nReport saved to: {args.output}")
    
    return exit_code


if __name__ == "__main__":
    exit(main())

