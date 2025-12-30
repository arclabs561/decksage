#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "scipy>=1.10.0",
# ]
# ///
"""
Statistical significance testing for evaluation results.

Compares embedding methods using:
1. Paired t-test
2. Wilcoxon signed-rank test
3. Bootstrap confidence intervals
4. Effect size (Cohen's d)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    import numpy as np
    from scipy import stats
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def paired_t_test(scores1: list[float], scores2: list[float]) -> dict[str, Any]:
    """Paired t-test for comparing two methods."""
    if not HAS_DEPS:
        return {}
    
    if len(scores1) != len(scores2):
        return {"error": "Scores must have same length"}
    
    t_stat, p_value = stats.ttest_rel(scores1, scores2)
    
    return {
        "test": "paired_t_test",
        "t_statistic": float(t_stat),
        "p_value": float(p_value),
        "significant": bool(p_value < 0.05),
        "mean_diff": float(np.mean(scores1) - np.mean(scores2)),
    }


def wilcoxon_test(scores1: list[float], scores2: list[float]) -> dict[str, Any]:
    """Wilcoxon signed-rank test (non-parametric)."""
    if not HAS_DEPS:
        return {}
    
    if len(scores1) != len(scores2):
        return {"error": "Scores must have same length"}
    
    try:
        stat, p_value = stats.wilcoxon(scores1, scores2)
    except ValueError:
        # All differences are zero
        return {
            "test": "wilcoxon",
            "statistic": 0.0,
            "p_value": 1.0,
            "significant": False,
            "mean_diff": 0.0,
        }
    
    return {
        "test": "wilcoxon",
        "statistic": float(stat),
        "p_value": float(p_value),
        "significant": bool(p_value < 0.05),
        "mean_diff": float(np.mean(scores1) - np.mean(scores2)),
    }


def cohens_d(scores1: list[float], scores2: list[float]) -> float:
    """Calculate Cohen's d (effect size)."""
    if not HAS_DEPS:
        return 0.0
    
    if len(scores1) != len(scores2):
        return 0.0
    
    diff = np.array(scores1) - np.array(scores2)
    pooled_std = np.sqrt((np.var(scores1) + np.var(scores2)) / 2)
    
    if pooled_std == 0:
        return 0.0
    
    return float(np.mean(diff) / pooled_std)


def compare_evaluation_results(
    eval1_path: Path,
    eval2_path: Path,
    metric: str = "p@10",
) -> dict[str, Any]:
    """Compare two evaluation results statistically."""
    if not HAS_DEPS:
        return {}
    
    print(f"📊 Comparing evaluations: {eval1_path.name} vs {eval2_path.name}")
    
    # Load results
    with open(eval1_path) as f:
        data1 = json.load(f)
    with open(eval2_path) as f:
        data2 = json.load(f)
    
    # Extract per-query scores
    per_query1 = data1.get("per_query_results", {})
    per_query2 = data2.get("per_query_results", {})
    
    # Find common queries
    common_queries = set(per_query1.keys()) & set(per_query2.keys())
    
    if not common_queries:
        return {"error": "No common queries found"}
    
    scores1 = [per_query1[q].get(metric, 0) for q in common_queries]
    scores2 = [per_query2[q].get(metric, 0) for q in common_queries]
    
    # Statistical tests
    t_test = paired_t_test(scores1, scores2)
    wilcoxon = wilcoxon_test(scores1, scores2)
    effect_size = cohens_d(scores1, scores2)
    
    comparison = {
        "metric": metric,
        "num_common_queries": len(common_queries),
        "method1": {
            "file": str(eval1_path),
            "mean": float(np.mean(scores1)),
            "std": float(np.std(scores1)),
        },
        "method2": {
            "file": str(eval2_path),
            "mean": float(np.mean(scores2)),
            "std": float(np.std(scores2)),
        },
        "paired_t_test": t_test,
        "wilcoxon_test": wilcoxon,
        "effect_size": effect_size,
        "interpretation": interpret_effect_size(effect_size),
    }
    
    print(f"  ✅ Compared {len(common_queries)} queries")
    print(f"     Method 1: {comparison['method1']['mean']:.4f} ± {comparison['method1']['std']:.4f}")
    print(f"     Method 2: {comparison['method2']['mean']:.4f} ± {comparison['method2']['std']:.4f}")
    print(f"     Effect size: {effect_size:.3f} ({comparison['interpretation']})")
    print(f"     Significant: {t_test.get('significant', False)} (p={t_test.get('p_value', 1.0):.4f})")
    
    return comparison


def interpret_effect_size(d: float) -> str:
    """Interpret Cohen's d effect size."""
    abs_d = abs(d)
    if abs_d < 0.2:
        return "negligible"
    elif abs_d < 0.5:
        return "small"
    elif abs_d < 0.8:
        return "medium"
    else:
        return "large"


def compare_all_methods(
    evaluations: dict[str, Path],
    metric: str = "p@10",
    baseline: str | None = None,
) -> dict[str, Any]:
    """Compare all methods against each other."""
    if not HAS_DEPS:
        return {}
    
    print(f"📊 Comparing all methods on {metric}...")
    
    comparisons = {}
    methods = list(evaluations.keys())
    
    # Compare each pair
    for i, method1 in enumerate(methods):
        for method2 in methods[i+1:]:
            key = f"{method1}_vs_{method2}"
            comparison = compare_evaluation_results(
                evaluations[method1],
                evaluations[method2],
                metric=metric,
            )
            comparisons[key] = comparison
    
    # Compare all against baseline if specified
    if baseline and baseline in evaluations:
        baseline_comparisons = {}
        for method in methods:
            if method != baseline:
                comparison = compare_evaluation_results(
                    evaluations[baseline],
                    evaluations[method],
                    metric=metric,
                )
                baseline_comparisons[f"{baseline}_vs_{method}"] = comparison
        comparisons["baseline_comparisons"] = baseline_comparisons
    
    return {
        "metric": metric,
        "comparisons": comparisons,
        "summary": {
            "num_methods": len(methods),
            "num_comparisons": len(comparisons),
        },
    }


def main() -> int:
    """Statistical significance testing."""
    parser = argparse.ArgumentParser(
        description="Statistical significance testing for evaluation results"
    )
    parser.add_argument("--eval1", type=str, required=True,
                       help="First evaluation JSON")
    parser.add_argument("--eval2", type=str, required=True,
                       help="Second evaluation JSON")
    parser.add_argument("--output", type=str,
                       default="experiments/statistical_comparison.json",
                       help="Output comparison JSON")
    parser.add_argument("--metric", type=str, default="p@10",
                       choices=["p@10", "recall@10", "ndcg@10", "map@10", "mrr"],
                       help="Metric to compare")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("❌ Missing dependencies (numpy, scipy)")
        return 1
    
    eval1_path = Path(args.eval1)
    eval2_path = Path(args.eval2)
    
    if not eval1_path.exists():
        print(f"❌ Evaluation 1 not found: {eval1_path}")
        return 1
    
    if not eval2_path.exists():
        print(f"❌ Evaluation 2 not found: {eval2_path}")
        return 1
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Compare
    comparison = compare_evaluation_results(
        eval1_path,
        eval2_path,
        metric=args.metric,
    )
    
    # Save
    with open(output_path, "w") as f:
        json.dump(comparison, f, indent=2)
    
    print(f"\n✅ Comparison saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
