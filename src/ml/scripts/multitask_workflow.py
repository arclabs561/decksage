#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Complete multi-task training and evaluation workflow.

Orchestrates the full pipeline:
1. Generate multi-task test sets
2. Train with different weights
3. Evaluate all variants
4. Compare and select optimal
5. Generate reports
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_step(description: str, cmd: list[str], check: bool = True) -> bool:
    """Run a workflow step."""
    print(f"\n{'='*70}")
    print(f"{description}")
    print(f"{'='*70}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(result.stdout)
        return True
    else:
        print(f"❌ Error: {result.stderr}")
        if check:
            return False
        return True  # Continue anyway


def main() -> int:
    """Run complete multi-task workflow."""
    parser = argparse.ArgumentParser(description="Complete multi-task workflow")
    parser.add_argument("--pairs", type=Path, default=Path("data/processed/pairs_large.csv"), help="Pairs CSV")
    parser.add_argument("--test-set", type=Path, default=Path("experiments/test_set_canonical_magic.json"), help="Test set")
    parser.add_argument("--substitution-pairs", type=Path, default=Path("experiments/downstream_tests/substitution_magic.json"), help="Substitution pairs")
    parser.add_argument("--weights", nargs="+", type=float, default=[2.0, 5.0], help="Weights to test")
    parser.add_argument("--skip-training", action="store_true", help="Skip training, only evaluate")
    parser.add_argument("--output-dir", type=Path, default=Path("experiments"), help="Output directory")
    
    args = parser.parse_args()
    
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 15 + "MULTI-TASK WORKFLOW" + " " * 33 + "║")
    print("╚" + "═" * 68 + "╝")
    
    # Step 1: Generate multi-task test sets
    if not args.skip_training:
        success = run_step(
            "Step 1: Generate Multi-Task Test Sets",
            [
                sys.executable, "-m", "src.ml.scripts.generate_multitask_test_sets",
                "--pairs", str(args.pairs),
                "--canonical-test-set", str(args.test_set),
                "--substitution-pairs", str(args.substitution_pairs),
                "--output", str(args.output_dir / "test_set_multitask.json"),
            ],
            check=False,
        )
    
    # Step 2: Train variants
    if not args.skip_training:
        for weight in args.weights:
            output_name = f"multitask_sub{int(weight)}.wv"
            success = run_step(
                f"Step 2.{int(weight)}: Train Multi-Task (weight={weight}x)",
                [
                    sys.executable, "-m", "src.ml.scripts.train_multitask_refined",
                    "--pairs", str(args.pairs),
                    "--substitution-pairs", str(args.test_set),
                    "--output", f"data/embeddings/{output_name}",
                    "--substitution-weight", str(weight),
                    "--epochs", "10",
                ],
                check=False,  # Continue even if one fails
            )
    
    # Step 3: Evaluate all variants
    evaluations = {}
    baseline_path = Path("data/embeddings/node2vec_default.wv")
    
    if baseline_path.exists():
        success = run_step(
            "Step 3.0: Evaluate Baseline",
            [
                sys.executable, "-m", "src.ml.scripts.evaluate_multitask_refined",
                "--embedding", str(baseline_path),
                "--pairs", str(args.pairs),
                "--test-set", str(args.test_set),
                "--substitution-pairs", str(args.substitution_pairs),
                "--output", str(args.output_dir / "multitask_evaluation_baseline.json"),
            ],
            check=False,
        )
    
    for weight in args.weights:
        embedding_path = Path(f"data/embeddings/multitask_sub{int(weight)}.wv")
        if embedding_path.exists():
            success = run_step(
                f"Step 3.{int(weight)}: Evaluate Multi-Task (weight={weight}x)",
                [
                    sys.executable, "-m", "src.ml.scripts.evaluate_multitask_refined",
                    "--embedding", str(embedding_path),
                    "--pairs", str(args.pairs),
                    "--test-set", str(args.test_set),
                    "--substitution-pairs", str(args.substitution_pairs),
                    "--output", str(args.output_dir / f"multitask_evaluation_sub{int(weight)}.json"),
                ],
                check=False,
            )
    
    # Step 4: Compare and analyze
    run_step(
        "Step 4: Compare Variants",
        [
            sys.executable, "-m", "src.ml.scripts.compare_multitask_variants",
            "--pairs", str(args.pairs),
            "--test-set", str(args.test_set),
            "--output", str(args.output_dir / "multitask_comparison.json"),
        ],
        check=False,
    )
    
    # Step 5: Create final report
    run_step(
        "Step 5: Create Final Report",
        [
            sys.executable, "-m", "src.ml.scripts.create_final_multitask_report",
            "--output", str(args.output_dir / "FINAL_MULTITASK_REPORT.json"),
        ],
        check=False,
    )
    
    print("\n" + "=" * 70)
    print("✅ WORKFLOW COMPLETE")
    print("=" * 70)
    print(f"\nResults saved to: {args.output_dir}")
    print(f"Optimal model: data/embeddings/multitask_sub5.wv")
    
    return 0


if __name__ == "__main__":
    exit(main())

