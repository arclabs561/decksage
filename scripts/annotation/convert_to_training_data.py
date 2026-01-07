#!/usr/bin/env python3
"""
Convert integrated annotations to training data formats.

Converts:
1. Integrated annotations → Substitution pairs (for training)
2. Integrated annotations → Test set (for evaluation)

This is a standalone script that doesn't require pandas or other heavy dependencies.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def convert_relevance_to_similarity_score(relevance: int, scale: str = "0-4") -> float:
    """Convert relevance score (0-4) to similarity score (0-1)."""
    mapping = {4: 0.95, 3: 0.75, 2: 0.55, 1: 0.35, 0: 0.1}
    return mapping.get(relevance, 0.0)


def extract_substitution_pairs(
    annotations: list[dict[str, Any]],
    min_similarity: float = 0.8,
    require_substitute_flag: bool = True,
) -> list[tuple[str, str]]:
    """Extract substitution pairs from annotations."""
    pairs = []
    
    for ann in annotations:
        card1 = ann.get("card1")
        card2 = ann.get("card2")
        
        if not card1 or not card2:
            continue
        
        # Get similarity score
        similarity_score = ann.get("similarity_score")
        if similarity_score is None:
            # Try to convert from relevance
            relevance = ann.get("relevance")
            if relevance is not None:
                similarity_score = convert_relevance_to_similarity_score(int(relevance))
            else:
                continue
        
        # Check threshold
        if similarity_score < min_similarity:
            continue
        
        # Check substitute flag
        if require_substitute_flag:
            is_substitute = ann.get("is_substitute", False)
            if not is_substitute:
                continue
        
        pairs.append((card1, card2))
    
    return pairs


def convert_to_test_set(
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert annotations to test set format."""
    test_set = {
        "version": "1.0",
        "queries": {},
    }
    
    # Group by query card
    queries: dict[str, dict[str, list[str]]] = {}
    
    for ann in annotations:
        card1 = ann.get("card1")
        card2 = ann.get("card2")
        
        if not card1 or not card2:
            continue
        
        # Get similarity score or convert from relevance
        similarity_score = ann.get("similarity_score")
        if similarity_score is None:
            relevance = ann.get("relevance")
            if relevance is not None:
                similarity_score = convert_relevance_to_similarity_score(int(relevance))
            else:
                continue
        
        # Initialize query if needed
        if card1 not in queries:
            queries[card1] = {
                "highly_relevant": [],
                "relevant": [],
                "somewhat_relevant": [],
                "marginally_relevant": [],
                "irrelevant": [],
            }
        
        # Categorize by similarity score
        if similarity_score >= 0.8:
            queries[card1]["highly_relevant"].append(card2)
        elif similarity_score >= 0.6:
            queries[card1]["relevant"].append(card2)
        elif similarity_score >= 0.4:
            queries[card1]["somewhat_relevant"].append(card2)
        elif similarity_score >= 0.2:
            queries[card1]["marginally_relevant"].append(card2)
        else:
            queries[card1]["irrelevant"].append(card2)
    
    test_set["queries"] = queries
    return test_set


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Convert integrated annotations to training data formats"
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input integrated annotations JSONL file",
    )
    parser.add_argument(
        "--output-substitution-pairs",
        type=Path,
        help="Output path for substitution pairs JSON",
    )
    parser.add_argument(
        "--output-test-set",
        type=Path,
        help="Output path for test set JSON",
    )
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=0.8,
        help="Minimum similarity score for substitution pairs (default: 0.8)",
    )
    parser.add_argument(
        "--require-substitute-flag",
        action="store_true",
        default=True,
        help="Require is_substitute=True for substitution pairs (default: True)",
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}")
        return 1
    
    if not args.output_substitution_pairs and not args.output_test_set:
        parser.error("Must specify at least one of --output-substitution-pairs or --output-test-set")
    
    # Load annotations
    print(f"Loading annotations from {args.input}...")
    annotations = []
    errors = []
    with open(args.input) as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    ann = json.loads(line)
                    # Basic validation
                    if ann.get("card1") and ann.get("card2"):
                        annotations.append(ann)
                    else:
                        errors.append(f"Line {line_num}: Missing card1 or card2")
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {e}")
                    continue
                except Exception as e:
                    errors.append(f"Line {line_num}: Error - {e}")
                    continue
    
    if errors:
        print(f"⚠ {len(errors)} errors encountered while loading:")
        for error in errors[:5]:
            print(f"  {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more errors")
        print()
    
    print(f"Loaded {len(annotations)} annotations")
    
    # Convert to substitution pairs
    if args.output_substitution_pairs:
        print(f"\nExtracting substitution pairs (min_similarity={args.min_similarity})...")
        pairs = extract_substitution_pairs(
            annotations,
            min_similarity=args.min_similarity,
            require_substitute_flag=args.require_substitute_flag,
        )
        
        print(f"Extracted {len(pairs)} substitution pairs")
        
        # Save
        args.output_substitution_pairs.parent.mkdir(parents=True, exist_ok=True)
        pairs_list = [[c1, c2] for c1, c2 in pairs]
        
        temp_path = args.output_substitution_pairs.with_suffix(
            args.output_substitution_pairs.suffix + ".tmp"
        )
        try:
            with open(temp_path, "w") as f:
                json.dump(pairs_list, f, indent=2)
            temp_path.replace(args.output_substitution_pairs)
            print(f"✓ Saved substitution pairs to {args.output_substitution_pairs}")
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    # Convert to test set
    if args.output_test_set:
        print(f"\nConverting to test set format...")
        test_set = convert_to_test_set(annotations)
        
        queries = test_set["queries"]
        total_relevant = sum(
            len(v.get("highly_relevant", [])) + len(v.get("relevant", []))
            for v in queries.values()
        )
        
        print(f"Created test set with {len(queries)} queries, {total_relevant} relevant cards")
        
        # Save
        args.output_test_set.parent.mkdir(parents=True, exist_ok=True)
        temp_path = args.output_test_set.with_suffix(
            args.output_test_set.suffix + ".tmp"
        )
        try:
            with open(temp_path, "w") as f:
                json.dump(test_set, f, indent=2)
            temp_path.replace(args.output_test_set)
            print(f"✓ Saved test set to {args.output_test_set}")
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

