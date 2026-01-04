#!/usr/bin/env python3
"""
Export decks with metadata if missing.

This script checks if decks_with_metadata.jsonl exists, and if not,
runs the Go export command to generate it.
"""

# /// script
# requires-python = ">=3.10"
# ///

import subprocess
import sys

from ml.utils.paths import PATHS


def export_decks_metadata() -> bool:
    """Export decks with metadata using Go command."""
    backend_dir = PATHS.backend
    export_cmd = backend_dir / "cmd" / "export-hetero" / "main.go"

    if not export_cmd.exists():
        print(f"Error: Export command not found: {export_cmd}")
        return False

    # Find data directory
    data_dir = backend_dir / "data-full" / "games" / "magic"
    if not data_dir.exists():
        print(f"Error: Data directory not found: {data_dir}")
        return False

    output_file = PATHS.decks_with_metadata
    output_file.parent.mkdir(parents=True, exist_ok=True)

    print("Exporting decks with metadata...")
    print(f" Data dir: {data_dir}")
    print(f" Output: {output_file}")

    try:
        result = subprocess.run(
            ["go", "run", str(export_cmd), str(data_dir), str(output_file)],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        print(result.stdout)

        if output_file.exists():
            count = sum(1 for _ in open(output_file))
            print(f"✓ Exported {count} decks to {output_file}")
            return True
        else:
            print("Error: Output file not created")
            return False

    except subprocess.CalledProcessError as e:
        print(f"Error: Export failed: {e}")
        print(f" stdout: {e.stdout}")
        print(f" stderr: {e.stderr}")
        return False
    except FileNotFoundError:
        print("Error: Go not found. Install Go to export decks.")
        return False


def main() -> int:
    """Check and export decks metadata if needed."""
    decks_file = PATHS.decks_with_metadata

    if decks_file.exists():
        count = sum(1 for _ in open(decks_file))
        print(f"✓ Decks metadata already exists: {decks_file} ({count} decks)")
        return 0

    print(f"Decks metadata not found: {decks_file}")
    print("Attempting to export...")

    if export_decks_metadata():
        return 0
    else:
        print("\nError: Failed to export decks metadata")
        print(" You may need to:")
        print(" 1. Ensure Go is installed")
        print(" 2. Ensure data exists in src/backend/data-full/games/magic/")
        print(
            " 3. Run manually: cd src/backend && go run cmd/export-hetero/main.go data-full/games/magic ../../data/processed/decks_with_metadata.jsonl"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
