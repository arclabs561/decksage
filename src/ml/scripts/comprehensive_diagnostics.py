#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "boto3>=1.34.0",
# ]
# ///
"""
Comprehensive diagnostics for all running tasks.

Based on best practices:
- Multi-dimensional monitoring (progress, errors, resources)
- Checkpoint validation
- Health checks
- Progress tracking with ETAs
"""

from __future__ import annotations

import csv
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_process_health(process_name: str) -> dict[str, Any]:
    """Check if a process is running and healthy."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", process_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        pids = result.stdout.strip().split("\n")
        pids = [p for p in pids if p]
        
        if not pids:
            return {
                "running": False,
                "pids": [],
                "count": 0,
            }
        
        # Check if processes are actually running
        running_pids = []
        for pid in pids:
            try:
                subprocess.run(["ps", "-p", pid], capture_output=True, check=True)
                running_pids.append(pid)
            except subprocess.CalledProcessError:
                pass
        
        return {
            "running": len(running_pids) > 0,
            "pids": running_pids,
            "count": len(running_pids),
        }
    except Exception as e:
        return {
            "running": False,
            "error": str(e),
            "pids": [],
            "count": 0,
        }


def check_card_enrichment() -> dict[str, Any]:
    """Comprehensive card enrichment diagnostics."""
    csv_path = Path("data/processed/card_attributes_enriched.csv")
    
    if not csv_path.exists():
        return {
            "status": "not_started",
            "progress": "0/0",
            "percent": 0.0,
            "file_exists": False,
        }
    
    try:
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            total = len(rows)
            
            enriched = sum(
                1 for row in rows
                if row.get("type")
                and str(row.get("type", "")).strip()
                and str(row.get("type", "")) != "nan"
            )
            
            failed = total - enriched
            percent = 100 * enriched / total if total > 0 else 0
            
            # Check process
            process = check_process_health("enrich.*scryfall.*optimized")
            
            # Estimate ETA
            # Assuming ~50 cards/minute based on logs
            remaining = total - enriched
            eta_minutes = remaining / 50 if remaining > 0 else 0
            eta = timedelta(minutes=eta_minutes)
            
            return {
                "status": "complete" if enriched == total else ("running" if process["running"] else "stopped"),
                "progress": f"{enriched}/{total}",
                "percent": percent,
                "enriched": enriched,
                "failed": failed,
                "remaining": remaining,
                "file_exists": True,
                "file_size_mb": csv_path.stat().st_size / (1024 * 1024),
                "process_running": process["running"],
                "process_count": process["count"],
                "eta_minutes": eta_minutes,
                "eta_human": str(eta).split(".")[0] if eta_minutes > 0 else "N/A",
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "file_exists": csv_path.exists(),
        }


def check_labeling() -> dict[str, Any]:
    """Comprehensive labeling diagnostics."""
    expanded_path = Path("experiments/test_set_expanded_magic.json")
    labeled_path = Path("experiments/test_set_labeled_magic.json")
    
    if not expanded_path.exists():
        return {
            "status": "not_started",
            "progress": "0/0",
            "percent": 0.0,
        }
    
    try:
        with open(expanded_path) as f:
            expanded = json.load(f)
        
        expanded_queries = expanded.get("queries", expanded)
        total = len(expanded_queries)
        
        labeled_count = 0
        missing = []
        failed = []
        
        if labeled_path.exists():
            with open(labeled_path) as f:
                labeled = json.load(f)
            
            labeled_queries = labeled.get("queries", labeled)
            
            for q_name in expanded_queries:
                if q_name in labeled_queries:
                    data = labeled_queries[q_name]
                    if isinstance(data, dict) and (data.get("highly_relevant") or data.get("relevant")):
                        labeled_count += 1
                    else:
                        failed.append(q_name)
                else:
                    missing.append(q_name)
        else:
            missing = list(expanded_queries.keys())
        
        percent = 100 * labeled_count / total if total > 0 else 0
        
        # Check process
        process = check_process_health("generate_labels.*optimized")
        
        return {
            "status": "complete" if labeled_count == total else ("running" if process["running"] else "stopped"),
            "progress": f"{labeled_count}/{total}",
            "percent": percent,
            "labeled": labeled_count,
            "missing": len(missing),
            "failed": len(failed),
            "total": total,
            "process_running": process["running"],
            "process_count": process["count"],
            "sample_missing": missing[:5],
            "sample_failed": failed[:5],
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


def check_hyperparameter_search() -> dict[str, Any]:
    """Check hyperparameter search status."""
    log_path = Path("/tmp/hyperparam_search.log")
    
    status = "not_started"
    instance_id = None
    error = None
    
    # Check if process is running
    process = check_process_health("hyperparam|runctl.*aws.*train")
    
    if log_path.exists():
        try:
            with open(log_path) as f:
                content = f.read()
                lines = content.split("\n")
                
            if "Instance created:" in content:
                # Extract instance ID
                for line in lines:
                    if "Instance created:" in line:
                        parts = line.split()
                        for part in parts:
                            if part.startswith("i-"):
                                instance_id = part
                                break
                
                if "error:" in content.lower() or "failed" in content.lower():
                    status = "error"
                    # Extract error
                    for line in lines[-10:]:
                        if "error:" in line.lower() or "failed" in line.lower():
                            error = line.strip()
                            break
                elif "Training started" in content or "monitor" in content.lower():
                    status = "running"
                elif "Starting hyperparameter search" in content:
                    status = "starting"
                elif instance_id:
                    status = "starting"  # Instance created but training not started yet
        except Exception as e:
            error = str(e)
    
    # If process is running, status should reflect that
    if process["running"] and status == "not_started":
        status = "running"
    
    # Check AWS instances
    aws_instances = []
    if HAS_BOTO3:
        try:
            ec2 = boto3.client("ec2")
            response = ec2.describe_instances(
                Filters=[{"Name": "instance-state-name", "Values": ["running", "pending"]}]
            )
            for reservation in response.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    aws_instances.append({
                        "id": instance["InstanceId"],
                        "type": instance["InstanceType"],
                        "state": instance["State"]["Name"],
                    })
        except Exception:
            pass
    
    # Check S3 for results
    results_exist = False
    if HAS_BOTO3:
        try:
            s3 = boto3.client("s3")
            s3.head_object(
                Bucket="games-collections",
                Key="experiments/hyperparameter_results.json"
            )
            results_exist = True
            status = "complete"
        except Exception:
            pass
    
    return {
        "status": status,
        "instance_id": instance_id,
        "error": error,
        "log_exists": log_path.exists(),
        "aws_instances": aws_instances,
        "results_exist": results_exist,
    }


def check_s3_backup() -> dict[str, Any]:
    """Check S3 backup status."""
    log_path = Path("/tmp/s3_backup.log")
    
    status = "not_started"
    progress = []
    
    if log_path.exists():
        try:
            with open(log_path) as f:
                lines = f.readlines()
                content = "\n".join(lines)
                
            if "Sync complete" in content:
                status = "complete"
            elif "Syncing" in content:
                status = "running"
            
            # Extract progress
            for line in lines[-20:]:
                if "Syncing" in line or "Done" in line or "upload" in line.lower():
                    progress.append(line.strip())
        except Exception:
            pass
    
    process = check_process_health("sync_to_s3")
    
    return {
        "status": status,
        "process_running": process["running"],
        "log_exists": log_path.exists(),
        "recent_activity": progress[-5:] if progress else [],
    }


def check_data_files() -> dict[str, Any]:
    """Check critical data files."""
    files = {
        "multi_game_export": Path("data/processed/pairs_multi_game.csv"),
        "card_attributes_enriched": Path("data/processed/card_attributes_enriched.csv"),
        "graph_enriched": Path("data/graphs/pairs_enriched.edg"),
        "node_features": Path("data/graphs/node_features.json"),
        "test_set_expanded": Path("experiments/test_set_expanded_magic.json"),
        "test_set_labeled": Path("experiments/test_set_labeled_magic.json"),
    }
    
    result = {}
    for name, path in files.items():
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            result[name] = {
                "exists": True,
                "size_mb": round(size_mb, 2),
                "size_human": f"{size_mb:.1f}MB" if size_mb < 1024 else f"{size_mb/1024:.1f}GB",
            }
        else:
            result[name] = {
                "exists": False,
                "size_mb": 0,
            }
    
    return result


def main() -> int:
    """Run comprehensive diagnostics."""
    print("=" * 80)
    print("🔍 COMPREHENSIVE SYSTEM DIAGNOSTICS")
    print("=" * 80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Card Enrichment
    print("📊 CARD ENRICHMENT")
    print("-" * 80)
    enrichment = check_card_enrichment()
    if enrichment.get("status") == "error":
        print(f"  ❌ Error: {enrichment.get('error')}")
    else:
        status_icon = "✅" if enrichment["status"] == "complete" else ("🔄" if enrichment["status"] == "running" else "⏸️")
        print(f"  {status_icon} Status: {enrichment['status'].upper()}")
        print(f"     Progress: {enrichment['progress']} ({enrichment['percent']:.2f}%)")
        print(f"     Enriched: {enrichment.get('enriched', 0):,}")
        print(f"     Remaining: {enrichment.get('remaining', 0):,}")
        if enrichment.get("eta_minutes", 0) > 0:
            print(f"     ETA: {enrichment.get('eta_human', 'N/A')}")
        print(f"     Process: {'✅ Running' if enrichment.get('process_running') else '❌ Stopped'} ({enrichment.get('process_count', 0)} processes)")
        if enrichment.get("file_size_mb"):
            print(f"     File Size: {enrichment.get('file_size_mb', 0):.1f} MB")
    print()
    
    # Labeling
    print("🏷️  TEST SET LABELING")
    print("-" * 80)
    labeling = check_labeling()
    if labeling.get("status") == "error":
        print(f"  ❌ Error: {labeling.get('error')}")
    else:
        status_icon = "✅" if labeling["status"] == "complete" else ("🔄" if labeling["status"] == "running" else "⏸️")
        print(f"  {status_icon} Status: {labeling['status'].upper()}")
        print(f"     Progress: {labeling['progress']} ({labeling['percent']:.1f}%)")
        print(f"     Labeled: {labeling.get('labeled', 0)}")
        print(f"     Missing: {labeling.get('missing', 0)}")
        print(f"     Failed: {labeling.get('failed', 0)}")
        print(f"     Process: {'✅ Running' if labeling.get('process_running') else '❌ Stopped'} ({labeling.get('process_count', 0)} processes)")
        if labeling.get("sample_missing"):
            print(f"     Sample Missing: {', '.join(labeling['sample_missing'][:3])}")
    print()
    
    # Hyperparameter Search
    print("🔬 HYPERPARAMETER SEARCH")
    print("-" * 80)
    hyperparam = check_hyperparameter_search()
    status_icon = "✅" if hyperparam["status"] == "complete" else ("🔄" if hyperparam["status"] == "running" else ("❌" if hyperparam["status"] == "error" else "⏸️"))
    print(f"  {status_icon} Status: {hyperparam['status'].upper()}")
    if hyperparam.get("instance_id"):
        print(f"     Instance: {hyperparam['instance_id']}")
    if hyperparam.get("error"):
        print(f"     Error: {hyperparam['error']}")
    if hyperparam.get("aws_instances"):
        print(f"     AWS Instances: {len(hyperparam['aws_instances'])} running")
        for inst in hyperparam["aws_instances"]:
            print(f"       - {inst['id']} ({inst['type']}) - {inst['state']}")
    if hyperparam.get("results_exist"):
        print(f"     ✅ Results available in S3")
    print()
    
    # S3 Backup
    print("☁️  S3 BACKUP")
    print("-" * 80)
    backup = check_s3_backup()
    status_icon = "✅" if backup["status"] == "complete" else ("🔄" if backup["status"] == "running" else "⏸️")
    print(f"  {status_icon} Status: {backup['status'].upper()}")
    print(f"     Process: {'✅ Running' if backup.get('process_running') else '❌ Stopped'}")
    if backup.get("recent_activity"):
        print(f"     Recent Activity:")
        for activity in backup["recent_activity"]:
            print(f"       - {activity[:70]}")
    print()
    
    # Data Files
    print("📁 DATA FILES")
    print("-" * 80)
    files = check_data_files()
    for name, info in files.items():
        icon = "✅" if info["exists"] else "❌"
        size = info.get("size_human", "N/A") if info["exists"] else "Missing"
        print(f"  {icon} {name.replace('_', ' ').title()}: {size}")
    
    # Check for hyperparameter results
    hyperparam_results = Path("experiments/hyperparameter_results.json")
    if hyperparam_results.exists():
        print(f"  ✅ Hyperparameter Results: Found locally")
    else:
        # Check S3
        if HAS_BOTO3:
            try:
                s3 = boto3.client("s3")
                s3.head_object(
                    Bucket="games-collections",
                    Key="experiments/hyperparameter_results.json"
                )
                print(f"  ✅ Hyperparameter Results: Available in S3")
            except Exception:
                print(f"  ⏳ Hyperparameter Results: Not yet available")
    print()
    
    # Summary with recommendations
    print("=" * 80)
    print("📋 SUMMARY")
    print("=" * 80)
    
    all_complete = (
        enrichment.get("status") == "complete"
        and labeling.get("status") == "complete"
        and hyperparam.get("status") == "complete"
    )
    
    if all_complete:
        print("✅ All critical tasks complete!")
    else:
        print("🔄 Tasks in progress:")
        if enrichment.get("status") != "complete":
            pct = enrichment.get('percent', 0)
            print(f"   - Card Enrichment: {pct:.1f}%")
            if pct > 90:
                print(f"     💡 Almost done! Consider retrying failed cards when complete")
        if labeling.get("status") != "complete":
            pct = labeling.get('percent', 0)
            print(f"   - Labeling: {pct:.1f}%")
            if pct < 100:
                print(f"     💡 Use fallback labeling for remaining queries")
        if hyperparam.get("status") != "complete":
            status = hyperparam.get('status', 'unknown')
            print(f"   - Hyperparameter Search: {status}")
            if status == "error":
                print(f"     💡 Check AWS permissions and instance status")
    
    # Recommendations
    print()
    print("💡 RECOMMENDATIONS:")
    if enrichment.get("status") != "complete" and enrichment.get("failed", 0) > 0:
        print(f"   - Retry failed enrichments: {enrichment.get('failed', 0)} cards")
        print(f"     Command: uv run --script src/ml/scripts/retry_failed_enrichments.py \\")
        print(f"       --input data/processed/card_attributes_enriched.csv")
    if hyperparam.get("status") == "error":
        print(f"   - Check hyperparameter search: Review logs and AWS status")
    if enrichment.get("status") == "complete" and hyperparam.get("status") == "complete":
        print(f"   - Ready to train improved embeddings!")
        print(f"     Command: just check-hyperparam && just train-aws <instance-id>")
    
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

