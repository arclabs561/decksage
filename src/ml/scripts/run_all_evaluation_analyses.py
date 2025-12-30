#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pandas",
#   "numpy",
#   "gensim",
# ]
# ///
"""
Run all evaluation analyses in sequence.

1. Embedding vs Jaccard investigation
2. Per-query analysis
3. Baseline evaluation
4. Synthetic label validation
5. Generate comprehensive report
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run_analysis(script_name: str, args: list[str], description: str) -> bool:
    """Run an analysis script."""
    print(f"\n{'='*70}")
    print(f"{description}")
    print(f"{'='*70}")
    
    cmd = [sys.executable, "-m", f"src.ml.scripts.{script_name}"] + args
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print(result.stdout)
            return True
        else:
            print(f"Error: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⚠️  Timeout after 5 minutes")
        return False
    except Exception as e:
        print(f"⚠️  Error: {e}")
        return False


def main() -> int:
    """Run all evaluation analyses."""
    parser = argparse.ArgumentParser(description="Run all evaluation analyses")
    parser.add_argument("--embedding", type=Path, default=Path("data/embeddings/node2vec_default.wv"), help="Embedding file")
    parser.add_argument("--pairs", type=Path, default=Path("data/processed/pairs_large.csv"), help="Pairs CSV")
    parser.add_argument("--test-set", type=Path, default=Path("experiments/test_set_expanded_magic.json"), help="Test set JSON")
    parser.add_argument("--output-dir", type=Path, default=Path("experiments"), help="Output directory")
    
    args = parser.parse_args()
    
    if not args.embedding.exists():
        print(f"❌ Embedding not found: {args.embedding}")
        return 1
    
    if not args.pairs.exists():
        print(f"❌ Pairs CSV not found: {args.pairs}")
        return 1
    
    if not args.test_set.exists():
        print(f"❌ Test set not found: {args.test_set}")
        return 1
    
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    results = {}
    
    # 1. Embedding vs Jaccard investigation
    if args.test_set.name != "test_set_expanded_magic.json":
        # Use canonical for this analysis (smaller, faster)
        canonical_test = Path("experiments/test_set_canonical_magic.json")
        if canonical_test.exists():
            test_set_for_jaccard = canonical_test
        else:
            test_set_for_jaccard = args.test_set
    else:
        test_set_for_jaccard = Path("experiments/test_set_canonical_magic.json")
        if not test_set_for_jaccard.exists():
            test_set_for_jaccard = args.test_set
    
    success = run_analysis(
        "investigate_embedding_vs_jaccard",
        [
            "--embedding", str(args.embedding),
            "--pairs", str(args.pairs),
            "--test-set", str(test_set_for_jaccard),
            "--output", str(args.output_dir / "embedding_vs_jaccard.json"),
        ],
        "1. Investigating Embedding vs Jaccard Similarity",
    )
    results["embedding_vs_jaccard"] = success
    
    # 2. Per-query analysis
    success = run_analysis(
        "per_query_analysis",
        [
            "--embedding", str(args.embedding),
            "--test-set", str(args.test_set),
            "--output", str(args.output_dir / "per_query_analysis.json"),
        ],
        "2. Per-Query Failure Analysis",
    )
    results["per_query_analysis"] = success
    
    # 3. Baseline evaluation
    success = run_analysis(
        "evaluate_baselines",
        [
            "--test-set", str(args.test_set),
            "--pairs", str(args.pairs),
            "--output", str(args.output_dir / "baseline_results.json"),
        ],
        "3. Evaluating Baselines (Random, Popular)",
    )
    results["baselines"] = success
    
    # 4. Synthetic label validation
    success = run_analysis(
        "validate_synthetic_labels",
        [
            "--test-set", str(args.test_set),
            "--output", str(args.output_dir / "label_validation.json"),
            "--sample", "20",
        ],
        "4. Validating Synthetic Labels",
    )
    results["label_validation"] = success
    
    # Summary
    print(f"\n{'='*70}")
    print("Analysis Summary")
    print(f"{'='*70}")
    
    for analysis, success in results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {analysis}")
    
    # Generate comprehensive report
    report_path = args.output_dir / "comprehensive_analysis_report.json"
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "config": {
                "embedding": str(args.embedding),
                "pairs": str(args.pairs),
                "test_set": str(args.test_set),
            },
            "results": results,
        }, f, indent=2)
    
    print(f"\n✅ Comprehensive report saved to {report_path}")
    
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    exit(main())

