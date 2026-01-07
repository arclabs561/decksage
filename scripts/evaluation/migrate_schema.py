#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Migrate evaluation logs to new schema versions.

Handles:
- Adding new fields
- Updating existing records
- Backward compatibility
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

from ml.utils.evaluation_logger import SCHEMA_VERSION


def migrate_sqlite_schema(db_path: Path, target_version: int, dry_run: bool = False) -> dict[str, Any]:
    """Migrate SQLite database to target schema version."""
    changes = []
    
    if not db_path.exists():
        return {"status": "missing", "changes": []}
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current schema
    cursor.execute("PRAGMA table_info(evaluation_runs)")
    columns = {col[1]: col for col in cursor.fetchall()}
    
    # Add schema_version column if missing
    if "schema_version" not in columns:
        if not dry_run:
            cursor.execute("ALTER TABLE evaluation_runs ADD COLUMN schema_version INTEGER DEFAULT 1")
            conn.commit()
        changes.append("Added schema_version column")
    
    # Update existing records without schema_version
    cursor.execute("SELECT COUNT(*) FROM evaluation_runs WHERE schema_version IS NULL")
    null_count = cursor.fetchone()[0]
    
    if null_count > 0:
        if not dry_run:
            cursor.execute(
                "UPDATE evaluation_runs SET schema_version = ? WHERE schema_version IS NULL",
                (target_version,)
            )
            conn.commit()
        changes.append(f"Updated {null_count} records with schema_version")
    
    # Future migrations can be added here
    # Example: if target_version >= 2:
    #   - Add new columns
    #   - Transform data
    
    conn.close()
    
    return {
        "status": "migrated" if changes else "up_to_date",
        "target_version": target_version,
        "changes": changes,
    }


def migrate_jsonl_schema(jsonl_path: Path, target_version: int, dry_run: bool = False) -> dict[str, Any]:
    """Migrate JSONL file to target schema version."""
    changes = []
    
    if not jsonl_path.exists():
        return {"status": "missing", "changes": []}
    
    if dry_run:
        # Just count records needing migration
        with open(jsonl_path) as f:
            count = 0
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        if "schema_version" not in record:
                            count += 1
                    except json.JSONDecodeError:
                        pass
        
        if count > 0:
            changes.append(f"Would update {count} records with schema_version")
        
        return {
            "status": "would_migrate" if changes else "up_to_date",
            "changes": changes,
        }
    
    # Actual migration: rewrite file with schema_version
    temp_path = jsonl_path.with_suffix(".jsonl.tmp")
    updated_count = 0
    
    with open(jsonl_path) as infile, open(temp_path, "w") as outfile:
        for line in infile:
            if line.strip():
                try:
                    record = json.loads(line)
                    if "schema_version" not in record:
                        record["schema_version"] = target_version
                        updated_count += 1
                    outfile.write(json.dumps(record) + "\n")
                except json.JSONDecodeError:
                    # Keep invalid lines as-is
                    outfile.write(line)
            else:
                outfile.write(line)
    
    if updated_count > 0:
        temp_path.replace(jsonl_path)
        changes.append(f"Updated {updated_count} records with schema_version")
    
    return {
        "status": "migrated" if changes else "up_to_date",
        "target_version": target_version,
        "changes": changes,
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate evaluation logs to new schema")
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("experiments/evaluation_logs"),
        help="Directory containing evaluation logs",
    )
    parser.add_argument(
        "--target-version",
        type=int,
        default=SCHEMA_VERSION,
        help="Target schema version",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Evaluation Log Schema Migration")
    print("=" * 80)
    if args.dry_run:
        print("Mode: DRY RUN")
    print("")
    
    results = {}
    
    # Migrate SQLite
    db_path = args.log_dir / "evaluation_runs.db"
    print("📊 Migrating SQLite database...")
    sqlite_result = migrate_sqlite_schema(db_path, args.target_version, args.dry_run)
    results["sqlite"] = sqlite_result
    
    if sqlite_result["status"] == "migrated":
        print(f"  ✅ Migrated: {', '.join(sqlite_result['changes'])}")
    elif sqlite_result["status"] == "up_to_date":
        print("  ✅ Already up to date")
    elif sqlite_result["status"] == "would_migrate":
        print(f"  Would migrate: {', '.join(sqlite_result['changes'])}")
    else:
        print(f"  ⚠️  {sqlite_result['status']}")
    print("")
    
    # Migrate JSONL
    jsonl_path = args.log_dir / "evaluation_runs.jsonl"
    print("📄 Migrating JSONL file...")
    jsonl_result = migrate_jsonl_schema(jsonl_path, args.target_version, args.dry_run)
    results["jsonl"] = jsonl_result
    
    if jsonl_result["status"] == "migrated":
        print(f"  ✅ Migrated: {', '.join(jsonl_result['changes'])}")
    elif jsonl_result["status"] == "up_to_date":
        print("  ✅ Already up to date")
    elif jsonl_result["status"] == "would_migrate":
        print(f"  Would migrate: {', '.join(jsonl_result['changes'])}")
    else:
        print(f"  ⚠️  {jsonl_result['status']}")
    print("")
    
    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    
    migrated = any(r["status"] in ["migrated", "would_migrate"] for r in results.values())
    
    if migrated:
        if args.dry_run:
            print("✅ Migration would be applied (run without --dry-run to apply)")
        else:
            print("✅ Migration complete")
    else:
        print("✅ All logs already up to date")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


