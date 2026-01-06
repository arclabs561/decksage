#!/usr/bin/env python3
"""
Sync annotation files to S3.

Uses s5cmd for efficient S3 operations.
"""

import argparse
import subprocess
import sys
from pathlib import Path


def sync_annotations_to_s3(
    annotations_dir: Path,
    s3_path: str,
    dry_run: bool = False,
) -> int:
    """Sync annotation files to S3.
    
    Args:
        annotations_dir: Local directory containing annotation files
        s3_path: S3 path (e.g., s3://bucket/path/to/annotations/)
        dry_run: If True, show what would be synced without actually syncing
        
    Returns:
        Exit code (0 for success)
    """
    print("=" * 80)
    print("SYNCING ANNOTATIONS TO S3")
    print("=" * 80)
    print(f"Local directory: {annotations_dir}")
    print(f"S3 path: {s3_path}")
    print(f"Dry run: {dry_run}")
    print()
    
    # Check s5cmd is available
    try:
        result = subprocess.run(
            ["s5cmd", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            print("Error: s5cmd not found or not working")
            print("Please install s5cmd: https://github.com/peak/s5cmd")
            return 1
    except FileNotFoundError:
        print("Error: s5cmd not found")
        print("Please install s5cmd: https://github.com/peak/s5cmd")
        return 1
    
    # Find annotation files to sync
    annotation_files = []
    
    # JSONL files
    annotation_files.extend(annotations_dir.glob("*.jsonl"))
    
    # JSON files (test sets, substitution pairs, etc.)
    annotation_files.extend(annotations_dir.glob("*.json"))
    
    # YAML files (hand annotation batches)
    annotation_files.extend(annotations_dir.glob("hand_batch_*.yaml"))
    
    # Quality reports
    annotation_files.extend(annotations_dir.glob("*quality*.json"))
    annotation_files.extend(annotations_dir.glob("*tracking*.json"))
    
    # Filter to only existing files
    annotation_files = [f for f in annotation_files if f.exists() and f.is_file()]
    
    if not annotation_files:
        print("No annotation files found to sync")
        return 0
    
    print(f"Found {len(annotation_files)} annotation files to sync:")
    for f in sorted(annotation_files):
        size = f.stat().st_size
        print(f"  {f.name} ({size:,} bytes)")
    
    print()
    
    if dry_run:
        print("DRY RUN - Would sync the following files:")
        for f in annotation_files:
            local_path = str(f)
            s3_file_path = f"{s3_path.rstrip('/')}/{f.name}"
            print(f"  {local_path} -> {s3_file_path}")
        return 0
    
    # Sync files using s5cmd
    print("Syncing files to S3...")
    
    synced_count = 0
    failed_count = 0
    
    for annotation_file in annotation_files:
        local_path = str(annotation_file)
        s3_file_path = f"{s3_path.rstrip('/')}/{annotation_file.name}"
        
        print(f"Syncing {annotation_file.name}...", end=" ", flush=True)
        
        try:
            result = subprocess.run(
                ["s5cmd", "cp", local_path, s3_file_path],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                print("✓")
                synced_count += 1
            else:
                print(f"✗ Error: {result.stderr}")
                failed_count += 1
        except subprocess.TimeoutExpired:
            print("✗ Timeout")
            failed_count += 1
        except Exception as e:
            print(f"✗ Error: {e}")
            failed_count += 1
    
    print()
    print("=" * 80)
    print("SYNC SUMMARY")
    print("=" * 80)
    print(f"Synced: {synced_count}")
    print(f"Failed: {failed_count}")
    print(f"Total: {len(annotation_files)}")
    
    if failed_count > 0:
        return 1
    
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Sync annotation files to S3")
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Local directory containing annotation files",
    )
    parser.add_argument(
        "--s3-path",
        type=str,
        required=True,
        help="S3 path (e.g., s3://bucket/path/to/annotations/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without actually syncing",
    )
    
    args = parser.parse_args()
    
    if not args.annotations_dir.exists():
        print(f"Error: Annotations directory not found: {args.annotations_dir}")
        return 1
    
    return sync_annotations_to_s3(
        annotations_dir=args.annotations_dir,
        s3_path=args.s3_path,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())


