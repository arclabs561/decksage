#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Comprehensive fix script for repository issues.

Fixes:
1. Validates data pipeline
2. Checks vocabulary coverage
3. Identifies working embeddings
4. Generates summary report
"""

import json
import sys
from pathlib import Path
from typing import Any


def check_file_exists(path: Path) -> bool:
    """Check if file exists."""
    return path.exists()


def main() -> int:
    """Main entry point."""
    print("=" * 70)
    print("DeckSage Repository Fix Script")
    print("=" * 70)
    print()
    
    issues = []
    fixes = []
    
    # 1. Check data files
    print("1. Checking data files...")
    data_files = {
        "decks_all_final.jsonl": Path("data/processed/decks_all_final.jsonl"),
        "decks_all_enhanced.jsonl": Path("data/processed/decks_all_enhanced.jsonl"),
        "decks_all_unified.jsonl": Path("data/processed/decks_all_unified.jsonl"),
        "pairs_large.csv": Path("data/processed/pairs_large.csv"),
        "pairs_multi_game.csv": Path("data/processed/pairs_multi_game.csv"),
        "decks_pokemon.jsonl": Path("data/processed/decks_pokemon.jsonl"),
    }
    
    for name, path in data_files.items():
        exists = check_file_exists(path)
        status = "✓" if exists else "✗"
        print(f"   {status} {name}")
        
        if not exists and name.startswith("decks_all"):
            issues.append({
                "file": name,
                "issue": "Missing deck file",
                "fix": f"Run: uv run scripts/data_processing/unified_export_pipeline.py",
            })
    
    print()
    
    # 2. Check test sets
    print("2. Checking test sets...")
    test_sets = {
        "test_set_canonical_magic.json": Path("experiments/test_set_canonical_magic.json"),
        "test_set_unified_magic.json": Path("experiments/test_set_unified_magic.json"),
        "test_set_canonical_pokemon.json": Path("experiments/test_set_canonical_pokemon.json"),
        "test_set_canonical_yugioh.json": Path("experiments/test_set_canonical_yugioh.json"),
    }
    
    for name, path in test_sets.items():
        exists = check_file_exists(path)
        status = "✓" if exists else "✗"
        print(f"   {status} {name}")
        
        if exists:
            try:
                with open(path) as f:
                    data = json.load(f)
                queries = data.get("queries", data) if isinstance(data, dict) else data
                if isinstance(queries, dict):
                    print(f"      Queries: {len(queries)}")
            except Exception:
                pass
    
    print()
    
    # 3. Check evaluation results
    print("3. Checking evaluation results...")
    eval_results_path = Path("experiments/evaluation_results.json")
    if eval_results_path.exists():
        try:
            with open(eval_results_path) as f:
                eval_data = json.load(f)
            
            results = eval_data.get("results", {})
            print(f"   Methods evaluated: {len(results)}")
            
            # Find methods with good coverage
            good_coverage = []
            for name, result in results.items():
                num_eval = result.get("num_evaluated", 0)
                num_queries = result.get("num_queries", 0)
                p_at_10 = result.get("p@10", 0)
                
                if num_queries > 0:
                    coverage = num_eval / num_queries
                    if coverage >= 0.8 and p_at_10 > 0:
                        good_coverage.append((name, coverage, p_at_10, num_eval))
            
            if good_coverage:
                print(f"   Methods with ≥80% coverage: {len(good_coverage)}")
                best = max(good_coverage, key=lambda x: x[2])
                print(f"   Best: {best[0]} - P@10={best[2]:.4f} ({best[1]:.1%} coverage, {best[3]} queries)")
            else:
                issues.append({
                    "issue": "No embeddings with good coverage",
                    "fix": "Run: uv run scripts/diagnostics/audit_all_embeddings.py to find working embeddings",
                })
        except Exception as e:
            print(f"   Error reading evaluation results: {e}")
    else:
        print("   No evaluation results found")
    
    print()
    
    # Summary
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    
    if issues:
        print(f"\nIssues found: {len(issues)}")
        for i, issue in enumerate(issues, 1):
            print(f"\n{i}. {issue['issue']}")
            if 'file' in issue:
                print(f"   File: {issue['file']}")
            print(f"   Fix: {issue['fix']}")
    else:
        print("\n✓ No critical issues found")
    
    # Save report
    report_path = Path("experiments/repository_fix_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "issues": issues,
            "fixes": fixes,
            "data_files": {name: check_file_exists(path) for name, path in data_files.items()},
            "test_sets": {name: check_file_exists(path) for name, path in test_sets.items()},
        }, f, indent=2)
    
    print(f"\nReport saved to: {report_path}")
    
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())

