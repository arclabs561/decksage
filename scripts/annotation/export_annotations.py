#!/usr/bin/env python3
"""
Export annotations to various formats.

Supports export to:
- CSV (for spreadsheet analysis)
- JSON (structured format)
- Training format (substitution pairs, test sets)
- Statistics summary
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def export_to_csv(annotations: list[dict[str, Any]], output_path: Path) -> None:
    """Export annotations to CSV."""
    if not annotations:
        return
    
    fieldnames = [
        "card1",
        "card2",
        "similarity_score",
        "is_substitute",
        "source",
        "similarity_type",
        "confidence",
        "timestamp",
    ]
    
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        
        for ann in annotations:
            row = {k: ann.get(k, "") for k in fieldnames}
            writer.writerow(row)


def export_to_training_format(
    annotations: list[dict[str, Any]],
    output_dir: Path,
    min_similarity: float = 0.8,
) -> None:
    """Export to training formats (substitution pairs, test sets)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Substitution pairs
    substitution_pairs = []
    for ann in annotations:
        if ann.get("is_substitute") and ann.get("similarity_score", 0) >= min_similarity:
            card1 = ann.get("card1", "")
            card2 = ann.get("card2", "")
            if card1 and card2:
                substitution_pairs.append([card1, card2])
    
    pairs_file = output_dir / "substitution_pairs.json"
    with open(pairs_file, "w") as f:
        json.dump(substitution_pairs, f, indent=2)
    print(f"  ✓ Exported {len(substitution_pairs)} substitution pairs: {pairs_file}")
    
    # Test set format
    test_set = {"queries": {}}
    for ann in annotations:
        query = ann.get("card1", "")
        candidate = ann.get("card2", "")
        score = ann.get("similarity_score", 0)
        
        if not query or not candidate:
            continue
        
        if query not in test_set["queries"]:
            test_set["queries"][query] = {
                "highly_relevant": [],
                "relevant": [],
                "somewhat_relevant": [],
                "marginally_relevant": [],
                "irrelevant": [],
            }
        
        if score >= 0.8:
            test_set["queries"][query]["highly_relevant"].append(candidate)
        elif score >= 0.6:
            test_set["queries"][query]["relevant"].append(candidate)
        elif score >= 0.4:
            test_set["queries"][query]["somewhat_relevant"].append(candidate)
        elif score >= 0.2:
            test_set["queries"][query]["marginally_relevant"].append(candidate)
        else:
            test_set["queries"][query]["irrelevant"].append(candidate)
    
    test_set_file = output_dir / "test_set.json"
    with open(test_set_file, "w") as f:
        json.dump(test_set, f, indent=2)
    print(f"  ✓ Exported test set: {test_set_file} ({len(test_set['queries'])} queries)")


def export_statistics(annotations: list[dict[str, Any]], output_path: Path) -> None:
    """Export statistics summary."""
    sources = Counter(ann.get("source", "unknown") for ann in annotations)
    games = Counter(ann.get("game", "unknown") for ann in annotations)
    scores = [ann.get("similarity_score", 0) for ann in annotations]
    
    stats = {
        "total_annotations": len(annotations),
        "unique_pairs": len(set(
            tuple(sorted([ann.get("card1", ""), ann.get("card2", "")]))
            for ann in annotations
            if ann.get("card1") and ann.get("card2")
        )),
        "sources": dict(sources),
        "games": dict(games),
        "score_stats": {
            "min": min(scores) if scores else 0,
            "max": max(scores) if scores else 0,
            "avg": sum(scores) / len(scores) if scores else 0,
        },
        "substitute_count": sum(1 for ann in annotations if ann.get("is_substitute")),
    }
    
    with open(output_path, "w") as f:
        json.dump(stats, f, indent=2)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Export annotations to various formats")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input annotations JSONL file",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json", "training", "stats", "all"],
        default="all",
        help="Export format",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file or directory",
    )
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=0.8,
        help="Minimum similarity for substitution pairs",
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("EXPORTING ANNOTATIONS")
    print("=" * 80)
    print()
    
    # Load annotations
    annotations = []
    errors = []
    if not args.input.exists():
        print(f"✗ Error: Input file not found: {args.input}")
        return 1
    
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
    
    # Determine output paths
    if args.output:
        output_base = args.output
    else:
        output_base = args.input.parent / args.input.stem
    
    # Export based on format
    if args.format in ["csv", "all"]:
        csv_path = output_base.with_suffix(".csv")
        export_to_csv(annotations, csv_path)
        print(f"✓ Exported CSV: {csv_path}")
    
    if args.format in ["json", "all"]:
        json_path = output_base.with_suffix(".json")
        with open(json_path, "w") as f:
            json.dump(annotations, f, indent=2)
        print(f"✓ Exported JSON: {json_path}")
    
    if args.format in ["training", "all"]:
        training_dir = output_base.parent / f"{output_base.name}_training"
        export_to_training_format(annotations, training_dir, args.min_similarity)
    
    if args.format in ["stats", "all"]:
        stats_path = output_base.parent / f"{output_base.name}_stats.json"
        export_statistics(annotations, stats_path)
        print(f"✓ Exported statistics: {stats_path}")
    
    print("\n✓ Export complete")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

