#!/usr/bin/env python3
"""
Run all analysis scripts to understand system scientifically.

This script orchestrates all analysis tools to provide comprehensive
understanding of current system performance and identify improvements.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from ..utils.logging_config import setup_script_logging


logger = setup_script_logging()


def run_analysis_script(script_name: str, args: list[str] = None) -> dict:
    """
    Run an analysis script and return results.

    Args:
        script_name: Name of script to run
        args: Additional arguments

    Returns:
        Dict with results or error
    """
    script_path = Path(__file__).parent / script_name

    if not script_path.exists():
        return {"error": f"Script not found: {script_name}"}

    cmd = [sys.executable, str(script_path)] + (args or [])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode == 0:
            # Try to parse JSON output if available
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"output": result.stdout, "status": "success"}
        else:
            return {
                "error": result.stderr,
                "status": "failed",
                "returncode": result.returncode,
            }
    except subprocess.TimeoutExpired:
        return {"error": "Script timed out", "status": "timeout"}
    except Exception as e:
        return {"error": str(e), "status": "error"}


def main():
    """Run all analysis scripts."""
    import argparse

    parser = argparse.ArgumentParser(description="Run comprehensive system analysis")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/comprehensive_analysis.json"),
        help="Output path for combined results",
    )
    parser.add_argument(
        "--skip",
        nargs="+",
        help="Scripts to skip",
        default=[],
    )

    args = parser.parse_args()

    logger.info("Running comprehensive system analysis...")

    analyses = {}

    # 1. Find best experiments
    if "find_best" not in args.skip:
        logger.info("1. Finding best experiments...")
        result = run_analysis_script("find_best_experiment.py", ["--top-n", "10"])
        analyses["best_experiments"] = result

    # 2. Weight sensitivity
    if "weight_sensitivity" not in args.skip:
        logger.info("2. Analyzing weight sensitivity...")
        result = run_analysis_script("weight_sensitivity.py", ["--suggest"])
        analyses["weight_sensitivity"] = result

    # 3. Signal performance (if similarity functions available)
    if "signal_performance" not in args.skip:
        logger.info("3. Measuring individual signal performance...")
        # This may fail if similarity functions not importable
        result = run_analysis_script("measure_signal_performance.py")
        analyses["signal_performance"] = result

    # 4. Failure analysis (if predictions available)
    if "failures" not in args.skip:
        logger.info("4. Analyzing failure cases...")
        result = run_analysis_script("analyze_failures.py")
        analyses["failures"] = result

    # Save combined results
    with open(args.output, "w") as f:
        json.dump(analyses, f, indent=2)

    logger.info(f"Analysis complete. Results saved to {args.output}")

    # Print summary
    print("\n=== Analysis Summary ===")
    for name, result in analyses.items():
        if "error" in result:
            print(f"{name}: ERROR - {result['error']}")
        else:
            print(f"{name}: SUCCESS")

    return 0


if __name__ == "__main__":
    sys.exit(main())
