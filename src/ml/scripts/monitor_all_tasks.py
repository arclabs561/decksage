#!/usr/bin/env python3
"""
Monitor all running improvement tasks.

Shows status of:
- Label generation
- Card enrichment
- Multi-game export
- Hyperparameter search
- AWS instances
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "boto3>=1.34.0",
# ]
# ///

import json
import subprocess
import sys
from pathlib import Path

def check_labeling() -> dict:
    """Check labeling progress."""
    try:
        with open("experiments/test_set_labeled_magic.json") as f:
            data = json.load(f)
            queries = data.get("queries", data)
            total = len(queries)
            labeled = sum(
                1 for q in queries.values()
                if q.get("highly_relevant") or q.get("relevant")
            )
            return {
                "status": "running" if labeled < total else "complete",
                "progress": f"{labeled}/{total}",
                "percent": 100 * labeled / total if total > 0 else 0,
            }
    except FileNotFoundError:
        return {"status": "not_started", "progress": "0/0", "percent": 0}


def check_card_enrichment() -> dict:
    """Check card enrichment progress."""
    try:
        import csv
        
        with open("data/processed/card_attributes_enriched.csv") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            total = len(rows)
            enriched = sum(
                1 for row in rows
                if row.get("type") and row["type"].strip()
            )
            return {
                "status": "running" if enriched < total else "complete",
                "progress": f"{enriched}/{total}",
                "percent": 100 * enriched / total if total > 0 else 0,
            }
    except FileNotFoundError:
        return {"status": "not_started", "progress": "0/0", "percent": 0}


def check_multigame_export() -> dict:
    """Check multi-game export status."""
    path = Path("data/processed/pairs_multi_game.csv")
    if path.exists():
        size_mb = path.stat().st_size / (1024 * 1024)
        return {
            "status": "complete",
            "size_mb": size_mb,
            "progress": f"{size_mb:.1f} MB",
        }
    return {"status": "running", "progress": "exporting..."}


def check_hyperparameter_search() -> dict:
    """Check hyperparameter search status."""
    try:
        import boto3
        
        s3 = boto3.client("s3")
        s3.head_object(
            Bucket="games-collections",
            Key="experiments/hyperparameter_search_results.json",
        )
        return {"status": "complete", "progress": "results available"}
    except Exception:
        # Check if instance is running
        try:
            result = subprocess.run(
                ["aws", "ec2", "describe-instances",
                 "--filters", "Name=instance-state-name,Values=running",
                 "--query", "Reservations[*].Instances[*].InstanceId",
                 "--output", "text"],
                capture_output=True,
                text=True,
            )
            instances = [i.strip() for i in result.stdout.split() if i.strip()]
            if instances:
                return {
                    "status": "running",
                    "progress": f"{len(instances)} instance(s) running",
                }
        except Exception:
            pass
        
        return {"status": "unknown", "progress": "checking..."}


def check_aws_instances() -> list:
    """Check running AWS instances."""
    try:
        result = subprocess.run(
            ["aws", "ec2", "describe-instances",
             "--filters", "Name=instance-state-name,Values=running",
             "--query", "Reservations[*].Instances[*].[InstanceId,InstanceType,LaunchTime]",
             "--output", "text"],
            capture_output=True,
            text=True,
        )
        instances = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.split()
                if len(parts) >= 3:
                    instances.append({
                        "id": parts[0],
                        "type": parts[1],
                        "launched": parts[2],
                    })
        return instances
    except Exception:
        return []


def main() -> int:
    """Print status of all tasks."""
    print("=" * 70)
    print("📊 Task Status Monitor")
    print("=" * 70)
    print()
    
    # Labeling
    labeling = check_labeling()
    status_icon = "✅" if labeling["status"] == "complete" else "🔄"
    print(f"{status_icon} Labeling: {labeling['progress']} ({labeling['percent']:.1f}%)")
    
    # Card enrichment
    enrichment = check_card_enrichment()
    status_icon = "✅" if enrichment["status"] == "complete" else "🔄"
    print(f"{status_icon} Card Enrichment: {enrichment['progress']} ({enrichment['percent']:.1f}%)")
    
    # Multi-game export
    multigame = check_multigame_export()
    status_icon = "✅" if multigame["status"] == "complete" else "🔄"
    print(f"{status_icon} Multi-Game Export: {multigame['progress']}")
    
    # Hyperparameter search
    hyperparam = check_hyperparameter_search()
    status_icon = "✅" if hyperparam["status"] == "complete" else "🔄"
    print(f"{status_icon} Hyperparameter Search: {hyperparam['progress']}")
    
    print()
    print("=" * 70)
    print("☁️  AWS Instances")
    print("=" * 70)
    
    instances = check_aws_instances()
    if instances:
        for inst in instances:
            print(f"  {inst['id']} ({inst['type']}) - Launched: {inst['launched']}")
    else:
        print("  No running instances")
    
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

