#!/usr/bin/env python3
"""
Migrate judgment JSON files to unified annotation JSONL format.

Converts old judgment format (JSON) to new annotation format (JSONL).
This is a one-time migration script.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ml.utils.annotation_utils import (
    convert_judgments_to_annotations,
    load_judgment_files,
)
from ml.utils.paths import PATHS


def migrate_judgment_file(judgment_file: Path, output_dir: Path) -> int:
    """Migrate a single judgment JSON file to annotation JSONL format."""
    print(f"Migrating {judgment_file.name}...")

    # Load judgment
    with open(judgment_file) as f:
        judgment = json.load(f)

    # Convert to annotations
    annotations = convert_judgments_to_annotations([judgment])

    if not annotations:
        print(f"  Warning: No annotations generated from {judgment_file.name}")
        return 0

    # Determine output filename (use same timestamp if available)
    timestamp = judgment.get("timestamp", "").replace(":", "").replace("-", "")[:14]
    if timestamp:
        output_file = output_dir / f"judgment_{timestamp}.jsonl"
    else:
        # Use original filename stem
        output_file = output_dir / f"{judgment_file.stem}.jsonl"

    # Save as JSONL with atomic write
    temp_path = output_file.with_suffix(output_file.suffix + ".tmp")
    try:
        with open(temp_path, "w") as f:
            for ann in annotations:
                f.write(json.dumps(ann) + "\n")
        temp_path.replace(output_file)
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise

    print(f"  ✓ Created {output_file.name} with {len(annotations)} annotations")
    return len(annotations)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate judgment JSON files to annotation JSONL format"
    )
    parser.add_argument(
        "--judgments-dir",
        type=Path,
        default=None,
        help="Directory containing judgment_*.json files (default: annotations/llm_judgments)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory for annotation JSONL files (default: annotations)",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup of original judgment files",
    )

    args = parser.parse_args()

    # Set defaults from PATHS utility
    if args.judgments_dir is None:
        args.judgments_dir = PATHS.annotations / "llm_judgments"
    if args.output_dir is None:
        args.output_dir = PATHS.annotations

    if not args.judgments_dir.exists():
        print(f"Error: Judgments directory not found: {args.judgments_dir}")
        return 1

    # Find all judgment JSON files
    judgment_files = list(args.judgments_dir.glob("judgment_*.json"))
    if not judgment_files:
        print(f"No judgment files found in {args.judgments_dir}")
        return 0

    print(f"Found {len(judgment_files)} judgment files to migrate")
    print(f"Output directory: {args.output_dir}")
    print()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Backup if requested
    if args.backup:
        backup_dir = args.judgments_dir / "backup"
        backup_dir.mkdir(exist_ok=True)
        print(f"Creating backup in {backup_dir}...")
        for judgment_file in judgment_files:
            import shutil

            shutil.copy2(judgment_file, backup_dir / judgment_file.name)
        print(f"  ✓ Backed up {len(judgment_files)} files")
        print()

    # Migrate each file
    total_annotations = 0
    for judgment_file in judgment_files:
        count = migrate_judgment_file(judgment_file, args.output_dir)
        total_annotations += count

    print()
    print("=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    print(f"Migrated {len(judgment_files)} judgment files")
    print(f"Created {total_annotations} annotations")
    print(f"Output directory: {args.output_dir}")
    print()
    print("Next steps:")
    print("  1. Verify migrated annotations")
    print("  2. Update scripts to use new format")
    print("  3. Archive old judgment files (optional)")

    return 0


if __name__ == "__main__":
    exit(main())

