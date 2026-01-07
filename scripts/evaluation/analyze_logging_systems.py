#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Analyze all evaluation logging systems and identify integration opportunities.

Checks for:
- Duplicate logging mechanisms
- Integration opportunities
- Cleanup needs
- System consolidation
"""

import json
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()


def analyze_systems():
    """Analyze all logging systems."""
    results = {
        "systems": {},
        "duplicates": [],
        "integration_opportunities": [],
        "cleanup_needed": [],
    }
    
    # 1. New evaluation logger
    new_db = Path("experiments/evaluation_logs/evaluation_runs.db")
    if new_db.exists():
        conn = sqlite3.connect(new_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM evaluation_runs")
        count = cursor.fetchone()[0]
        conn.close()
        results["systems"]["evaluation_logger"] = {
            "type": "SQLite + JSONL + JSON",
            "location": "experiments/evaluation_logs/",
            "records": count,
            "purpose": "Unified evaluation run tracking",
        }
    
    # 2. Old evaluation registry
    old_db = Path("experiments/evaluation_registry.db")
    if old_db.exists():
        conn = sqlite3.connect(old_db)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM evaluations")
            count = cursor.fetchone()[0]
            results["systems"]["evaluation_registry"] = {
                "type": "SQLite",
                "location": "experiments/evaluation_registry.db",
                "records": count,
                "purpose": "Model versioning + evaluation tracking",
            }
        except:
            pass
        conn.close()
    
    # 3. EXPERIMENT_LOG
    exp_log = Path("experiments/EXPERIMENT_LOG_CANONICAL.jsonl")
    if exp_log.exists():
        with open(exp_log) as f:
            lines = sum(1 for line in f if line.strip())
        results["systems"]["experiment_log"] = {
            "type": "JSONL",
            "location": str(exp_log),
            "records": lines,
            "purpose": "General experiment tracking",
        }
    
    # 4. Individual JSON files
    eval_results = Path("experiments/evaluation_results")
    if eval_results.exists():
        json_files = list(eval_results.glob("*.json"))
        results["systems"]["individual_json"] = {
            "type": "JSON files",
            "location": str(eval_results),
            "records": len(json_files),
            "purpose": "Legacy evaluation results",
        }
    
    # Check for duplicates
    if "evaluation_registry" in results["systems"] and "evaluation_logger" in results["systems"]:
        results["duplicates"].append(
            "Both evaluation_registry and evaluation_logger track evaluations"
        )
    
    # Integration opportunities
    if "experiment_log" in results["systems"]:
        results["integration_opportunities"].append(
            "EvaluationLogger could optionally write to EXPERIMENT_LOG_CANONICAL.jsonl"
        )
    
    if "evaluation_registry" in results["systems"]:
        results["integration_opportunities"].append(
            "Bridge EvaluationLogger to EvaluationRegistry for model-centric queries"
        )
    
    if "individual_json" in results["systems"] and results["systems"]["individual_json"]["records"] > 0:
        results["cleanup_needed"].append(
            f"Migrate remaining {results['systems']['individual_json']['records']} JSON files"
        )
    
    return results


def main():
    results = analyze_systems()
    
    print("=" * 80)
    print("Evaluation Logging Systems Analysis")
    print("=" * 80)
    print("")
    
    print("📊 Current Systems:")
    for name, info in results["systems"].items():
        print(f"  {name}:")
        print(f"    Type: {info['type']}")
        print(f"    Location: {info['location']}")
        print(f"    Records: {info['records']}")
        print(f"    Purpose: {info['purpose']}")
        print("")
    
    if results["duplicates"]:
        print("⚠️  Duplicate Systems:")
        for dup in results["duplicates"]:
            print(f"  - {dup}")
        print("")
    
    if results["integration_opportunities"]:
        print("🔗 Integration Opportunities:")
        for opp in results["integration_opportunities"]:
            print(f"  - {opp}")
        print("")
    
    if results["cleanup_needed"]:
        print("🧹 Cleanup Needed:")
        for cleanup in results["cleanup_needed"]:
            print(f"  - {cleanup}")
        print("")
    
    print("💡 Recommendations:")
    print("  1. Keep evaluation_logger as primary system")
    print("  2. Make EvaluationLogger optionally bridge to EvaluationRegistry")
    print("  3. Add option to write to EXPERIMENT_LOG for unified experiment tracking")
    print("  4. Complete migration of old JSON files")
    print("  5. Document when to use which system")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


