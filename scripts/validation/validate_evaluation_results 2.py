#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Validate evaluation results quality.

Checks:
- Results format valid
- Coverage statistics present
- Query counts reasonable
- Performance metrics valid
- Consistency checks
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


def validate_evaluation_results(results_path: Path) -> dict[str, Any]:
    """Validate evaluation results."""
    with open(results_path) as f:
        data = json.load(f)

    issues = []
    stats = {
        "total_methods": 0,
        "methods_with_coverage": 0,
        "methods_with_full_coverage": 0,
        "methods_with_low_coverage": 0,
        "methods_evaluated_on_few_queries": 0,
    }

    if not isinstance(data, dict):
        return {
            "valid": False,
            "error": "Results format invalid: not a dict",
        }

    results = data.get("results", {})
    if not isinstance(results, dict):
        return {
            "valid": False,
            "error": "Results format invalid: 'results' not a dict",
        }

    stats["total_methods"] = len(results)

    # Check test set info
    test_set_path = data.get("test_set")
    if not test_set_path:
        issues.append("Test set path not specified")
    elif not Path(test_set_path).exists():
        issues.append(f"Test set file not found: {test_set_path}")

    # Validate each method's results
    for method_name, result in results.items():
        if not isinstance(result, dict):
            issues.append(f"Method '{method_name}': result not a dict")
            continue

        # Check required metrics
        if "p@10" not in result:
            issues.append(f"Method '{method_name}': missing p@10 metric")

        # Check query counts
        num_queries = result.get("num_queries", 0)
        num_evaluated = result.get("num_evaluated", 0)

        if num_queries == 0:
            issues.append(f"Method '{method_name}': num_queries is 0")

        if num_evaluated == 0:
            issues.append(f"Method '{method_name}': num_evaluated is 0 (no queries evaluated)")
        elif num_evaluated < num_queries * 0.5:
            issues.append(
                f"Method '{method_name}': only {num_evaluated}/{num_queries} queries evaluated "
                f"({num_evaluated / num_queries:.1%} coverage)"
            )
            stats["methods_with_low_coverage"] += 1
        elif num_evaluated == num_queries:
            stats["methods_with_full_coverage"] += 1

        if num_evaluated < 10:
            stats["methods_evaluated_on_few_queries"] += 1
            issues.append(
                f"Method '{method_name}': evaluated on only {num_evaluated} queries "
                "(results may not be statistically reliable)"
            )

        # Check vocabulary coverage
        vocab_coverage = result.get("vocab_coverage")
        if vocab_coverage:
            stats["methods_with_coverage"] += 1
            found = vocab_coverage.get("found_in_vocab", 0)
            total = vocab_coverage.get("total_queries", 0)
            if total > 0:
                coverage = found / total
                if coverage < 0.5:
                    issues.append(
                        f"Method '{method_name}': poor vocabulary coverage "
                        f"({coverage:.1%}, {found}/{total})"
                    )

        # Check metric values
        p_at_10 = result.get("p@10", 0)
        if p_at_10 < 0 or p_at_10 > 1:
            issues.append(f"Method '{method_name}': invalid p@10 value: {p_at_10}")

        mrr = result.get("mrr", 0)
        if mrr < 0 or mrr > 1:
            issues.append(f"Method '{method_name}': invalid MRR value: {mrr}")

    return {
        "valid": len(issues) == 0,
        "results_file": str(results_path),
        "stats": stats,
        "issues": issues,
        "quality_score": calculate_quality_score(stats, issues),
    }


def calculate_quality_score(stats: dict[str, Any], issues: list[str]) -> float:
    """Calculate quality score (0-1)."""
    score = 1.0

    # Penalize low coverage
    if stats["total_methods"] > 0:
        low_coverage_ratio = stats["methods_with_low_coverage"] / stats["total_methods"]
        score -= low_coverage_ratio * 0.3

    # Penalize few queries
    if stats["total_methods"] > 0:
        few_queries_ratio = stats["methods_evaluated_on_few_queries"] / stats["total_methods"]
        score -= few_queries_ratio * 0.2

    # Penalize issues
    score -= len(issues) * 0.02

    return max(0.0, min(1.0, score))


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate evaluation results")
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("experiments/evaluation_results.json"),
        help="Evaluation results JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON report",
    )

    args = parser.parse_args()

    if not args.results.exists():
        print(f"Error: Results file not found: {args.results}")
        return 1

    print(f"Validating evaluation results: {args.results}")
    print()

    result = validate_evaluation_results(args.results)

    print("Validation Report")
    print("=" * 70)
    print()

    stats = result["stats"]
    print(f"Total methods: {stats['total_methods']}")
    print(f"Methods with coverage info: {stats['methods_with_coverage']}")
    print(f"Methods with full coverage: {stats['methods_with_full_coverage']}")
    print(f"Methods with low coverage: {stats['methods_with_low_coverage']}")
    print(f"Methods evaluated on <10 queries: {stats['methods_evaluated_on_few_queries']}")
    print()

    print(f"Quality score: {result['quality_score']:.2%}")
    print()

    if result["issues"]:
        print("Issues found:")
        for issue in result["issues"][:20]:  # Limit to 20
            print(f"  ⚠ {issue}")
        if len(result["issues"]) > 20:
            print(f"  ... and {len(result['issues']) - 20} more issues")
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
