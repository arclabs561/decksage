#!/usr/bin/env python3
"""
Analyze weight sensitivity in fusion grid search.

Scientific analysis: Understand how P@10 changes with weight variations
to identify if current weights are optimal and if small adjustments help.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from ..utils.logging_config import setup_script_logging


logger = setup_script_logging()


def analyze_weight_sensitivity(
    grid_search_results: dict[str, Any] | Path,
    current_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Analyze sensitivity of P@10 to weight changes.

    Args:
        grid_search_results: Dict or path to grid search results
        current_weights: Current best weights (for comparison)

    Returns:
        Dict with sensitivity analysis
    """
    # Load results
    if isinstance(grid_search_results, Path):
        with open(grid_search_results) as f:
            results = json.load(f)
    else:
        results = grid_search_results

    # Extract weight combinations and scores
    # Format depends on how grid search stores results
    # Assuming format: list of {weights: {...}, score: float}

    if "results" in results:
        weight_scores = results["results"]
    else:
        # Single best result
        weight_scores = [
            {
                "weights": results.get("best_weights", {}),
                "score": results.get("best_score", 0.0),
            }
        ]

    # Analyze sensitivity per weight dimension
    sensitivity = {}

    for signal_name in ["embed", "jaccard", "functional"]:
        signal_weights = []
        signal_scores = []

        for result in weight_scores:
            weights = result.get("weights", {})
            score = result.get("score", 0.0)

            if signal_name in weights:
                signal_weights.append(weights[signal_name])
                signal_scores.append(score)

        if signal_weights:
            # Compute correlation
            correlation = np.corrcoef(signal_weights, signal_scores)[0, 1]

            # Compute sensitivity (change in score per unit change in weight)
            if len(signal_weights) > 1:
                weight_range = max(signal_weights) - min(signal_weights)
                score_range = max(signal_scores) - min(signal_scores)
                sensitivity_per_unit = score_range / weight_range if weight_range > 0 else 0.0
            else:
                sensitivity_per_unit = 0.0

            sensitivity[signal_name] = {
                "correlation": float(correlation),
                "sensitivity_per_unit": float(sensitivity_per_unit),
                "weight_range": [float(min(signal_weights)), float(max(signal_weights))],
                "score_range": [float(min(signal_scores)), float(max(signal_scores))],
            }

    # Compare current weights to optimal
    if current_weights and weight_scores:
        best_result = max(weight_scores, key=lambda x: x.get("score", 0.0))
        best_weights = best_result.get("weights", {})
        best_score = best_result.get("score", 0.0)

        current_score = None
        # Find score for current weights (if in results)
        for result in weight_scores:
            if result.get("weights") == current_weights:
                current_score = result.get("score")
                break

        comparison = {
            "best_weights": best_weights,
            "best_score": float(best_score),
            "current_weights": current_weights,
            "current_score": float(current_score) if current_score is not None else None,
            "improvement_potential": float(best_score - current_score) if current_score else None,
        }
    else:
        comparison = {}

    return {
        "sensitivity": sensitivity,
        "comparison": comparison,
        "n_combinations": len(weight_scores),
    }


def suggest_weight_adjustments(
    sensitivity_analysis: dict[str, Any],
    current_weights: dict[str, float],
    step_size: float = 0.05,
) -> list[dict[str, Any]]:
    """
    Suggest small weight adjustments based on sensitivity.

    Args:
        sensitivity_analysis: Results from analyze_weight_sensitivity
        current_weights: Current weights
        step_size: Size of adjustment to try

    Returns:
        List of suggested weight combinations
    """
    suggestions = []
    sensitivity = sensitivity_analysis.get("sensitivity", {})

    # For each signal, try increasing/decreasing if sensitive
    for signal_name, sens_data in sensitivity.items():
        if signal_name not in current_weights:
            continue

        current_weight = current_weights[signal_name]
        correlation = sens_data.get("correlation", 0.0)

        # If positive correlation, try increasing
        if correlation > 0.1:
            new_weights = current_weights.copy()
            new_weights[signal_name] = min(1.0, current_weight + step_size)
            # Normalize
            total = sum(new_weights.values())
            new_weights = {k: v / total for k, v in new_weights.items()}
            suggestions.append(
                {
                    "weights": new_weights,
                    "adjustment": f"increase_{signal_name}",
                    "reason": f"Positive correlation ({correlation:.2f})",
                }
            )

        # If negative correlation, try decreasing
        elif correlation < -0.1:
            new_weights = current_weights.copy()
            new_weights[signal_name] = max(0.0, current_weight - step_size)
            # Normalize
            total = sum(new_weights.values())
            new_weights = {k: v / total for k, v in new_weights.items()}
            suggestions.append(
                {
                    "weights": new_weights,
                    "adjustment": f"decrease_{signal_name}",
                    "reason": f"Negative correlation ({correlation:.2f})",
                }
            )

    return suggestions


def main():
    """Run weight sensitivity analysis."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze weight sensitivity")
    parser.add_argument(
        "--grid-search",
        type=Path,
        default=Path("experiments/fusion_grid_search_latest.json"),
        help="Path to grid search results",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/weight_sensitivity.json"),
        help="Output path for results",
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="Generate weight adjustment suggestions",
    )

    args = parser.parse_args()

    logger.info("Weight sensitivity analysis")
    logger.info(f"Grid search: {args.grid_search}")

    # Load current weights
    with open(args.grid_search) as f:
        grid_data = json.load(f)

    current_weights = grid_data.get("best_weights", {})

    # Analyze
    results = analyze_weight_sensitivity(grid_data, current_weights)

    # Generate suggestions if requested
    if args.suggest:
        suggestions = suggest_weight_adjustments(results, current_weights)
        results["suggestions"] = suggestions

    # Save results
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Results saved to {args.output}")

    # Print summary
    print("\nWeight Sensitivity Analysis:")
    for signal, sens in results.get("sensitivity", {}).items():
        print(f"  {signal}:")
        print(f"    Correlation: {sens['correlation']:.3f}")
        print(f"    Sensitivity: {sens['sensitivity_per_unit']:.3f} P@10 per unit weight")

    if "comparison" in results and results["comparison"].get("improvement_potential"):
        imp = results["comparison"]["improvement_potential"]
        print(f"\nImprovement potential: {imp:.4f} P@10")


if __name__ == "__main__":
    main()
