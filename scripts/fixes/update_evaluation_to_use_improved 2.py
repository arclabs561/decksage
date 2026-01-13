#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Update evaluation scripts to use improved test set by default.

Updates default test set paths in evaluation scripts to use:
- Improved canonical test set (if exists)
- Or unified test set (better quality)
"""

import re
import sys
from pathlib import Path
from typing import Any


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def update_evaluation_script(script_path: Path) -> dict[str, Any]:
    """Update evaluation script to use improved test set."""
    if not script_path.exists():
        return {
            "success": False,
            "error": "Script not found",
        }

    with open(script_path) as f:
        content = f.read()

    original_content = content
    changes = []

    # Check for improved test set
    improved_test_set = Path("experiments/test_set_canonical_magic_improved.json")
    unified_test_set = Path("experiments/test_set_unified_magic.json")

    # Determine which test set to use
    if improved_test_set.exists():
        target_test_set = str(improved_test_set)
        test_set_name = "improved canonical"
    elif unified_test_set.exists():
        target_test_set = str(unified_test_set)
        test_set_name = "unified"
    else:
        return {
            "success": False,
            "error": "No improved or unified test set found",
        }

    # Update default test set paths
    patterns = [
        # Pattern 1: default=Path("experiments/test_set_canonical_magic.json")
        (
            r'default=Path\("experiments/test_set_canonical_magic\.json"\)',
            f'default=Path("{target_test_set}")',
        ),
        # Pattern 2: default="experiments/test_set_canonical_magic.json"
        (r'default="experiments/test_set_canonical_magic\.json"', f'default="{target_test_set}"'),
        # Pattern 3: PATHS.test_magic (if it points to canonical)
        (r"PATHS\.test_magic", f'Path("{target_test_set}")'),
    ]

    for pattern, replacement in patterns:
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content)
            changes.append(f"Updated: {pattern}")

    if content != original_content:
        # Backup original
        backup_path = script_path.parent / f"{script_path.stem}_backup.py"
        with open(backup_path, "w") as f:
            f.write(original_content)

        # Write updated
        with open(script_path, "w") as f:
            f.write(content)

        return {
            "success": True,
            "script": str(script_path),
            "test_set": test_set_name,
            "changes": changes,
            "backup": str(backup_path),
        }
    else:
        return {
            "success": True,
            "script": str(script_path),
            "test_set": test_set_name,
            "changes": [],
            "message": "No changes needed",
        }


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Update evaluation scripts")
    parser.add_argument(
        "--script",
        type=Path,
        help="Specific script to update (or update all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files",
    )

    args = parser.parse_args()

    # Find evaluation scripts
    if args.script:
        scripts_to_update = [args.script]
    else:
        scripts_to_update = [
            Path("src/ml/scripts/evaluate_all_embeddings.py"),
            Path("scripts/evaluation/evaluate_with_coverage_check.py"),
            Path("scripts/evaluation/ensure_full_evaluation.py"),
        ]

    print("Updating evaluation scripts to use improved test set...")
    print()

    for script_path in scripts_to_update:
        if not script_path.exists():
            print(f"⚠ Skipping {script_path.name}: not found")
            continue

        print(f"Updating {script_path.name}...", end=" ", flush=True)

        if args.dry_run:
            result = update_evaluation_script(script_path)
            if result.get("changes"):
                print(f"Would update to use {result['test_set']} test set")
            else:
                print("No changes needed")
        else:
            result = update_evaluation_script(script_path)
            if result["success"]:
                if result.get("changes"):
                    print(f"✓ Updated to use {result['test_set']} test set")
                    if result.get("backup"):
                        print(f"  Backup: {result['backup']}")
                else:
                    print(f"✓ Already using {result['test_set']} test set")
            else:
                print(f"✗ {result.get('error', 'Failed')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
