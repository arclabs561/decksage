#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas"]
# ///
"""
Regenerate pairs_multi_game.csv with all games (MTG, Pokemon, Yu-Gi-Oh).

Uses the Go export-multi-game-graph tool to generate pairs from all game data.
"""

import argparse
import subprocess
import sys
from pathlib import Path


# Add src to path (must be before other imports)
script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ml.utils.paths import PATHS  # noqa: E402


def regenerate_multi_game_pairs(
    data_dir: Path | None = None,
    output_path: Path | None = None,
    rebuild: bool = False,
) -> int:
    """Regenerate multi-game pairs CSV from raw data."""
    if data_dir is None:
        # Try to find canonical data directory
        backend_data = Path("src/backend/data-full/games")
        if backend_data.exists():
            data_dir = backend_data
        else:
            print("Error: Could not find data directory")
            print(" Expected: src/backend/data-full/games")
            return 1

    if output_path is None:
        output_path = PATHS.processed / "pairs_multi_game.csv"

    if output_path.exists() and not rebuild:
        print(f"Warning: Output file exists: {output_path}")
        print(" Use --rebuild to regenerate")
        return 0

    # Check if Go tool exists
    go_tool = Path("src/backend/cmd/export-multi-game-graph/main.go")
    if not go_tool.exists():
        print(f"Error: Go tool not found: {go_tool}")
        return 1

    print("=" * 70)
    print("Regenerating Multi-Game Pairs")
    print("=" * 70)
    print(f"Data directory: {data_dir}")
    print(f"Output: {output_path}")
    print()

    # Build Go tool using utility
    print("Building export-multi-game-graph...")
    try:
        from ml.utils.export_tools import build_export_tool

        binary_path = build_export_tool(
            "export-multi-game-graph",
            go_tool,
        )
        print("✓ Built successfully")
        print()
    except Exception as e:
        print(f"Error: Failed to build Go tool: {e}")
        return 1

    # Run export
    print("Exporting multi-game pairs...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    export_result = subprocess.run(
        [str(binary_path), str(data_dir), str(output_path)],
        capture_output=True,
        text=True,
    )

    if export_result.returncode != 0:
        print(f"Error: Export failed: {export_result.stderr}")
        return 1

    print(export_result.stdout)

    # Verify output
    if not output_path.exists():
        print(f"Error: Output file not created: {output_path}")
        return 1

    # Count rows efficiently (streaming, not loading entire file)
    print()
    print("=" * 70)
    print("Export Complete")
    print("=" * 70)

    # Use wc for fast line count
    try:
        result = subprocess.run(
            ["wc", "-l", str(output_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        total_lines = int(result.stdout.split()[0])
        # Subtract 1 for header
        total_pairs = max(0, total_lines - 1)
        print(f"Total pairs: {total_pairs:,}")
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        # Fallback: count manually (slower but works)
        total_pairs = 0
        with open(output_path) as f:
            next(f)  # Skip header
            for _ in f:
                total_pairs += 1
        print(f"Total pairs: {total_pairs:,}")

    # Game distribution (sample first 100k rows for performance)
    import csv
    from collections import Counter

    game_counts = Counter()
    sample_size = 0
    max_sample = 100000

    with open(output_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            game_counts[row.get("GAME_1", "")] += 1
            sample_size += 1
            if sample_size >= max_sample:
                break

    if game_counts:
        print("\nGame distribution (sampled from first 100k rows):")
        for game, count in game_counts.most_common():
            percentage = (count / sample_size * 100) if sample_size > 0 else 0
            # Estimate total based on sample
            estimated_total = int(count / sample_size * total_pairs) if sample_size > 0 else 0
            print(f" {game}: {estimated_total:,} pairs ({percentage:.1f}% of sample)")

    print(f"\nOutput: {output_path}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Regenerate multi-game pairs CSV")
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Path to games data directory (default: src/backend/data-full/games)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output CSV path (default: data/processed/pairs_multi_game.csv)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild even if output exists",
    )

    args = parser.parse_args()

    return regenerate_multi_game_pairs(
        data_dir=args.data_dir,
        output_path=args.output,
        rebuild=args.rebuild,
    )


if __name__ == "__main__":
    sys.exit(main())
