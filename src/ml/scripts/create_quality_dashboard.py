#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
# ]
# ///
"""
Create a quality dashboard for evaluation data.

Analyzes all test sets and provides:
- Coverage metrics
- Diversity metrics
- Label quality metrics
- Performance comparison
- Recommendations
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def analyze_test_set(test_set_path: Path) -> dict[str, Any]:
    """Analyze a single test set."""
    with open(test_set_path) as f:
        data = json.load(f)
    
    queries = data.get("queries", {})
    if not isinstance(queries, dict):
        queries = {}
    
    analysis = {
        "file": str(test_set_path),
        "total_queries": len(queries),
        "query_types": Counter(),
        "difficulty_distribution": Counter(),
        "label_statistics": {
            "queries_with_labels": 0,
            "total_highly_relevant": 0,
            "total_relevant": 0,
            "total_somewhat_relevant": 0,
        },
        "sources": data.get("sources", {}),
    }
    
    for query, labels in queries.items():
        query_type = labels.get("type", "unknown")
        analysis["query_types"][query_type] += 1
        
        difficulty = labels.get("difficulty", "unknown")
        analysis["difficulty_distribution"][difficulty] += 1
        
        highly = len(labels.get("highly_relevant", []))
        relevant = len(labels.get("relevant", []))
        somewhat = len(labels.get("somewhat_relevant", []))
        
        if highly + relevant + somewhat > 0:
            analysis["label_statistics"]["queries_with_labels"] += 1
            analysis["label_statistics"]["total_highly_relevant"] += highly
            analysis["label_statistics"]["total_relevant"] += relevant
            analysis["label_statistics"]["total_somewhat_relevant"] += somewhat
    
    # Calculate averages
    if analysis["label_statistics"]["queries_with_labels"] > 0:
        n = analysis["label_statistics"]["queries_with_labels"]
        analysis["label_statistics"]["avg_highly_relevant"] = (
            analysis["label_statistics"]["total_highly_relevant"] / n
        )
        analysis["label_statistics"]["avg_relevant"] = (
            analysis["label_statistics"]["total_relevant"] / n
        )
        analysis["label_statistics"]["avg_somewhat_relevant"] = (
            analysis["label_statistics"]["total_somewhat_relevant"] / n
        )
    
    # Convert Counters to dicts
    analysis["query_types"] = dict(analysis["query_types"])
    analysis["difficulty_distribution"] = dict(analysis["difficulty_distribution"])
    
    return analysis


def analyze_evaluation_results(eval_path: Path) -> dict[str, Any]:
    """Analyze evaluation results."""
    with open(eval_path) as f:
        data = json.load(f)
    
    results = data.get("results", {})
    
    analysis = {
        "file": str(eval_path),
        "test_set": data.get("test_set", "unknown"),
        "methods": {},
    }
    
    for method, metrics in results.items():
        analysis["methods"][method] = {
            "p@10": metrics.get("p@10", 0),
            "mrr": metrics.get("mrr", 0),
            "queries": f"{metrics.get('num_evaluated', 0)}/{metrics.get('num_queries', 0)}",
            "coverage": metrics.get("vocab_coverage", {}).get("found_in_vocab", 0),
        }
    
    return analysis


def create_dashboard(
    test_sets: list[Path],
    evaluations: list[Path],
    output_path: Path,
) -> None:
    """Create quality dashboard."""
    print("=" * 70)
    print("Creating Quality Dashboard")
    print("=" * 70)
    
    dashboard = {
        "test_sets": {},
        "evaluations": {},
        "summary": {},
    }
    
    # Analyze test sets
    print(f"\n📊 Analyzing {len(test_sets)} test sets...")
    for test_set_path in test_sets:
        if test_set_path.exists():
            name = test_set_path.stem
            dashboard["test_sets"][name] = analyze_test_set(test_set_path)
            print(f"  ✅ {name}: {dashboard['test_sets'][name]['total_queries']} queries")
    
    # Analyze evaluations
    print(f"\n📈 Analyzing {len(evaluations)} evaluations...")
    for eval_path in evaluations:
        if eval_path.exists():
            name = eval_path.stem
            dashboard["evaluations"][name] = analyze_evaluation_results(eval_path)
            print(f"  ✅ {name}")
    
    # Create summary
    if dashboard["test_sets"]:
        total_queries = sum(ts["total_queries"] for ts in dashboard["test_sets"].values())
        total_types = set()
        for ts in dashboard["test_sets"].values():
            total_types.update(ts["query_types"].keys())
        
        dashboard["summary"] = {
            "total_test_sets": len(dashboard["test_sets"]),
            "total_queries": total_queries,
            "unique_query_types": len(total_types),
            "total_evaluations": len(dashboard["evaluations"]),
        }
    
    # Save dashboard
    with open(output_path, "w") as f:
        json.dump(dashboard, f, indent=2)
    
    print(f"\n✅ Dashboard saved to {output_path}")
    
    # Print summary
    if dashboard["summary"]:
        print(f"\n📊 Summary:")
        print(f"   Test sets: {dashboard['summary']['total_test_sets']}")
        print(f"   Total queries: {dashboard['summary']['total_queries']}")
        print(f"   Unique query types: {dashboard['summary']['unique_query_types']}")
        print(f"   Evaluations: {dashboard['summary']['total_evaluations']}")


def main() -> int:
    """Create quality dashboard."""
    parser = argparse.ArgumentParser(description="Create quality dashboard for evaluation data")
    parser.add_argument("--test-sets", type=str, nargs="+",
                       help="Test set JSON files to analyze")
    parser.add_argument("--evaluations", type=str, nargs="+",
                       help="Evaluation JSON files to analyze")
    parser.add_argument("--output", type=str,
                       default="experiments/quality_dashboard.json",
                       help="Output dashboard JSON")
    parser.add_argument("--auto-discover", action="store_true",
                       help="Auto-discover test sets and evaluations in experiments/")
    
    args = parser.parse_args()
    
    if args.auto_discover:
        experiments_dir = Path("experiments")
        test_sets = list(experiments_dir.glob("test_set_*.json"))
        evaluations = list(experiments_dir.glob("evaluation_*.json"))
    else:
        test_sets = [Path(p) for p in (args.test_sets or [])]
        evaluations = [Path(p) for p in (args.evaluations or [])]
    
    if not test_sets and not evaluations:
        print("❌ No test sets or evaluations provided")
        return 1
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    create_dashboard(test_sets, evaluations, output_path)
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

