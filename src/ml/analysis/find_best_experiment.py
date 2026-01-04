#!/usr/bin/env python3
"""
Find best performing experiment from log.

Scientific analysis: Identify what worked to replicate success.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from ..utils.logging_config import setup_script_logging

logger = setup_script_logging()


def find_best_experiments(
    log_path: Path,
    min_p10: float = 0.10,
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """
    Find best performing experiments from log.
    
    Args:
        log_path: Path to experiment log JSONL
        min_p10: Minimum P@10 to consider
        top_n: Number of top experiments to return
    
    Returns:
        List of experiment dicts, sorted by P@10
    """
    experiments = []
    
    with open(log_path) as f:
        for line in f:
            try:
                exp = json.loads(line)
                p10 = exp.get("results", {}).get("p10", 0.0)
                if p10 >= min_p10:
                    experiments.append(exp)
            except json.JSONDecodeError:
                continue
    
    # Sort by P@10 descending
    experiments.sort(key=lambda x: x.get("results", {}).get("p10", 0.0), reverse=True)
    
    return experiments[:top_n]


def analyze_best_method(
    experiment: dict[str, Any],
) -> dict[str, Any]:
    """
    Analyze what made an experiment successful.
    
    Args:
        experiment: Experiment dict
    
    Returns:
        Dict with analysis
    """
    results = experiment.get("results", {})
    method = experiment.get("method", "unknown")
    weights = results.get("weights", {})
    p10 = results.get("p10", 0.0)
    
    analysis = {
        "experiment_id": experiment.get("experiment_id"),
        "method": method,
        "p10": p10,
        "weights": weights,
        "hypothesis": experiment.get("hypothesis"),
        "data": experiment.get("data"),
        "test_set": experiment.get("test_set"),
        "keywords": experiment.get("keywords", []),
        "tags": experiment.get("tags", []),
        "date": experiment.get("date"),
    }
    
    # Extract key insights
    insights = []
    
    if "jaccard" in method.lower():
        insights.append("Uses Jaccard similarity")
    
    if weights:
        insights.append(f"Weights: {weights}")
    
    if experiment.get("phase") == "research_informed":
        insights.append("Research-informed approach")
    
    analysis["insights"] = insights
    
    return analysis


def main():
    """Find and analyze best experiments."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Find best experiments")
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("experiments/EXPERIMENT_LOG_CANONICAL.jsonl"),
        help="Path to experiment log",
    )
    parser.add_argument(
        "--min-p10",
        type=float,
        default=0.10,
        help="Minimum P@10 to consider",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/best_experiments.json"),
        help="Output path",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of top experiments to analyze",
    )
    
    args = parser.parse_args()
    
    logger.info("Finding best experiments")
    logger.info(f"Log: {args.log}")
    logger.info(f"Min P@10: {args.min_p10}")
    
    # Find best experiments
    best = find_best_experiments(args.log, args.min_p10, args.top_n)
    
    # Analyze each
    analyses = []
    for exp in best:
        analysis = analyze_best_method(exp)
        analyses.append(analysis)
    
    # Save results
    results = {
        "total_found": len(best),
        "min_p10": args.min_p10,
        "experiments": analyses,
    }
    
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    
    logger.info(f"Results saved to {args.output}")
    
    # Print summary
    print(f"\nTop {len(best)} Experiments (P@10 >= {args.min_p10}):")
    for i, analysis in enumerate(analyses, 1):
        print(f"\n{i}. {analysis['experiment_id']}: P@10 = {analysis['p10']:.4f}")
        print(f"   Method: {analysis['method']}")
        if analysis['weights']:
            print(f"   Weights: {analysis['weights']}")
        if analysis['insights']:
            print(f"   Insights: {', '.join(analysis['insights'])}")


if __name__ == "__main__":
    main()







