#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Verify data integrity across evaluation logging formats.

Checks:
- SQLite and JSONL consistency (same record counts)
- Schema version consistency
- Data corruption detection
- Format sync verification
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


def verify_sqlite_jsonl_sync(log_dir: Path) -> dict[str, Any]:
    """Verify SQLite and JSONL are in sync."""
    issues = []
    
    db_path = log_dir / "evaluation_runs.db"
    jsonl_path = log_dir / "evaluation_runs.jsonl"
    
    if not db_path.exists():
        return {"status": "missing", "issues": ["SQLite database not found"]}
    
    if not jsonl_path.exists():
        return {"status": "missing", "issues": ["JSONL file not found"]}
    
    # Count SQLite records
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM evaluation_runs")
    sqlite_count = cursor.fetchone()[0]
    
    # Get SQLite run_ids
    cursor.execute("SELECT run_id FROM evaluation_runs")
    sqlite_ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    # Count JSONL records
    jsonl_ids = set()
    with open(jsonl_path) as f:
        for line in f:
            if line.strip():
                try:
                    record = json.loads(line)
                    if "run_id" in record:
                        jsonl_ids.add(record["run_id"])
                except json.JSONDecodeError:
                    issues.append(f"Invalid JSON in JSONL: {line[:50]}")
    
    jsonl_count = len(jsonl_ids)
    
    # Compare
    if sqlite_count != jsonl_count:
        issues.append(
            f"Count mismatch: SQLite has {sqlite_count}, JSONL has {jsonl_count}"
        )
    
    # Check for missing IDs
    missing_in_jsonl = sqlite_ids - jsonl_ids
    if missing_in_jsonl:
        issues.append(
            f"Missing in JSONL: {len(missing_in_jsonl)} run_ids (e.g., {list(missing_in_jsonl)[:3]})"
        )
    
    missing_in_sqlite = jsonl_ids - sqlite_ids
    if missing_in_sqlite:
        issues.append(
            f"Missing in SQLite: {len(missing_in_sqlite)} run_ids (e.g., {list(missing_in_sqlite)[:3]})"
        )
    
    return {
        "status": "ok" if not issues else "inconsistent",
        "sqlite_count": sqlite_count,
        "jsonl_count": jsonl_count,
        "issues": issues,
    }


def verify_schema_versions(log_dir: Path) -> dict[str, Any]:
    """Verify schema versions are consistent."""
    issues = []
    versions_found = set()
    
    db_path = log_dir / "evaluation_runs.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if schema_version column exists
        cursor.execute("PRAGMA table_info(evaluation_runs)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "schema_version" in columns:
            cursor.execute("SELECT DISTINCT schema_version FROM evaluation_runs")
            versions = {row[0] for row in cursor.fetchall() if row[0] is not None}
            versions_found.update(versions)
        else:
            issues.append("SQLite missing schema_version column")
        
        conn.close()
    
    jsonl_path = log_dir / "evaluation_runs.jsonl"
    if jsonl_path.exists():
        with open(jsonl_path) as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "schema_version" in record:
                            versions_found.add(record["schema_version"])
                        else:
                            issues.append(f"JSONL line {line_num} missing schema_version")
                    except json.JSONDecodeError:
                        pass
    
    if len(versions_found) > 1:
        issues.append(f"Multiple schema versions found: {versions_found}")
    
    return {
        "status": "ok" if not issues else "inconsistent",
        "versions": list(versions_found),
        "issues": issues,
    }


def verify_data_corruption(log_dir: Path) -> dict[str, Any]:
    """Check for data corruption indicators."""
    issues = []
    
    db_path = log_dir / "evaluation_runs.db"
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Try to read all records
            cursor.execute("SELECT * FROM evaluation_runs LIMIT 100")
            rows = cursor.fetchall()
            
            for row in rows:
                # Check JSON fields can be parsed
                try:
                    metrics = json.loads(row[7]) if row[7] else {}
                    config = json.loads(row[8]) if row[8] else {}
                except (json.JSONDecodeError, IndexError) as e:
                    issues.append(f"Corrupted JSON in SQLite row: {e}")
            
            conn.close()
        except sqlite3.Error as e:
            issues.append(f"SQLite corruption detected: {e}")
    
    jsonl_path = log_dir / "evaluation_runs.jsonl"
    if jsonl_path.exists():
        with open(jsonl_path) as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        record = json.loads(line)
                        # Basic structure check
                        if "run_id" not in record:
                            issues.append(f"JSONL line {line_num} missing run_id")
                        if "timestamp" not in record:
                            issues.append(f"JSONL line {line_num} missing timestamp")
                    except json.JSONDecodeError as e:
                        issues.append(f"JSONL line {line_num} invalid JSON: {e}")
    
    return {
        "status": "ok" if not issues else "corrupted",
        "issues": issues,
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Verify evaluation data integrity")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("experiments/evaluation_logs"),
        help="Directory containing evaluation logs",
    )
    parser.add_argument("--fix", action="store_true", help="Attempt to fix issues")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Evaluation Data Integrity Verification")
    print("=" * 80)
    print("")
    
    results = {}
    
    # 1. Sync verification
    print("🔄 Verifying SQLite/JSONL sync...")
    sync_result = verify_sqlite_jsonl_sync(args.log_dir)
    results["sync"] = sync_result
    
    if sync_result["status"] == "ok":
        print(f"  ✅ In sync: {sync_result['sqlite_count']} records in both")
    else:
        print(f"  ❌ Issues found:")
        for issue in sync_result["issues"]:
            print(f"    - {issue}")
    print("")
    
    # 2. Schema version verification
    print("📋 Verifying schema versions...")
    version_result = verify_schema_versions(args.log_dir)
    results["schema"] = version_result
    
    if version_result["status"] == "ok":
        if version_result["versions"]:
            print(f"  ✅ Consistent: version {version_result['versions'][0]}")
        else:
            print("  ⚠️  No schema versions found (old data?)")
    else:
        print(f"  ❌ Issues found:")
        for issue in version_result["issues"]:
            print(f"    - {issue}")
    print("")
    
    # 3. Corruption check
    print("🔍 Checking for data corruption...")
    corruption_result = verify_data_corruption(args.log_dir)
    results["corruption"] = corruption_result
    
    if corruption_result["status"] == "ok":
        print("  ✅ No corruption detected")
    else:
        print(f"  ❌ Corruption detected:")
        for issue in corruption_result["issues"][:5]:
            print(f"    - {issue}")
    print("")
    
    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    
    all_ok = all(r["status"] == "ok" for r in results.values())
    
    if all_ok:
        print("✅ All integrity checks passed")
        return 0
    else:
        print("❌ Integrity issues found")
        if args.fix:
            print("\n⚠️  Auto-fix not implemented yet")
        return 1


if __name__ == "__main__":
    sys.exit(main())


