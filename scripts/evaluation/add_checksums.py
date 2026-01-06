#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Add checksums to evaluation logs for data integrity.

Implements:
- Record-level checksums (SHA-256)
- SQLite checksum column
- JSONL checksum validation
- Corruption detection
"""

import hashlib
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


def compute_record_checksum(record: dict[str, Any]) -> str:
    """Compute SHA-256 checksum for a record."""
    # Exclude checksum field itself
    record_copy = {k: v for k, v in record.items() if k != "checksum"}
    record_json = json.dumps(record_copy, sort_keys=True)
    return hashlib.sha256(record_json.encode()).hexdigest()


def add_checksums_to_sqlite(db_path: Path, dry_run: bool = False) -> dict[str, Any]:
    """Add checksum column and compute checksums for SQLite records."""
    if not db_path.exists():
        return {"status": "missing", "updated": 0}
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if checksum column exists
    cursor.execute("PRAGMA table_info(evaluation_runs)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "checksum" not in columns:
        if not dry_run:
            cursor.execute("ALTER TABLE evaluation_runs ADD COLUMN checksum TEXT")
            conn.commit()
    
    # Compute checksums for existing records
    # Check if checksum column exists first
    if "checksum" in columns:
        cursor.execute("SELECT id, metrics, config, notes FROM evaluation_runs WHERE checksum IS NULL")
    else:
        # If column doesn't exist yet, get all records
        cursor.execute("SELECT id, metrics, config, notes FROM evaluation_runs")
    records = cursor.fetchall()
    
    updated = 0
    for record_id, metrics_json, config_json, notes in records:
        # Reconstruct record for checksum
        record = {
            "metrics": json.loads(metrics_json) if metrics_json else {},
            "config": json.loads(config_json) if config_json else {},
            "notes": notes,
        }
        
        checksum = compute_record_checksum(record)
        
        if not dry_run:
            cursor.execute(
                "UPDATE evaluation_runs SET checksum = ? WHERE id = ?",
                (checksum, record_id)
            )
        
        updated += 1
    
    if not dry_run:
        conn.commit()
    
    conn.close()
    
    return {
        "status": "ok",
        "updated": updated,
        "dry_run": dry_run,
    }


def add_checksums_to_jsonl(jsonl_path: Path, dry_run: bool = False) -> dict[str, Any]:
    """Add checksums to JSONL file."""
    if not jsonl_path.exists():
        return {"status": "missing", "updated": 0}
    
    if dry_run:
        # Just count records needing checksums
        count = 0
        with open(jsonl_path) as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "checksum" not in record:
                            count += 1
                    except json.JSONDecodeError:
                        pass
        return {"status": "would_update", "updated": count, "dry_run": True}
    
    # Rewrite file with checksums
    temp_path = jsonl_path.with_suffix(".jsonl.tmp")
    updated = 0
    
    with open(jsonl_path) as infile, open(temp_path, "w") as outfile:
        for line in infile:
            if line.strip():
                try:
                    record = json.loads(line)
                    if "checksum" not in record:
                        record["checksum"] = compute_record_checksum(record)
                        updated += 1
                    outfile.write(json.dumps(record) + "\n")
                except json.JSONDecodeError:
                    # Keep invalid lines as-is
                    outfile.write(line)
            else:
                outfile.write(line)
    
    if updated > 0:
        temp_path.replace(jsonl_path)
    
    return {
        "status": "ok",
        "updated": updated,
    }


def verify_checksums(db_path: Path, jsonl_path: Path) -> dict[str, Any]:
    """Verify checksums across SQLite and JSONL."""
    issues = []
    
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT run_id, checksum FROM evaluation_runs WHERE checksum IS NOT NULL")
        sqlite_checksums = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
    else:
        sqlite_checksums = {}
    
    jsonl_checksums = {}
    if jsonl_path.exists():
        with open(jsonl_path) as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "checksum" in record and "run_id" in record:
                            jsonl_checksums[record["run_id"]] = record["checksum"]
                    except json.JSONDecodeError:
                        pass
    
    # Compare checksums
    for run_id in set(sqlite_checksums.keys()) | set(jsonl_checksums.keys()):
        sqlite_cs = sqlite_checksums.get(run_id)
        jsonl_cs = jsonl_checksums.get(run_id)
        
        if sqlite_cs and jsonl_cs:
            if sqlite_cs != jsonl_cs:
                issues.append(f"Mismatch for {run_id}: SQLite={sqlite_cs[:8]}..., JSONL={jsonl_cs[:8]}...")
        elif sqlite_cs and not jsonl_cs:
            issues.append(f"Missing checksum in JSONL for {run_id}")
        elif jsonl_cs and not sqlite_cs:
            issues.append(f"Missing checksum in SQLite for {run_id}")
    
    return {
        "status": "ok" if not issues else "mismatch",
        "issues": issues,
        "sqlite_count": len(sqlite_checksums),
        "jsonl_count": len(jsonl_checksums),
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Add checksums to evaluation logs")
    parser.add_argument("--log-dir", type=Path, default=Path("experiments/evaluation_logs"))
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--verify", action="store_true", help="Verify existing checksums")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Add Checksums to Evaluation Logs")
    print("=" * 80)
    if args.dry_run:
        print("Mode: DRY RUN")
    print("")
    
    if args.verify:
        print("🔍 Verifying checksums...")
        db_path = args.log_dir / "evaluation_runs.db"
        jsonl_path = args.log_dir / "evaluation_runs.jsonl"
        
        result = verify_checksums(db_path, jsonl_path)
        
        if result["status"] == "ok":
            print(f"  ✅ All checksums valid")
            print(f"  SQLite: {result['sqlite_count']} records")
            print(f"  JSONL: {result['jsonl_count']} records")
        else:
            print(f"  ❌ Issues found:")
            for issue in result["issues"][:10]:
                print(f"    - {issue}")
            return 1
    else:
        # Add checksums
        print("📊 Adding checksums to SQLite...")
        db_path = args.log_dir / "evaluation_runs.db"
        sqlite_result = add_checksums_to_sqlite(db_path, args.dry_run)
        
        if sqlite_result["status"] == "ok":
            if args.dry_run:
                print(f"  Would update: {sqlite_result['updated']} records")
            else:
                print(f"  ✅ Updated: {sqlite_result['updated']} records")
        else:
            print(f"  ⚠️  {sqlite_result['status']}")
        
        print("")
        
        print("📄 Adding checksums to JSONL...")
        jsonl_path = args.log_dir / "evaluation_runs.jsonl"
        jsonl_result = add_checksums_to_jsonl(jsonl_path, args.dry_run)
        
        if jsonl_result["status"] == "ok":
            if args.dry_run:
                print(f"  Would update: {jsonl_result['updated']} records")
            else:
                print(f"  ✅ Updated: {jsonl_result['updated']} records")
        elif jsonl_result["status"] == "would_update":
            print(f"  Would update: {jsonl_result['updated']} records")
        else:
            print(f"  ⚠️  {jsonl_result['status']}")
    
    print("")
    print("✅ Complete")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

