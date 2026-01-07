#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sqlite3",
# ]
# ///
"""
Consolidate old evaluation_registry.db with new evaluation_logs system.

Reads from experiments/evaluation_registry.db and migrates records to
the new unified evaluation logging system.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

from ml.utils.evaluation_logger import log_evaluation_run


def read_old_registry(db_path: Path) -> list[dict[str, Any]]:
    """Read evaluation records from old registry database."""
    if not db_path.exists():
        return []
    
    records = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Try to read from evaluations table (new schema)
        try:
            cursor.execute("SELECT * FROM evaluations")
            rows = cursor.fetchall()
            
            for row in rows:
                record = dict(row)
                # Parse JSON fields
                if "metrics" in record and record["metrics"]:
                    try:
                        record["metrics"] = json.loads(record["metrics"])
                    except:
                        record["metrics"] = {}
                
                if "metadata" in record and record["metadata"]:
                    try:
                        record["metadata"] = json.loads(record["metadata"])
                    except:
                        record["metadata"] = {}
                
                records.append(record)
        except sqlite3.OperationalError:
            # Table doesn't exist or different schema
            pass
        
        conn.close()
    except Exception as e:
        print(f"Warning: Failed to read old registry: {e}")
    
    return records


def migrate_registry_record(record: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    """Migrate a single registry record to new system."""
    # Extract information (handle both old and new schema)
    model_type = record.get("model_type") or record.get("model_type", "unknown")
    model_version = record.get("model_version") or record.get("version", "unknown")
    timestamp = record.get("timestamp") or record.get("created_at")
    
    # Extract metrics
    metrics = record.get("metrics", {})
    if isinstance(metrics, str):
        try:
            metrics = json.loads(metrics)
        except:
            metrics = {}
    
    # Extract full_results if available (may contain metrics)
    full_results = record.get("full_results", {})
    if isinstance(full_results, str):
        try:
            full_results = json.loads(full_results)
        except:
            full_results = {}
    
    # Merge metrics from full_results if metrics is empty
    if not metrics and full_results:
        # Try to extract metrics from full_results
        if "p_at_k" in full_results or "p_at_10" in full_results:
            metrics = {k: v for k, v in full_results.items() if isinstance(v, (int, float))}
    
    # Extract metadata
    metadata = record.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except:
            metadata = {}
    
    # Build config
    config = {
        "model_type": model_type,
        "model_version": model_version,
        "model_path": record.get("model_path"),
    }
    config.update(metadata)
    
    # Create evaluation type
    eval_type = f"{model_type}_evaluation"
    
    # Create method name
    method = f"{model_type}_{model_version}"
    
    # Create notes
    notes = f"Migrated from evaluation_registry.db"
    if record.get("is_production"):
        notes += " (production model)"
    
    if dry_run:
        return {
            "status": "dry_run",
            "model_type": model_type,
            "model_version": model_version,
            "metrics": metrics or {},
        }
    
    # Log to new system
    try:
        run_id = log_evaluation_run(
            evaluation_type=eval_type,
            method=method,
            metrics=metrics,
            test_set_path=record.get("test_set_path"),
            num_queries=None,  # May not be available in old format
            config=config,
            notes=notes,
        )
        return {"status": "success", "run_id": run_id, "model": f"{model_type} v{model_version}"}
    except Exception as e:
        return {"status": "error", "error": str(e), "model": f"{model_type} v{model_version}"}


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Consolidate evaluation registries")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually migrating",
    )
    parser.add_argument(
        "--old-registry",
        type=str,
        default="experiments/evaluation_registry.db",
        help="Path to old registry database",
    )
    
    args = parser.parse_args()
    
    old_registry_path = Path(args.old_registry)
    
    print(f"{'='*80}")
    print("Consolidation of Evaluation Registries")
    print(f"{'='*80}")
    print(f"Old registry: {old_registry_path}")
    if args.dry_run:
        print("Mode: DRY RUN (no changes will be made)")
    print("")
    
    if not old_registry_path.exists():
        print(f"Old registry not found: {old_registry_path}")
        print("Nothing to migrate.")
        return 0
    
    # Read old registry
    records = read_old_registry(old_registry_path)
    
    if not records:
        print("No records found in old registry.")
        return 0
    
    print(f"Found {len(records)} records in old registry")
    print("")
    
    results = {
        "success": [],
        "error": [],
        "dry_run": [],
    }
    
    for record in records:
        result = migrate_registry_record(record, dry_run=args.dry_run)
        status = result.get("status")
        
        if status == "success":
            results["success"].append(result)
            model_str = result.get('model', f"{result.get('model_type', 'unknown')} v{result.get('model_version', 'unknown')}")
            print(f"✓ Migrated: {model_str} -> {result['run_id']}")
        elif status == "dry_run":
            results["dry_run"].append(result)
            model_str = f"{result.get('model_type', 'unknown')} v{result.get('model_version', 'unknown')}"
            print(f"  Would migrate: {model_str}")
            print(f"    Metrics: {list(result.get('metrics', {}).keys())}")
        elif status == "error":
            results["error"].append(result)
            model_str = result.get('model', f"{result.get('model_type', 'unknown')} v{result.get('model_version', 'unknown')}")
            print(f"✗ Error: {model_str} - {result.get('error', 'Unknown error')}")
    
    print("")
    print(f"{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    print(f"Total records: {len(records)}")
    print(f"Success: {len(results['success'])}")
    print(f"Errors: {len(results['error'])}")
    if args.dry_run:
        print(f"Would migrate: {len(results['dry_run'])}")
    
    return 0 if len(results["error"]) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

