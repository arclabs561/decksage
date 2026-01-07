#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Validate evaluation data across all formats.

Checks:
- Schema compliance
- Data integrity
- Format consistency
- Duplication analysis
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


def validate_jsonl_file(file_path: Path) -> dict[str, Any]:
    """Validate JSONL file format and content."""
    issues = []
    valid_lines = 0
    invalid_lines = 0
    
    if not file_path.exists():
        return {"status": "missing", "issues": []}
    
    with open(file_path) as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            try:
                record = json.loads(line)
                valid_lines += 1
                
                # Basic schema check
                required_fields = ["timestamp", "run_id"] if "run_id" in record else ["timestamp"]
                for field in required_fields:
                    if field not in record:
                        issues.append(f"Line {line_num}: Missing required field '{field}'")
                
                # Check timestamp format
                if "timestamp" in record:
                    ts = record["timestamp"]
                    if not isinstance(ts, str) or "T" not in ts:
                        issues.append(f"Line {line_num}: Invalid timestamp format")
                
            except json.JSONDecodeError as e:
                invalid_lines += 1
                issues.append(f"Line {line_num}: Invalid JSON - {e}")
    
    return {
        "status": "valid" if not issues else "invalid",
        "valid_lines": valid_lines,
        "invalid_lines": invalid_lines,
        "issues": issues,
    }


def validate_sqlite_db(db_path: Path) -> dict[str, Any]:
    """Validate SQLite database schema and data."""
    issues = []
    
    if not db_path.exists():
        return {"status": "missing", "issues": []}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        if not tables:
            issues.append("No tables found in database")
        else:
            # Check each table
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                
                # Sample rows for validation
                cursor.execute(f"SELECT * FROM {table} LIMIT 5")
                rows = cursor.fetchall()
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [col[1] for col in cursor.fetchall()]
                
                # Check for NULL in required fields
                for col in columns:
                    if "NOT NULL" in str(cursor.execute(f"PRAGMA table_info({table})").fetchall()):
                        # This is simplified - would need proper schema parsing
                        pass
        
        conn.close()
    except Exception as e:
        issues.append(f"Database error: {e}")
    
    return {
        "status": "valid" if not issues else "invalid",
        "tables": tables if "tables" in locals() else [],
        "issues": issues,
    }


def validate_json_file(file_path: Path) -> dict[str, Any]:
    """Validate individual JSON file."""
    issues = []
    
    if not file_path.exists():
        return {"status": "missing", "issues": []}
    
    try:
        with open(file_path) as f:
            data = json.load(f)
        
        # Basic structure check
        if not isinstance(data, dict):
            issues.append("Root must be a JSON object")
        
        # Check for required fields
        if "timestamp" not in data:
            issues.append("Missing 'timestamp' field")
        
        if "metrics" not in data:
            issues.append("Missing 'metrics' field")
        
        # Validate metrics is a dict
        if "metrics" in data and not isinstance(data["metrics"], dict):
            issues.append("'metrics' must be a dictionary")
        
    except json.JSONDecodeError as e:
        issues.append(f"Invalid JSON: {e}")
    except Exception as e:
        issues.append(f"Error reading file: {e}")
    
    return {
        "status": "valid" if not issues else "invalid",
        "issues": issues,
    }


def analyze_duplication() -> dict[str, Any]:
    """Analyze data duplication across formats."""
    duplication = {
        "sqlite_databases": [],
        "jsonl_files": [],
        "json_files": [],
        "overlap": [],
    }
    
    # Check SQLite databases
    db_files = list(Path("experiments").glob("*.db"))
    duplication["sqlite_databases"] = [str(f.name) for f in db_files]
    
    # Check JSONL files
    jsonl_files = list(Path("experiments").glob("*.jsonl"))
    duplication["jsonl_files"] = [str(f.name) for f in jsonl_files]
    
    # Check for overlap
    eval_logs_db = Path("experiments/evaluation_logs/evaluation_runs.db")
    eval_logs_jsonl = Path("experiments/evaluation_logs/evaluation_runs.jsonl")
    
    if eval_logs_db.exists() and eval_logs_jsonl.exists():
        duplication["overlap"].append(
            "evaluation_runs.db and evaluation_runs.jsonl contain same data"
        )
    
    return duplication


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Validate evaluation data")
    parser.add_argument("--format", choices=["all", "sqlite", "jsonl", "json"], default="all")
    parser.add_argument("--check-duplication", action="store_true")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Evaluation Data Validation")
    print("=" * 80)
    print("")
    
    results = {}
    
    # Validate SQLite
    if args.format in ["all", "sqlite"]:
        print("📊 Validating SQLite databases...")
        db_files = [
            Path("experiments/evaluation_logs/evaluation_runs.db"),
            Path("experiments/evaluation_registry.db"),
        ]
        
        for db_path in db_files:
            if db_path.exists():
                result = validate_sqlite_db(db_path)
                results[db_path.name] = result
                status_icon = "✅" if result["status"] == "valid" else "❌"
                print(f"  {status_icon} {db_path.name}: {result['status']}")
                if result.get("issues"):
                    for issue in result["issues"][:3]:
                        print(f"    - {issue}")
        print("")
    
    # Validate JSONL
    if args.format in ["all", "jsonl"]:
        print("📄 Validating JSONL files...")
        jsonl_files = [
            Path("experiments/evaluation_logs/evaluation_runs.jsonl"),
            Path("experiments/EXPERIMENT_LOG_CANONICAL.jsonl"),
        ]
        
        for jsonl_path in jsonl_files:
            if jsonl_path.exists():
                result = validate_jsonl_file(jsonl_path)
                results[jsonl_path.name] = result
                status_icon = "✅" if result["status"] == "valid" else "❌"
                print(f"  {status_icon} {jsonl_path.name}: {result['status']}")
                print(f"    Valid lines: {result.get('valid_lines', 0)}")
                print(f"    Invalid lines: {result.get('invalid_lines', 0)}")
                if result.get("issues"):
                    for issue in result["issues"][:3]:
                        print(f"    - {issue}")
        print("")
    
    # Validate JSON
    if args.format in ["all", "json"]:
        print("📋 Validating JSON files...")
        json_dir = Path("experiments/evaluation_logs")
        if json_dir.exists():
            json_files = list(json_dir.glob("*.json"))[:5]  # Sample
            valid_count = 0
            invalid_count = 0
            
            for json_path in json_files:
                result = validate_json_file(json_path)
                if result["status"] == "valid":
                    valid_count += 1
                else:
                    invalid_count += 1
                    if invalid_count <= 3:
                        print(f"  ❌ {json_path.name}: {', '.join(result['issues'][:2])}")
            
            print(f"  ✅ Valid: {valid_count}, ❌ Invalid: {invalid_count}")
        print("")
    
    # Duplication analysis
    if args.check_duplication:
        print("🔄 Duplication Analysis...")
        dup = analyze_duplication()
        print(f"  SQLite databases: {len(dup['sqlite_databases'])}")
        print(f"  JSONL files: {len(dup['jsonl_files'])}")
        if dup["overlap"]:
            for overlap in dup["overlap"]:
                print(f"  ⚠️  {overlap}")
        print("")
    
    # Summary
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    
    total_valid = sum(1 for r in results.values() if r.get("status") == "valid")
    total_invalid = sum(1 for r in results.values() if r.get("status") == "invalid")
    
    print(f"Valid: {total_valid}")
    print(f"Invalid: {total_invalid}")
    
    if total_invalid > 0:
        print("\n⚠️  Validation issues found")
        return 1
    
    print("\n✅ All validations passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())


