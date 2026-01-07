#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Archive old evaluation logs.

Features:
- Archive by age (days)
- Archive by count (keep N most recent)
- Compress archives
- Remove archived logs (optional)
"""

import json
import shutil
import sqlite3
import sys
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()


def archive_old_logs(
    log_dir: Path,
    archive_dir: Path,
    days: int | None = None,
    keep_recent: int | None = None,
    compress: bool = True,
    remove: bool = False,
) -> dict[str, Any]:
    """
    Archive old evaluation logs.
    
    Args:
        log_dir: Directory containing logs
        archive_dir: Directory to store archives
        days: Archive logs older than N days
        keep_recent: Keep only N most recent logs
        compress: Compress archive
        remove: Remove archived logs after archiving
    
    Returns:
        Archive results
    """
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    results = {
        "archived": [],
        "kept": [],
        "errors": [],
    }
    
    # Get all runs from SQLite
    db_path = log_dir / "evaluation_runs.db"
    if not db_path.exists():
        return results
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all runs with timestamps
    cursor.execute("SELECT run_id, timestamp FROM evaluation_runs ORDER BY timestamp DESC")
    runs = cursor.fetchall()
    
    cutoff_date = None
    if days:
        cutoff_date = datetime.now() - timedelta(days=days)
    
    # Determine which runs to archive
    runs_to_archive = []
    runs_to_keep = []
    
    for i, run in enumerate(runs):
        run_id = run["run_id"]
        timestamp_str = run["timestamp"]
        
        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            results["errors"].append(f"Invalid timestamp for {run_id}")
            continue
        
        should_archive = False
        
        # Check age
        if cutoff_date and timestamp < cutoff_date:
            should_archive = True
        
        # Check count
        if keep_recent and i >= keep_recent:
            should_archive = True
        
        if should_archive:
            runs_to_archive.append((run_id, timestamp))
        else:
            runs_to_keep.append(run_id)
    
    # Archive runs
    if runs_to_archive:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"evaluation_logs_archive_{timestamp}"
        
        if compress:
            archive_path = archive_dir / f"{archive_name}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                # Archive JSON files
                for run_id, _ in runs_to_archive:
                    json_path = log_dir / f"{run_id}.json"
                    if json_path.exists():
                        tar.add(json_path, arcname=json_path.name)
        else:
            archive_path = archive_dir / archive_name
            archive_path.mkdir()
            
            for run_id, _ in runs_to_archive:
                json_path = log_dir / f"{run_id}.json"
                if json_path.exists():
                    shutil.copy2(json_path, archive_path / json_path.name)
        
        results["archived"] = [run_id for run_id, _ in runs_to_archive]
        results["archive_path"] = archive_path
        
        # Remove archived logs if requested
        if remove:
            for run_id, _ in runs_to_archive:
                json_path = log_dir / f"{run_id}.json"
                if json_path.exists():
                    json_path.unlink()
    
    results["kept"] = runs_to_keep
    
    conn.close()
    
    return results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Archive old evaluation logs")
    parser.add_argument("--log-dir", type=Path, default=Path("experiments/evaluation_logs"))
    parser.add_argument("--archive-dir", type=Path, default=Path("experiments/archives"))
    parser.add_argument("--days", type=int, help="Archive logs older than N days")
    parser.add_argument("--keep-recent", type=int, help="Keep only N most recent logs")
    parser.add_argument("--compress", action="store_true", default=True)
    parser.add_argument("--no-compress", dest="compress", action="store_false")
    parser.add_argument("--remove", action="store_true", help="Remove archived logs after archiving")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be archived")
    
    args = parser.parse_args()
    
    if not args.days and not args.keep_recent:
        parser.error("Must specify --days or --keep-recent")
    
    print("=" * 80)
    print("Archiving Old Evaluation Logs")
    print("=" * 80)
    if args.dry_run:
        print("Mode: DRY RUN")
    print("")
    
    if args.dry_run:
        # Just show what would be archived
        print("Would archive logs:")
        if args.days:
            print(f"  Older than {args.days} days")
        if args.keep_recent:
            print(f"  Keeping only {args.keep_recent} most recent")
        return 0
    
    results = archive_old_logs(
        log_dir=args.log_dir,
        archive_dir=args.archive_dir,
        days=args.days,
        keep_recent=args.keep_recent,
        compress=args.compress,
        remove=args.remove,
    )
    
    print(f"📦 Archived: {len(results['archived'])} runs")
    print(f"💾 Kept: {len(results['kept'])} runs")
    
    if results.get("archive_path"):
        print(f"📁 Archive: {results['archive_path']}")
    
    if results["errors"]:
        print(f"⚠️  Errors: {len(results['errors'])}")
        for error in results["errors"][:5]:
            print(f"  - {error}")
    
    print("")
    print("✅ Archiving complete")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


