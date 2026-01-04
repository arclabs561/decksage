#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# ]
# ///
"""
Query evaluation history and model versions.

Provides utilities to:
- List all evaluations over time
- Compare versions
- Detect trends
- Find best/worst performing models
"""

from __future__ import annotations

import argparse
import json
import sys


try:
    from ..utils.evaluation_registry import EvaluationRegistry

    HAS_REGISTRY = True
except ImportError:
    try:
        from ml.utils.evaluation_registry import EvaluationRegistry

        HAS_REGISTRY = True
    except ImportError:
        HAS_REGISTRY = False


def list_evaluations(
    model_type: str | None = None,
    limit: int | None = None,
    output_format: str = "table",
) -> None:
    """List all evaluations."""
    if not HAS_REGISTRY:
        print("Error: EvaluationRegistry not available")
        return

    registry = EvaluationRegistry()
    evaluations = registry.list_evaluations(model_type=model_type, limit=limit)

    if not evaluations:
        print("No evaluations found")
        return

    if output_format == "json":
        print(json.dumps(evaluations, indent=2))
        return

    # Table format
    print(f"\n{'Version':<20} {'Type':<15} {'P@10':<10} {'MRR':<10} {'Date':<25}")
    print("-" * 80)

    for eval_record in evaluations:
        version = eval_record.get("model_version", "unknown")
        mtype = eval_record.get("model_type", "unknown")
        metrics = eval_record.get("metrics", {})
        p_at_10 = metrics.get("p_at_10", 0.0)
        mrr = metrics.get("mrr", 0.0)
        timestamp = eval_record.get("timestamp", "unknown")

        print(f"{version:<20} {mtype:<15} {p_at_10:<10.4f} {mrr:<10.4f} {timestamp:<25}")


def show_trends(model_type: str, metric: str = "p_at_10") -> None:
    """Show performance trends over time."""
    if not HAS_REGISTRY:
        print("Error: EvaluationRegistry not available")
        return

    registry = EvaluationRegistry()
    evaluations = registry.list_evaluations(model_type=model_type)

    if len(evaluations) < 2:
        print(f"Need at least 2 evaluations to show trends (found {len(evaluations)})")
        return

    print(f"\nPerformance Trend: {model_type} ({metric})")
    print("=" * 70)

    values = []
    for eval_record in evaluations:
        version = eval_record.get("model_version", "unknown")
        metrics = eval_record.get("metrics", {})
        value = metrics.get(metric, 0.0)
        timestamp = eval_record.get("timestamp", "unknown")
        values.append((version, value, timestamp))

    # Sort by timestamp (oldest first)
    values.sort(key=lambda x: x[2])

    print(f"{'Version':<20} {'Value':<10} {'Change':<15} {'Date':<25}")
    print("-" * 70)

    prev_value = None
    for version, value, timestamp in values:
        change = ""
        if prev_value is not None:
            delta = value - prev_value
            delta_pct = (delta / prev_value * 100) if prev_value > 0 else 0
            change = f"{delta:+.4f} ({delta_pct:+.1f}%)"

        print(f"{version:<20} {value:<10.4f} {change:<15} {timestamp:<25}")
        prev_value = value


def find_best(model_type: str, metric: str = "p_at_10") -> None:
    """Find best performing model."""
    if not HAS_REGISTRY:
        print("Error: EvaluationRegistry not available")
        return

    registry = EvaluationRegistry()
    evaluations = registry.list_evaluations(model_type=model_type)

    if not evaluations:
        print(f"No evaluations found for {model_type}")
        return

    # Find best by metric
    best = max(evaluations, key=lambda e: e.get("metrics", {}).get(metric, 0.0))

    version = best.get("model_version", "unknown")
    metrics = best.get("metrics", {})
    value = metrics.get(metric, 0.0)

    print(f"\nBest {model_type} model ({metric}):")
    print(f"  Version: {version}")
    print(f"  {metric}: {value:.4f}")
    print(f"  Model path: {best.get('model_path', 'unknown')}")
    print(f"  Test set: {best.get('test_set_path', 'unknown')}")
    print(f"  Timestamp: {best.get('timestamp', 'unknown')}")


def compare_versions(
    model_type: str,
    version1: str,
    version2: str,
) -> None:
    """Compare two versions."""
    if not HAS_REGISTRY:
        print("Error: EvaluationRegistry not available")
        return

    registry = EvaluationRegistry()
    comparison = registry.compare_evaluations(model_type, version1, version2)

    if not comparison:
        print(f"Could not compare {version1} and {version2}")
        return

    print(f"\nComparison: {version1} vs {version2}")
    print("=" * 70)
    print(f"Metric: {comparison['metric']}")
    print(f"  {version1}: {comparison['value1']:.4f}")
    print(f"  {version2}: {comparison['value2']:.4f}")
    print(f"  Delta: {comparison['delta']:+.4f} ({comparison['delta_pct']:+.1f}%)")
    print(f"  Improved: {comparison['improved']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Query evaluation history")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List command
    list_parser = subparsers.add_parser("list", help="List evaluations")
    list_parser.add_argument("--model-type", help="Filter by model type")
    list_parser.add_argument("--limit", type=int, help="Limit number of results")
    list_parser.add_argument("--format", choices=["table", "json"], default="table")

    # Trends command
    trends_parser = subparsers.add_parser("trends", help="Show performance trends")
    trends_parser.add_argument("--model-type", required=True, help="Model type")
    trends_parser.add_argument("--metric", default="p_at_10", help="Metric to track")

    # Best command
    best_parser = subparsers.add_parser("best", help="Find best model")
    best_parser.add_argument("--model-type", required=True, help="Model type")
    best_parser.add_argument("--metric", default="p_at_10", help="Metric to optimize")

    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare two versions")
    compare_parser.add_argument("--model-type", required=True, help="Model type")
    compare_parser.add_argument("--version1", required=True, help="First version")
    compare_parser.add_argument("--version2", required=True, help="Second version")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        if args.command == "list":
            list_evaluations(
                model_type=args.model_type,
                limit=args.limit,
                output_format=args.format,
            )
        elif args.command == "trends":
            show_trends(args.model_type, args.metric)
        elif args.command == "best":
            find_best(args.model_type, args.metric)
        elif args.command == "compare":
            compare_versions(args.model_type, args.version1, args.version2)

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
