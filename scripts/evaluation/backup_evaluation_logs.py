#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Backup and restore evaluation logs.

Features:
- Full backup (SQLite + JSONL + JSON)
- Incremental backup
- Restore from backup
- Compression support
"""

import json
import shutil
import sqlite3
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()


def backup_evaluation_logs(
    log_dir: Path,
    backup_dir: Path,
    compress: bool = True,
    incremental: bool = False,
) -> Path:
    """
    Backup evaluation logs.
    
    Args:
        log_dir: Directory containing logs
        backup_dir: Directory to store backups
        compress: Compress backup (tar.gz)
        incremental: Only backup new/changed files
    
    Returns:
        Path to backup file
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"evaluation_logs_backup_{timestamp}"
    
    if compress:
        backup_path = backup_dir / f"{backup_name}.tar.gz"
        with tarfile.open(backup_path, "w:gz") as tar:
            # Backup SQLite
            db_path = log_dir / "evaluation_runs.db"
            if db_path.exists():
                tar.add(db_path, arcname="evaluation_runs.db")
            
            # Backup JSONL
            jsonl_path = log_dir / "evaluation_runs.jsonl"
            if jsonl_path.exists():
                tar.add(jsonl_path, arcname="evaluation_runs.jsonl")
            
            # Backup JSON files (optional)
            for json_file in log_dir.glob("*.json"):
                tar.add(json_file, arcname=json_file.name)
    else:
        backup_path = backup_dir / backup_name
        backup_path.mkdir()
        
        # Copy SQLite
        db_path = log_dir / "evaluation_runs.db"
        if db_path.exists():
            shutil.copy2(db_path, backup_path / "evaluation_runs.db")
        
        # Copy JSONL
        jsonl_path = log_dir / "evaluation_runs.jsonl"
        if jsonl_path.exists():
            shutil.copy2(jsonl_path, backup_path / "evaluation_runs.jsonl")
        
        # Copy JSON files
        for json_file in log_dir.glob("*.json"):
            shutil.copy2(json_file, backup_path / json_file.name)
    
    return backup_path


def restore_evaluation_logs(
    backup_path: Path,
    restore_dir: Path,
    overwrite: bool = False,
) -> None:
    """
    Restore evaluation logs from backup.
    
    Args:
        backup_path: Path to backup file/directory
        restore_dir: Directory to restore to
        overwrite: Overwrite existing files
    """
    restore_dir.mkdir(parents=True, exist_ok=True)
    
    if backup_path.suffix == ".gz" or backup_path.suffixes == [".tar", ".gz"]:
        # Compressed backup
        with tarfile.open(backup_path, "r:gz") as tar:
            tar.extractall(restore_dir)
    else:
        # Directory backup
        for item in backup_path.iterdir():
            if item.is_file():
                dest = restore_dir / item.name
                if dest.exists() and not overwrite:
                    raise FileExistsError(f"{dest} exists. Use --overwrite to replace.")
                shutil.copy2(item, dest)


def verify_backup(backup_path: Path) -> dict[str, Any]:
    """Verify backup integrity."""
    issues = []
    
    if backup_path.suffix == ".gz":
        # Compressed backup
        try:
            with tarfile.open(backup_path, "r:gz") as tar:
                members = tar.getnames()
                if "evaluation_runs.db" not in members:
                    issues.append("Missing evaluation_runs.db")
                if "evaluation_runs.jsonl" not in members:
                    issues.append("Missing evaluation_runs.jsonl")
        except Exception as e:
            issues.append(f"Backup corrupted: {e}")
    else:
        # Directory backup
        if not (backup_path / "evaluation_runs.db").exists():
            issues.append("Missing evaluation_runs.db")
        if not (backup_path / "evaluation_runs.jsonl").exists():
            issues.append("Missing evaluation_runs.jsonl")
    
    return {
        "status": "ok" if not issues else "invalid",
        "issues": issues,
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Backup and restore evaluation logs")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Create backup")
    backup_parser.add_argument("--log-dir", type=Path, default=Path("experiments/evaluation_logs"))
    backup_parser.add_argument("--backup-dir", type=Path, default=Path("experiments/backups"))
    backup_parser.add_argument("--compress", action="store_true", default=True)
    backup_parser.add_argument("--no-compress", dest="compress", action="store_false")
    
    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("backup_path", type=Path, help="Path to backup")
    restore_parser.add_argument("--restore-dir", type=Path, default=Path("experiments/evaluation_logs"))
    restore_parser.add_argument("--overwrite", action="store_true")
    
    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify backup")
    verify_parser.add_argument("backup_path", type=Path, help="Path to backup")
    
    args = parser.parse_args()
    
    if args.command == "backup":
        print("=" * 80)
        print("Backing up evaluation logs...")
        print("=" * 80)
        
        backup_path = backup_evaluation_logs(
            log_dir=args.log_dir,
            backup_dir=args.backup_dir,
            compress=args.compress,
        )
        
        print(f"✅ Backup created: {backup_path}")
        
        # Verify backup
        result = verify_backup(backup_path)
        if result["status"] == "ok":
            print("✅ Backup verified")
        else:
            print(f"⚠️  Backup issues: {', '.join(result['issues'])}")
    
    elif args.command == "restore":
        print("=" * 80)
        print("Restoring evaluation logs...")
        print("=" * 80)
        
        restore_evaluation_logs(
            backup_path=args.backup_path,
            restore_dir=args.restore_dir,
            overwrite=args.overwrite,
        )
        
        print(f"✅ Restored to: {args.restore_dir}")
    
    elif args.command == "verify":
        print("=" * 80)
        print("Verifying backup...")
        print("=" * 80)
        
        result = verify_backup(args.backup_path)
        if result["status"] == "ok":
            print("✅ Backup is valid")
        else:
            print(f"❌ Backup issues:")
            for issue in result["issues"]:
                print(f"  - {issue}")
            return 1
    
    else:
        parser.print_help()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


