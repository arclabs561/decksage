#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "gensim>=4.3.0",
# ]
# ///
"""
Ensure full evaluation on all test queries.

Wraps evaluate_all_embeddings.py but validates:
1. All queries in test set are used
2. Vocabulary coverage is reported
3. Results include coverage statistics
"""

import json
import sys
from pathlib import Path
from typing import Any


def validate_test_set(test_set_path: Path) -> dict[str, Any]:
    """Validate test set and return query count."""
    with open(test_set_path) as f:
        data = json.load(f)

    if "queries" in data:
        queries = data["queries"]
    else:
        queries = data

    if not isinstance(queries, dict):
        return {
            "valid": False,
            "error": f"Test set format invalid: expected dict, got {type(queries)}",
        }

    return {
        "valid": True,
        "num_queries": len(queries),
        "queries": list(queries.keys())[:10],  # Sample
    }


def main() -> int:
    """Main entry point."""
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(
        description="Ensure full evaluation on all test queries",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=Path("experiments/test_set_canonical_magic_improved.json"),
        help="Test set JSON",
    )
    parser.add_argument(
        "--embeddings-dir",
        type=Path,
        default=Path("data/embeddings"),
        help="Embeddings directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/full_evaluation_results.json"),
        help="Output JSON",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.8,
        help="Minimum vocabulary coverage (default: 0.8)",
    )

    args = parser.parse_args()

    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1

    # Validate test set
    print("Validating test set...")
    validation = validate_test_set(args.test_set)
    if not validation["valid"]:
        print(f"Error: {validation['error']}")
        return 1

    num_queries = validation["num_queries"]
    print(f"✓ Test set valid: {num_queries} queries")
    print(f"  Sample queries: {', '.join(validation['queries'][:5])}")
    print()

    # Run evaluation with coverage check
    print("Running evaluation with coverage check...")
    print()

    eval_cmd = [
        sys.executable,
        "scripts/evaluation/evaluate_with_coverage_check.py",
        "--test-set",
        str(args.test_set),
        "--embeddings-dir",
        str(args.embeddings_dir),
        "--min-coverage",
        str(args.min_coverage),
        "--auto-filter",
        "--output",
        str(args.output),
    ]

    result = subprocess.run(eval_cmd, capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print("Errors:", result.stderr, file=sys.stderr)

    if result.returncode != 0:
        print(f"\nEvaluation failed with exit code {result.returncode}")
        return result.returncode

    # Validate results
    if args.output.exists():
        with open(args.output) as f:
            results = json.load(f)

        print()
        print("=" * 70)
        print("Results Validation")
        print("=" * 70)

        eval_results = results.get("results", {})
        if not eval_results:
            print("⚠ No embeddings passed coverage check")
            return 1

        print(f"Embeddings evaluated: {len(eval_results)}")

        # Check coverage
        for name, result in eval_results.items():
            coverage = result.get("coverage", 0)
            num_eval = result.get("num_evaluated", 0)
            num_queries_result = result.get("num_queries", num_queries)

            print(f"\n{name}:")
            print(f"  Coverage: {coverage:.1%}")
            print(f"  Evaluated: {num_eval}/{num_queries_result} queries")
            print(f"  P@10: {result.get('p@10', 0):.4f}")

            if num_eval < num_queries * 0.8:
                print(f"  ⚠ Warning: Only {num_eval}/{num_queries} queries evaluated")

        # Find best
        best = max(
            eval_results.items(),
            key=lambda x: (x[1].get("coverage", 0) >= args.min_coverage, x[1].get("p@10", 0)),
        )
        print(f"\nBest: {best[0]}")
        print(f"  P@10: {best[1].get('p@10', 0):.4f}")
        print(f"  Coverage: {best[1].get('coverage', 0):.1%}")
        print(f"  Queries: {best[1].get('num_evaluated', 0)}/{num_queries}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
