#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Migrate existing evaluation results to the new evaluation logging system.

Reads JSON files from experiments/evaluation_results/ and logs them to
the unified evaluation logging system (SQLite + JSONL).
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

from ml.utils.evaluation_logger import log_evaluation_run


def extract_metrics(data: dict) -> dict:
    """Extract metrics from various evaluation result formats."""
    metrics = {}
    
    # Direct metrics
    if "p_at_k" in data:
        metrics["p_at_k"] = data["p_at_k"]
    if "ndcg_at_k" in data:
        metrics["ndcg_at_k"] = data["ndcg_at_k"]
    if "mrr" in data:
        metrics["mrr"] = data["mrr"]
    if "recall_at_k" in data:
        metrics["recall_at_k"] = data["recall_at_k"]
    if "diversity" in data:
        metrics["diversity"] = data["diversity"]
    
    # Nested in results
    if "results" in data:
        results = data["results"]
        if "p_at_k" in results:
            metrics["p_at_k"] = results["p_at_k"]
        if "ndcg_at_k" in results:
            metrics["ndcg_at_k"] = results["ndcg_at_k"]
        if "mrr" in results:
            metrics["mrr"] = results["mrr"]
        if "recall_at_k" in results:
            metrics["recall_at_k"] = results["recall_at_k"]
    
    # Legacy format (p10, p_at_10, etc.)
    if "p10" in data:
        metrics["p_at_k"] = data["p10"]
    if "p_at_10" in data:
        metrics["p_at_k"] = data["p_at_10"]
    
    return metrics


def extract_method(filename: str, data: dict) -> str:
    """Extract method name from filename or data."""
    # Try data first
    if "method" in data:
        return data["method"]
    
    # Try results.method
    if "results" in data and "method" in data["results"]:
        return data["results"]["method"]
    
    # Extract from filename
    # Format: {type}_evaluation_v{version}.json
    parts = filename.replace(".json", "").split("_")
    if "evaluation" in parts:
        idx = parts.index("evaluation")
        if idx > 0:
            return "_".join(parts[:idx])
    
    return "unknown"


def extract_evaluation_type(filename: str, data: dict) -> str:
    """Extract evaluation type from filename or data."""
    # Try data
    if "evaluation_type" in data:
        return data["evaluation_type"]
    
    # Extract from filename
    if "hybrid" in filename.lower():
        return "hybrid_evaluation"
    elif "downstream" in filename.lower():
        return "downstream_evaluation"
    elif "compat" in filename.lower() or "compatibility" in filename.lower():
        return "compatibility_evaluation"
    elif "verification" in filename.lower():
        return "verification_evaluation"
    else:
        return "legacy_evaluation"


def migrate_file(file_path: Path, dry_run: bool = False) -> dict:
    """Migrate a single evaluation result file."""
    try:
        with open(file_path) as f:
            data = json.load(f)
    except Exception as e:
        return {"status": "error", "error": str(e)}
    
    # Extract information
    method = extract_method(file_path.name, data)
    eval_type = extract_evaluation_type(file_path.name, data)
    metrics = extract_metrics(data)
    
    # Extract config
    config = {}
    if "config" in data:
        config = data["config"]
    elif "weights" in data:
        config["weights"] = data["weights"]
    if "top_k" in data:
        config["top_k"] = data["top_k"]
    
    # Extract test set path
    test_set_path = data.get("test_set_path") or data.get("test_set")
    
    # Extract num queries
    num_queries = data.get("num_queries") or data.get("results", {}).get("num_queries")
    
    # Create notes
    notes = f"Migrated from {file_path.name}"
    if "timestamp" in data:
        notes += f" (original: {data['timestamp']})"
    
    if dry_run:
        return {
            "status": "dry_run",
            "file": file_path.name,
            "method": method,
            "eval_type": eval_type,
            "metrics": metrics,
            "num_queries": num_queries,
        }
    
    # Log to new system
    try:
        run_id = log_evaluation_run(
            evaluation_type=eval_type,
            method=method,
            metrics=metrics,
            test_set_path=test_set_path,
            num_queries=num_queries,
            config=config,
            notes=notes,
        )
        return {"status": "success", "run_id": run_id, "file": file_path.name}
    except Exception as e:
        return {"status": "error", "error": str(e), "file": file_path.name}


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate existing evaluation results")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually migrating",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of files to migrate",
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.json",
        help="File pattern to match (default: *.json)",
    )
    
    args = parser.parse_args()
    
    eval_dir = Path("experiments/evaluation_results")
    if not eval_dir.exists():
        print(f"Error: {eval_dir} does not exist")
        return 1
    
    json_files = list(eval_dir.glob(args.pattern))
    if args.limit:
        json_files = json_files[:args.limit]
    
    print(f"{'='*80}")
    print("Migration of Existing Evaluation Results")
    print(f"{'='*80}")
    print(f"Source: {eval_dir}")
    print(f"Files found: {len(json_files)}")
    if args.dry_run:
        print("Mode: DRY RUN (no changes will be made)")
    print("")
    
    results = {
        "success": [],
        "error": [],
        "dry_run": [],
    }
    
    for file_path in sorted(json_files):
        result = migrate_file(file_path, dry_run=args.dry_run)
        status = result.get("status")
        
        if status == "success":
            results["success"].append(result)
            print(f"✓ Migrated: {file_path.name} -> {result['run_id']}")
        elif status == "dry_run":
            results["dry_run"].append(result)
            print(f"  Would migrate: {file_path.name}")
            print(f"    Method: {result['method']}, Type: {result['eval_type']}")
            print(f"    Metrics: {list(result['metrics'].keys())}")
        elif status == "error":
            results["error"].append(result)
            print(f"✗ Error: {file_path.name} - {result.get('error', 'Unknown error')}")
    
    print("")
    print(f"{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    print(f"Total files: {len(json_files)}")
    print(f"Success: {len(results['success'])}")
    print(f"Errors: {len(results['error'])}")
    if args.dry_run:
        print(f"Would migrate: {len(results['dry_run'])}")
    
    return 0 if len(results["error"]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


