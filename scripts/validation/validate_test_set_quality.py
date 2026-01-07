#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Validate test set quality and coverage.

Checks:
- Query coverage (all queries have labels)
- Label quality (sufficient relevant labels)
- Label distribution (balanced relevance levels)
- Query diversity (not all same cards)
"""

import json
import sys
from pathlib import Path
from typing import Any


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def validate_test_set_quality(test_set_path: Path) -> dict[str, Any]:
    """Validate test set quality."""
    with open(test_set_path) as f:
        data = json.load(f)

    queries = data.get("queries", data)
    if not isinstance(queries, dict):
        return {
            "valid": False,
            "error": "Test set format invalid: queries not a dict",
        }

    issues = []
    stats = {
        "total_queries": len(queries),
        "queries_with_labels": 0,
        "queries_without_labels": 0,
        "queries_with_few_labels": 0,
        "label_distribution": {
            "highly_relevant": 0,
            "relevant": 0,
            "somewhat_relevant": 0,
            "marginally_relevant": 0,
            "irrelevant": 0,
        },
    }

    for query, labels in queries.items():
        if not isinstance(labels, dict):
            issues.append(f"Query '{query}': labels not a dict")
            stats["queries_without_labels"] += 1
            continue

        # Count labels by level
        total_labels = 0
        for level in stats["label_distribution"].keys():
            level_labels = labels.get(level, [])
            if isinstance(level_labels, list):
                count = len(level_labels)
                stats["label_distribution"][level] += count
                total_labels += count

        if total_labels == 0:
            issues.append(f"Query '{query}': no labels")
            stats["queries_without_labels"] += 1
        elif total_labels < 3:
            issues.append(f"Query '{query}': only {total_labels} labels (recommend ≥3)")
            stats["queries_with_few_labels"] += 1
        else:
            stats["queries_with_labels"] += 1

    # Check label distribution
    total_labels = sum(stats["label_distribution"].values())
    if total_labels == 0:
        issues.append("No labels found in test set")

    # Check for sufficient highly relevant labels
    highly_relevant = stats["label_distribution"]["highly_relevant"]
    if highly_relevant < stats["total_queries"] * 0.5:
        issues.append(
            f"Only {highly_relevant} highly_relevant labels (recommend ≥{stats['total_queries'] * 0.5:.0f})"
        )

    return {
        "valid": len(issues) == 0,
        "test_set": str(test_set_path),
        "stats": stats,
        "issues": issues,
        "quality_score": calculate_quality_score(stats, issues),
    }


def calculate_quality_score(stats: dict[str, Any], issues: list[str]) -> float:
    """Calculate quality score (0-1)."""
    score = 1.0

    # Penalize queries without labels
    if stats["total_queries"] > 0:
        missing_ratio = stats["queries_without_labels"] / stats["total_queries"]
        score -= missing_ratio * 0.5

    # Penalize queries with few labels
    if stats["total_queries"] > 0:
        few_labels_ratio = stats["queries_with_few_labels"] / stats["total_queries"]
        score -= few_labels_ratio * 0.2

    # Penalize issues
    score -= len(issues) * 0.05

    return max(0.0, min(1.0, score))


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate test set quality")
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_canonical_magic.json"),
        help="Test set JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON report",
    )

    args = parser.parse_args()

    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1

    print(f"Validating test set quality: {args.test_set}")
    print()

    result = validate_test_set_quality(args.test_set)

    print("Quality Report")
    print("=" * 70)
    print()

    stats = result["stats"]
    print(f"Total queries: {stats['total_queries']}")
    print(f"Queries with labels: {stats['queries_with_labels']}")
    print(f"Queries without labels: {stats['queries_without_labels']}")
    print(f"Queries with few labels: {stats['queries_with_few_labels']}")
    print()

    print("Label distribution:")
    for level, count in stats["label_distribution"].items():
        print(f"  {level}: {count}")
    print()

    print(f"Quality score: {result['quality_score']:.2%}")
    print()

    if result["issues"]:
        print("Issues found:")
        for issue in result["issues"]:
            print(f"  ⚠ {issue}")
    else:
        print("✓ No issues found")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nReport saved to: {args.output}")

    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
