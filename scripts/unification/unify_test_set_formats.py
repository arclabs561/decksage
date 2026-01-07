#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Unify test set formats across the repository.

Ensures all test sets use the same format:
- Wrapped in "queries" key
- Consistent label structure
- Standardized metadata
"""

import json
import sys
from pathlib import Path
from typing import Any


# Add src to path
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def unify_test_set_format(test_set_path: Path, output_path: Path | None = None) -> dict[str, Any]:
    """Unify test set format."""
    with open(test_set_path) as f:
        data = json.load(f)

    # Extract queries
    if "queries" in data:
        queries = data["queries"]
        metadata = {k: v for k, v in data.items() if k != "queries"}
    else:
        queries = data
        metadata = {}

    if not isinstance(queries, dict):
        return {
            "success": False,
            "error": "Invalid format: queries not a dict",
        }

    # Create unified format
    unified = {
        "version": metadata.get("version", "unified"),
        "description": metadata.get("description", "Unified test set format"),
        "game": metadata.get("game", "magic"),
        "queries": queries,
    }

    # Add metadata if present
    if "created_at" in metadata:
        unified["created_at"] = metadata["created_at"]
    if "updated_at" in metadata:
        unified["updated_at"] = metadata["updated_at"]

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(unified, f, indent=2)

    return {
        "success": True,
        "unified_format": unified,
        "output_path": str(output_path) if output_path else None,
    }


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Unify test set formats")
    parser.add_argument(
        "--test-set",
        type=Path,
        required=True,
        help="Test set to unify",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output unified test set",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Backup original",
    )

    args = parser.parse_args()

    if not args.test_set.exists():
        print(f"Error: Test set not found: {args.test_set}")
        return 1

    if args.output is None:
        args.output = args.test_set.parent / f"{args.test_set.stem}_unified.json"

    print(f"Unifying format for {args.test_set.name}...")
    print()

    # Backup if requested
    if args.backup:
        backup_path = args.test_set.parent / f"{args.test_set.stem}_backup.json"
        import shutil

        shutil.copy2(args.test_set, backup_path)
        print(f"Backed up to: {backup_path}")
        print()

    result = unify_test_set_format(args.test_set, args.output)

    if not result["success"]:
        print(f"Error: {result.get('error', 'Unknown error')}")
        return 1

    print("✓ Unified format created")
    print(f"  Output: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
