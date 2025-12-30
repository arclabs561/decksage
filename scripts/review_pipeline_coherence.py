#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Review entire pipeline for coherence.

Checks:
1. S3 usage consistency
2. Dataset path consistency
3. Training script data dependencies
4. Evaluation script data dependencies
5. Path usage patterns
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def check_s3_consistency() -> dict[str, Any]:
    """Check S3 bucket usage consistency."""
    issues = []
    
    # Expected bucket
    expected_bucket = "s3://games-collections"
    
    # Find all S3 references
    s3_refs = []
    for path in Path(".").rglob("*.{py,sh,go,md,yml,yaml}".replace("{", "").replace("}", "")):
        if path.is_file() and not any(x in str(path) for x in [".git", "node_modules", "__pycache__"]):
            try:
                content = path.read_text()
                matches = re.findall(r's3://[^\s"\'`]+', content)
                for match in matches:
                    if match not in s3_refs:
                        s3_refs.append((match, path))
            except Exception:
                pass
    
    # Check consistency
    for s3_path, file_path in s3_refs:
        if expected_bucket not in s3_path:
            issues.append(f"Inconsistent bucket in {file_path}: {s3_path}")
    
    return {
        "expected_bucket": expected_bucket,
        "s3_references": len(s3_refs),
        "issues": issues,
    }


def check_dataset_paths() -> dict[str, Any]:
    """Check dataset path consistency."""
    issues = []
    recommendations = []
    
    # Expected paths from paths.py
    expected_paths = {
        "pairs_large": "data/processed/pairs_large.csv",
        "decks_all_unified": "data/processed/decks_all_unified.jsonl",
        "test_magic": "experiments/test_set_canonical_magic.json",
        "test_pokemon": "experiments/test_set_canonical_pokemon.json",
        "test_yugioh": "experiments/test_set_canonical_yugioh.json",
    }
    
    # Check if paths exist
    missing = []
    for name, path in expected_paths.items():
        if not Path(path).exists():
            missing.append((name, path))
    
    # Check for hardcoded paths in scripts
    hardcoded_paths = defaultdict(list)
    for script in Path("src/ml/scripts").glob("*.py"):
        try:
            content = script.read_text()
            for name, expected_path in expected_paths.items():
                # Look for hardcoded paths (not using PATHS)
                if expected_path in content and "PATHS." not in content:
                    hardcoded_paths[name].append(script.name)
        except Exception:
            pass
    
    if missing:
        issues.append(f"Missing expected paths: {[p for _, p in missing]}")
    
    if hardcoded_paths:
        recommendations.append("Consider using PATHS from paths.py instead of hardcoded paths")
    
    return {
        "expected_paths": expected_paths,
        "missing": missing,
        "hardcoded_usage": dict(hardcoded_paths),
        "issues": issues,
        "recommendations": recommendations,
    }


def check_training_scripts() -> dict[str, Any]:
    """Check training script data dependencies."""
    training_scripts = list(Path("src/ml/scripts").glob("*train*.py"))
    
    dependencies = defaultdict(set)
    
    for script in training_scripts:
        try:
            content = script.read_text()
            
            # Check for data dependencies
            if "pairs_large.csv" in content:
                dependencies["pairs_large"].add(script.name)
            if "pairs_multi_game.csv" in content:
                dependencies["pairs_multi_game"].add(script.name)
            if "decks_all" in content:
                dependencies["decks_all"].add(script.name)
            if "decks_with_metadata" in content:
                dependencies["decks_with_metadata"].add(script.name)
            
            # Check for S3 usage
            if "s3://" in content:
                dependencies["s3"].add(script.name)
        except Exception:
            pass
    
    return {
        "training_scripts": len(training_scripts),
        "dependencies": {k: list(v) for k, v in dependencies.items()},
    }


def check_evaluation_scripts() -> dict[str, Any]:
    """Check evaluation script data dependencies."""
    eval_scripts = list(Path("src/ml/scripts").glob("*eval*.py"))
    
    test_set_usage = defaultdict(set)
    embedding_usage = defaultdict(set)
    
    for script in eval_scripts:
        try:
            content = script.read_text()
            
            # Check test set usage
            if "test_set_canonical" in content:
                test_set_usage["canonical"].add(script.name)
            if "test_set_expanded" in content:
                test_set_usage["expanded"].add(script.name)
            if "ground_truth" in content:
                test_set_usage["ground_truth"].add(script.name)
            
            # Check embedding usage
            if "production.wv" in content:
                embedding_usage["production"].add(script.name)
            if "trained_validated.wv" in content:
                embedding_usage["trained_validated"].add(script.name)
        except Exception:
            pass
    
    return {
        "eval_scripts": len(eval_scripts),
        "test_set_usage": {k: list(v) for k, v in test_set_usage.items()},
        "embedding_usage": {k: list(v) for k, v in embedding_usage.items()},
    }


def main() -> int:
    """Review pipeline coherence."""
    print("=" * 70)
    print("PIPELINE COHERENCE REVIEW")
    print("=" * 70)
    
    # 1. S3 consistency
    print("\n1. S3 USAGE")
    print("-" * 70)
    s3_check = check_s3_consistency()
    print(f"Expected bucket: {s3_check['expected_bucket']}")
    print(f"S3 references found: {s3_check['s3_references']}")
    if s3_check['issues']:
        print("Issues:")
        for issue in s3_check['issues']:
            print(f"  ⚠️  {issue}")
    else:
        print("  ✅ S3 usage consistent")
    
    # 2. Dataset paths
    print("\n2. DATASET PATHS")
    print("-" * 70)
    paths_check = check_dataset_paths()
    print(f"Expected paths: {len(paths_check['expected_paths'])}")
    if paths_check['missing']:
        print("Missing paths:")
        for name, path in paths_check['missing']:
            print(f"  ❌ {name}: {path}")
    else:
        print("  ✅ All expected paths exist")
    
    if paths_check['hardcoded_usage']:
        print("Hardcoded path usage (consider using PATHS):")
        for path, scripts in paths_check['hardcoded_usage'].items():
            print(f"  ⚠️  {path}: {len(scripts)} scripts")
    
    # 3. Training scripts
    print("\n3. TRAINING SCRIPTS")
    print("-" * 70)
    training_check = check_training_scripts()
    print(f"Training scripts: {training_check['training_scripts']}")
    print("Data dependencies:")
    for dep, scripts in training_check['dependencies'].items():
        print(f"  {dep}: {len(scripts)} scripts")
    
    # 4. Evaluation scripts
    print("\n4. EVALUATION SCRIPTS")
    print("-" * 70)
    eval_check = check_evaluation_scripts()
    print(f"Evaluation scripts: {eval_check['eval_scripts']}")
    print("Test set usage:")
    for test_set, scripts in eval_check['test_set_usage'].items():
        print(f"  {test_set}: {len(scripts)} scripts")
    print("Embedding usage:")
    for emb, scripts in eval_check['embedding_usage'].items():
        print(f"  {emb}: {len(scripts)} scripts")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    total_issues = (
        len(s3_check['issues']) +
        len(paths_check['missing']) +
        len(paths_check['hardcoded_usage'])
    )
    
    if total_issues == 0:
        print("✅ Pipeline is coherent!")
    else:
        print(f"⚠️  Found {total_issues} potential issues")
        print("\nRecommendations:")
        for rec in paths_check['recommendations']:
            print(f"  - {rec}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

