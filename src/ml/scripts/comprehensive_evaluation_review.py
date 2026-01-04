#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy",
# ]
# ///
"""
Comprehensive evaluation review and analysis.

Reviews all evaluation results, identifies patterns, and provides recommendations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ml.utils.paths import PATHS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_evaluation_results() -> dict[str, dict[str, Any]]:
    """Load all evaluation results from various locations."""
    results = {}
    
    # Production embeddings
    prod_eval = PATHS.embeddings / "production_eval.json"
    if prod_eval.exists():
        with open(prod_eval) as f:
            data = json.load(f)
            results["production"] = {
                "cooccurrence_p@10": data["tasks"]["cooccurrence"]["p@10"],
                "functional_p@10": data["tasks"]["functional_similarity"]["p@10"],
                "cooccurrence_n": data["tasks"]["cooccurrence"]["num_queries"],
                "functional_n": data["tasks"]["functional_similarity"]["num_queries"],
            }
    
    # Multitask enhanced (50 queries)
    mt_eval = PATHS.embeddings / "multitask_enhanced_vv2024-W01_eval.json"
    if mt_eval.exists():
        with open(mt_eval) as f:
            data = json.load(f)
            results["multitask_enhanced_50"] = {
                "cooccurrence_p@10": data["tasks"]["cooccurrence"]["p@10"],
                "functional_p@10": data["tasks"]["functional_similarity"]["p@10"],
                "cooccurrence_n": data["tasks"]["cooccurrence"]["num_queries"],
                "functional_n": data["tasks"]["functional_similarity"]["num_queries"],
            }
    
    # Multitask enhanced (500 queries)
    mt_eval_full = PATHS.embeddings / "multitask_enhanced_vv2024-W01_eval_full.json"
    if mt_eval_full.exists():
        with open(mt_eval_full) as f:
            data = json.load(f)
            results["multitask_enhanced_500"] = {
                "cooccurrence_p@10": data["tasks"]["cooccurrence"]["p@10"],
                "functional_p@10": data["tasks"]["functional_similarity"]["p@10"],
                "cooccurrence_n": data["tasks"]["cooccurrence"]["num_queries"],
                "functional_n": data["tasks"]["functional_similarity"]["num_queries"],
            }
    
    # Hybrid evaluation
    hybrid_eval = PATHS.experiments / "evaluation_results" / "hybrid_evaluation_v2026-W01.json"
    if hybrid_eval.exists():
        with open(hybrid_eval) as f:
            data = json.load(f)
            results["hybrid_2026_W01"] = {
                "p@10": data["metrics"].get("p_at_10", 0.0),
            }
    
    return results


def analyze_results(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Analyze evaluation results and provide insights."""
    analysis = {
        "summary": {},
        "findings": [],
        "recommendations": [],
    }
    
    # Compare small vs large test sets
    if "multitask_enhanced_50" in results and "multitask_enhanced_500" in results:
        p50 = results["multitask_enhanced_50"]["cooccurrence_p@10"]
        p500 = results["multitask_enhanced_500"]["cooccurrence_p@10"]
        drop = p50 - p500
        analysis["findings"].append(
            f"Test set size impact: P@10 drops from {p50:.4f} (50 queries) to {p500:.4f} (500 queries) = {drop:.4f} drop"
        )
        if drop > 0.05:
            analysis["recommendations"].append(
                "Small test sets show inflated metrics - use larger test sets (500+) for reliable evaluation"
            )
    
    # Compare production vs enhanced
    if "production" in results and "multitask_enhanced_50" in results:
        prod = results["production"]["cooccurrence_p@10"]
        enh = results["multitask_enhanced_50"]["cooccurrence_p@10"]
        improvement = enh - prod
        analysis["findings"].append(
            f"Multitask enhancement improves P@10 from {prod:.4f} to {enh:.4f} = {improvement:.4f} improvement (on 50 queries)"
        )
    
    # Check against target
    target = 0.15
    if "hybrid_2026_W01" in results:
        hybrid_p10 = results["hybrid_2026_W01"]["p@10"]
        gap = target - hybrid_p10
        analysis["findings"].append(
            f"Hybrid system P@10 = {hybrid_p10:.4f}, target = {target:.4f}, gap = {gap:.4f}"
        )
        if gap > 0:
            analysis["recommendations"].append(
                f"Hybrid system below target - need {gap:.4f} improvement to reach {target:.4f}"
            )
    
    # Functional similarity performance
    if "production" in results:
        func_p10 = results["production"]["functional_p@10"]
        cooc_p10 = results["production"]["cooccurrence_p@10"]
        if func_p10 < cooc_p10 * 0.5:
            analysis["findings"].append(
                f"Functional similarity underperforms: {func_p10:.4f} vs co-occurrence {cooc_p10:.4f}"
            )
            analysis["recommendations"].append(
                "Review functional tagger quality - may need improvement or different weighting"
            )
    
    return analysis


def main() -> int:
    """Run comprehensive evaluation review."""
    logger.info("=" * 60)
    logger.info("Comprehensive Evaluation Review")
    logger.info("=" * 60)
    
    # Load results
    results = load_evaluation_results()
    
    if not results:
        logger.error("No evaluation results found")
        return 1
    
    logger.info(f"\nLoaded {len(results)} evaluation result sets")
    
    # Analyze
    analysis = analyze_results(results)
    
    # Print findings
    logger.info("\n" + "=" * 60)
    logger.info("Findings")
    logger.info("=" * 60)
    for finding in analysis["findings"]:
        logger.info(f"  • {finding}")
    
    # Print recommendations
    logger.info("\n" + "=" * 60)
    logger.info("Recommendations")
    logger.info("=" * 60)
    for rec in analysis["recommendations"]:
        logger.info(f"  • {rec}")
    
    # Save analysis
    output_path = PATHS.experiments / "evaluation_analysis.json"
    with open(output_path, "w") as f:
        json.dump({
            "results": results,
            "analysis": analysis,
        }, f, indent=2)
    
    logger.info(f"\n📁 Analysis saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

