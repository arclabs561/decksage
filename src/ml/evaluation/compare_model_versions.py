#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "pandas",
# ]
# ///
"""
Compare model performance across versions.

Compares evaluation results from different model versions to detect
performance regressions, improvements, or stability.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..utils.logging_config import log_exception, setup_script_logging


logger = setup_script_logging()


def load_evaluation_results(path: Path | str) -> dict[str, Any]:
    """Load evaluation results from file or S3."""
    path = Path(path)

    if not path.exists():
        # Try S3 path
        if str(path).startswith("s3://"):
            import subprocess

            result = subprocess.run(
                ["s5cmd", "cp", str(path), "/tmp/temp_eval.json"], capture_output=True, text=True
            )
            if result.returncode == 0:
                path = Path("/tmp/temp_eval.json")
            else:
                raise FileNotFoundError(f"Could not load from S3: {path}")
        else:
            raise FileNotFoundError(f"Evaluation file not found: {path}")

    with open(path) as f:
        return json.load(f)


def extract_metrics(results: dict[str, Any]) -> dict[str, float]:
    """Extract key metrics from evaluation results."""
    metrics = {}

    # Overall metrics
    if "overall" in results:
        overall = results["overall"]
        metrics["p_at_5"] = overall.get("p_at_5", 0.0)
        metrics["p_at_10"] = overall.get("p_at_10", 0.0)
        metrics["p_at_20"] = overall.get("p_at_20", 0.0)
        metrics["ndcg_at_10"] = overall.get("ndcg_at_10", 0.0)
        metrics["recall_at_10"] = overall.get("recall_at_10", 0.0)

    # Downstream task metrics
    if "downstream_tasks" in results:
        downstream = results["downstream_tasks"]
        metrics["completion_rate"] = downstream.get("completion_rate", 0.0)
        metrics["substitution_accuracy"] = downstream.get("substitution_accuracy", 0.0)

    return metrics


def compare_versions(
    current_path: Path | str,
    previous_path: Path | str,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Compare two model versions and compute deltas.

    Returns dict with:
    - current_metrics: Metrics from current version
    - previous_metrics: Metrics from previous version
    - deltas: Absolute and relative changes
    - regression_detected: Boolean indicating if regression >10%
    """
    logger.info(f"Loading current evaluation: {current_path}")
    current_results = load_evaluation_results(current_path)
    current_metrics = extract_metrics(current_results)

    logger.info(f"Loading previous evaluation: {previous_path}")
    previous_results = load_evaluation_results(previous_path)
    previous_metrics = extract_metrics(previous_results)

    # Compute deltas
    deltas = {}
    regression_detected = False

    for metric_name in current_metrics:
        current_val = current_metrics[metric_name]
        previous_val = previous_metrics.get(metric_name, 0.0)

        if previous_val > 0:
            delta_abs = current_val - previous_val
            delta_rel = (delta_abs / previous_val) * 100
        else:
            delta_abs = current_val
            delta_rel = 100.0 if current_val > 0 else 0.0

        deltas[f"{metric_name}_delta"] = delta_abs
        deltas[f"{metric_name}_delta_pct"] = delta_rel

        # Check for regression (P@10 drop >10%)
        if metric_name == "p_at_10" and delta_rel < -10.0:
            regression_detected = True
            logger.warning(f"Warning: Regression detected: P@10 dropped {delta_rel:.1f}%")

    comparison = {
        "current_version": str(current_path),
        "previous_version": str(previous_path),
        "current_metrics": current_metrics,
        "previous_metrics": previous_metrics,
        "deltas": deltas,
        "regression_detected": regression_detected,
        "summary": {
            "p_at_10_change": deltas.get("p_at_10_delta_pct", 0.0),
            "p_at_5_change": deltas.get("p_at_5_delta_pct", 0.0),
            "completion_rate_change": deltas.get("completion_rate_delta_pct", 0.0),
        },
    }

    # Save comparison
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(comparison, f, indent=2)
        logger.info(f"Comparison saved to: {output_path}")

    # Print summary
    print("\n" + "=" * 70)
    print("MODEL VERSION COMPARISON")
    print("=" * 70)
    print(f"Current: {current_path}")
    print(f"Previous: {previous_path}")
    print("\nKey Metrics:")
    print(
        f" P@10: {previous_metrics.get('p_at_10', 0):.4f} → {current_metrics.get('p_at_10', 0):.4f} ({deltas.get('p_at_10_delta_pct', 0):+.1f}%)"
    )
    print(
        f" P@5: {previous_metrics.get('p_at_5', 0):.4f} → {current_metrics.get('p_at_5', 0):.4f} ({deltas.get('p_at_5_delta_pct', 0):+.1f}%)"
    )
    print(
        f" Completion: {previous_metrics.get('completion_rate', 0):.4f} → {current_metrics.get('completion_rate', 0):.4f} ({deltas.get('completion_rate_delta_pct', 0):+.1f}%)"
    )

    if regression_detected:
        print("\nWarning: REGRESSION DETECTED: Consider rollback or investigation")
    else:
        print("\n✓ Performance acceptable")
    print("=" * 70)

    return comparison


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare model performance across versions")
    parser.add_argument(
        "--current",
        type=Path,
        required=True,
        help="Path to current evaluation results (JSON or S3)",
    )
    parser.add_argument(
        "--previous",
        type=Path,
        required=True,
        help="Path to previous evaluation results (JSON or S3)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for comparison JSON",
    )
    args = parser.parse_args()

    try:
        comparison = compare_versions(
            args.current,
            args.previous,
            args.output,
        )

        return 0 if not comparison["regression_detected"] else 1
    except Exception as e:
        log_exception(logger, "Comparison failed", e, include_context=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
