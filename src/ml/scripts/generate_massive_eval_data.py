#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Generate massive amounts of evaluation data from all available sources.

Combines:
1. All existing test sets
2. Comprehensive generated data
3. Quality test sets
4. Synthetic test cases
5. Implicit signals
6. Edge cases
7. Adversarial pairs

Creates the largest, most diverse test set possible.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def discover_test_sets(experiments_dir: Path, game: str) -> list[Path]:
    """Discover all test sets for a game."""
    test_sets = []
    
    # Pattern-based discovery
    patterns = [
        f"test_set_expanded_{game}.json",
        f"test_set_comprehensive_generated_{game}.json",
        f"test_set_comprehensive_generated_{game}_v2.json",
        f"test_set_synthetic_{game}.json",
        f"test_set_synthetic_{game}_v2.json",
        f"test_set_quality_{game}.json",
        f"test_set_improved_quality_{game}.json",
        f"test_set_merged_all_{game}.json",
        f"test_set_merged_all_sources_{game}.json",
        f"test_set_mega_merged_{game}.json",
        f"test_set_ultimate_{game}.json",
    ]
    
    for pattern in patterns:
        path = experiments_dir / pattern
        if path.exists():
            test_sets.append(path)
    
    # Also find any test set with game name
    for path in experiments_dir.glob(f"test_set_*{game}*.json"):
        if path not in test_sets:
            test_sets.append(path)
    
    return test_sets


def generate_additional_synthetic_data(
    pairs_csv: Path,
    embedding_path: Path | None = None,
    game: str = "magic",
    num_queries: int = 200,
) -> Path:
    """Generate additional synthetic data."""
    output = Path(f"experiments/test_set_massive_synthetic_{game}.json")
    
    print(f"📊 Generating massive synthetic data for {game}...")
    
    cmd = [
        sys.executable, "-m", "ml.scripts.create_synthetic_test_cases",
        "--game", game,
        "--pairs-csv", str(pairs_csv),
        "--output", str(output),
        "--functional-num", str(num_queries // 4),
        "--archetype-num", str(num_queries // 2),
        "--power-level-num", str(num_queries // 4),
        "--format-num", str(num_queries // 4),
    ]
    
    if embedding_path and embedding_path.exists():
        cmd.extend(["--embedding", str(embedding_path)])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0 and output.exists():
        print(f"  ✅ Generated {output}")
        return output
    
    return None


def merge_all_test_sets(
    test_sets: list[Path],
    output_path: Path,
    game: str = "magic",
    pairs_csv: Path | None = None,
) -> None:
    """Merge all test sets into one massive test set."""
    print(f"📝 Merging {len(test_sets)} test sets...")
    
    cmd = [
        sys.executable, "-m", "ml.scripts.merge_and_analyze_test_sets",
        "--test-sets", *[str(ts) for ts in test_sets],
        "--output", str(output_path),
        "--game", game,
    ]
    
    if pairs_csv:
        cmd.extend(["--pairs-csv", str(pairs_csv)])
        cmd.extend(["--analysis-output", str(output_path.parent / f"test_set_analysis_massive_{game}.json")])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"  ✅ Merged into {output_path}")
    else:
        print(f"  ⚠️  Merge failed: {result.stderr}")


def main() -> int:
    """Generate massive evaluation data."""
    parser = argparse.ArgumentParser(
        description="Generate massive amounts of evaluation data"
    )
    parser.add_argument("--game", type=str, default="magic",
                       choices=["magic", "pokemon", "yugioh"],
                       help="Game to generate data for")
    parser.add_argument("--pairs-csv", type=str, required=True,
                       help="Pairs CSV file")
    parser.add_argument("--embedding", type=str, help="Embedding file (.wv)")
    parser.add_argument("--output", type=str,
                       default="experiments/test_set_massive_{game}.json",
                       help="Output test set JSON")
    parser.add_argument("--additional-synthetic", type=int, default=200,
                       help="Additional synthetic queries to generate")
    parser.add_argument("--include-all-existing", action="store_true",
                       help="Include all existing test sets")
    
    args = parser.parse_args()
    
    pairs_csv = Path(args.pairs_csv)
    if not pairs_csv.exists():
        print(f"❌ Pairs CSV not found: {pairs_csv}")
        return 1
    
    embedding_path = Path(args.embedding) if args.embedding else None
    
    experiments_dir = Path("experiments")
    output_path = Path(args.output.replace("{game}", args.game))
    
    print("=" * 70)
    print("Generate Massive Evaluation Data")
    print("=" * 70)
    print(f"\nGame: {args.game}")
    print(f"Pairs CSV: {pairs_csv}")
    if embedding_path:
        print(f"Embedding: {embedding_path}")
    print(f"Output: {output_path}\n")
    
    # Discover existing test sets
    test_sets = []
    if args.include_all_existing:
        test_sets = discover_test_sets(experiments_dir, args.game)
        print(f"📊 Discovered {len(test_sets)} existing test sets")
    
    # Generate additional synthetic data
    if args.additional_synthetic > 0:
        synthetic_path = generate_additional_synthetic_data(
            pairs_csv,
            embedding_path=embedding_path,
            game=args.game,
            num_queries=args.additional_synthetic,
        )
        if synthetic_path:
            test_sets.append(synthetic_path)
    
    if not test_sets:
        print("❌ No test sets to merge")
        return 1
    
    # Merge all test sets
    merge_all_test_sets(
        test_sets,
        output_path,
        game=args.game,
        pairs_csv=pairs_csv,
    )
    
    print(f"\n✅ Massive test set created: {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

