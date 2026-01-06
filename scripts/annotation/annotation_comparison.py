#!/usr/bin/env python3
"""
Compare annotation sets.

Compare two annotation files to identify differences, additions, and changes.
Useful for tracking annotation evolution and validating updates.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.annotation_utils import normalize_card_name
    HAS_UTILS = True
except ImportError:
    HAS_UTILS = False
    def normalize_card_name(name: str) -> str:
        return name.strip().lower() if name else ""


def load_annotations(file_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Load annotations and index by card pair."""
    annotations = {}
    
    if not file_path.exists():
        raise FileNotFoundError(f"Annotation file not found: {file_path}")
    
    errors = []
    with open(file_path) as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    ann = json.loads(line)
                    card1 = normalize_card_name(ann.get("card1", ""))
                    card2 = normalize_card_name(ann.get("card2", ""))
                    
                    if card1 and card2:
                        pair = tuple(sorted([card1, card2]))
                        annotations[pair] = ann
                    else:
                        errors.append(f"Line {line_num}: Missing card names")
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {e}")
                    continue
                except Exception as e:
                    errors.append(f"Line {line_num}: Error - {e}")
                    continue
    
    if errors:
        print(f"⚠ {len(errors)} errors encountered while loading {file_path.name}:")
        for error in errors[:5]:
            print(f"  {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more errors")
        print()
    
    return annotations


def compare_annotations(
    old_annotations: dict[tuple[str, str], dict[str, Any]],
    new_annotations: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    """Compare two annotation sets."""
    old_pairs = set(old_annotations.keys())
    new_pairs = set(new_annotations.keys())
    
    added = new_pairs - old_pairs
    removed = old_pairs - new_pairs
    common = old_pairs & new_pairs
    
    # Check for changes in common pairs
    changed = []
    unchanged = []
    
    for pair in common:
        old_ann = old_annotations[pair]
        new_ann = new_annotations[pair]
        
        old_score = old_ann.get("similarity_score", 0)
        new_score = new_ann.get("similarity_score", 0)
        old_sub = old_ann.get("is_substitute", False)
        new_sub = new_ann.get("is_substitute", False)
        
        if abs(old_score - new_score) > 0.01 or old_sub != new_sub:
            changed.append({
                "pair": pair,
                "old": {"score": old_score, "is_substitute": old_sub},
                "new": {"score": new_score, "is_substitute": new_sub},
            })
        else:
            unchanged.append(pair)
    
    return {
        "total_old": len(old_annotations),
        "total_new": len(new_annotations),
        "added": len(added),
        "removed": len(removed),
        "common": len(common),
        "changed": len(changed),
        "unchanged": len(unchanged),
        "added_pairs": list(added)[:20],  # Sample
        "removed_pairs": list(removed)[:20],  # Sample
        "changed_pairs": changed[:20],  # Sample
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Compare annotation sets")
    parser.add_argument(
        "--old",
        type=Path,
        required=True,
        help="Old annotation file",
    )
    parser.add_argument(
        "--new",
        type=Path,
        required=True,
        help="New annotation file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output comparison report JSON",
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("ANNOTATION COMPARISON")
    print("=" * 80)
    print()
    
    # Load annotations
    try:
        print(f"Loading old annotations: {args.old}")
        old_anns = load_annotations(args.old)
        print(f"  Loaded {len(old_anns)} annotations")
    except FileNotFoundError as e:
        print(f"✗ Error: {e}")
        return 1
    except Exception as e:
        print(f"✗ Error loading old annotations: {e}")
        return 1
    
    try:
        print(f"\nLoading new annotations: {args.new}")
        new_anns = load_annotations(args.new)
        print(f"  Loaded {len(new_anns)} annotations")
    except FileNotFoundError as e:
        print(f"✗ Error: {e}")
        return 1
    except Exception as e:
        print(f"✗ Error loading new annotations: {e}")
        return 1
    
    # Compare
    print("\nComparing annotations...")
    comparison = compare_annotations(old_anns, new_anns)
    
    print(f"\nComparison Results:")
    print(f"  Old total: {comparison['total_old']}")
    print(f"  New total: {comparison['total_new']}")
    print(f"  Added: {comparison['added']}")
    print(f"  Removed: {comparison['removed']}")
    print(f"  Changed: {comparison['changed']}")
    print(f"  Unchanged: {comparison['unchanged']}")
    
    if comparison['added'] > 0:
        print(f"\n  Sample added pairs:")
        for pair in comparison['added_pairs'][:5]:
            print(f"    {pair[0]} <-> {pair[1]}")
    
    if comparison['changed'] > 0:
        print(f"\n  Sample changed pairs:")
        for change in comparison['changed_pairs'][:5]:
            pair = change['pair']
            old = change['old']
            new = change['new']
            print(f"    {pair[0]} <-> {pair[1]}:")
            print(f"      Score: {old['score']:.3f} → {new['score']:.3f}")
            print(f"      Substitute: {old['is_substitute']} → {new['is_substitute']}")
    
    # Save report
    if args.output:
        with open(args.output, "w") as f:
            json.dump(comparison, f, indent=2)
        print(f"\n✓ Saved comparison report: {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

