#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Clean up evaluation files after migration.

Removes:
- Lock files (.lock)
- Duplicate files (with " 2" suffix)
- Optionally archives old JSON files after migration verification
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()


def cleanup_evaluation_files(dry_run: bool = False, archive: bool = False):
    """Clean up evaluation files."""
    eval_results = Path("experiments/evaluation_results")
    if not eval_results.exists():
        print("No evaluation_results directory found")
        return
    
    removed = []
    archived = []
    
    # 1. Remove lock files
    lock_files = list(eval_results.glob("*.lock"))
    for lock_file in lock_files:
        if dry_run:
            print(f"Would remove: {lock_file.name}")
        else:
            lock_file.unlink()
            removed.append(lock_file.name)
    
    # 2. Remove duplicate files (with " 2" suffix)
    duplicate_files = list(eval_results.glob("* 2.json"))
    for dup_file in duplicate_files:
        if dry_run:
            print(f"Would remove: {dup_file.name}")
        else:
            dup_file.unlink()
            removed.append(dup_file.name)
    
    # 3. Archive migrated files (optional)
    if archive:
        # Check which files have been migrated
        migrated_ids = set()
        log_db = Path("experiments/evaluation_logs/evaluation_runs.db")
        if log_db.exists():
            import sqlite3
            conn = sqlite3.connect(log_db)
            cursor = conn.cursor()
            cursor.execute('SELECT notes FROM evaluation_runs WHERE notes LIKE "%Migrated from%"')
            for row in cursor.fetchall():
                notes = row[0]
                if "Migrated from" in notes:
                    filename = notes.split("Migrated from")[-1].strip()
                    migrated_ids.add(filename)
            conn.close()
        
        # Create archive directory
        archive_dir = eval_results / "archived"
        if not dry_run:
            archive_dir.mkdir(exist_ok=True)
        
        json_files = list(eval_results.glob("*.json"))
        for json_file in json_files:
            if json_file.name in migrated_ids:
                if dry_run:
                    print(f"Would archive: {json_file.name}")
                else:
                    json_file.rename(archive_dir / json_file.name)
                    archived.append(json_file.name)
    
    return removed, archived


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean up evaluation files")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--archive", action="store_true", help="Archive migrated files")
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("Evaluation Files Cleanup")
    print("=" * 80)
    if args.dry_run:
        print("Mode: DRY RUN")
    print("")
    
    removed, archived = cleanup_evaluation_files(dry_run=args.dry_run, archive=args.archive)
    
    print("")
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Removed: {len(removed)} files")
    if archived:
        print(f"Archived: {len(archived)} files")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


