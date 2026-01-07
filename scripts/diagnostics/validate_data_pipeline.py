#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Validate data pipeline - check what files actually exist vs what's documented.
"""

import json
import sys
from pathlib import Path
from typing import Any


def check_file(path: Path, description: str) -> dict[str, Any]:
    """Check if file exists and get stats."""
    exists = path.exists()
    result = {
        "path": str(path),
        "description": description,
        "exists": exists,
    }

    if exists:
        try:
            size = path.stat().st_size
            result["size_mb"] = size / (1024 * 1024)

            # Try to count lines if JSONL
            if path.suffix == ".jsonl":
                try:
                    with open(path) as f:
                        line_count = sum(1 for _ in f)
                    result["line_count"] = line_count
                except Exception:
                    pass
        except Exception as e:
            result["error"] = str(e)

    return result


def main() -> int:
    """Main entry point."""
    import sys
    from pathlib import Path

    # Add src to path
    script_dir = Path(__file__).parent
    src_dir = script_dir.parent.parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    # Import PATHS directly without triggering full ml.utils imports
    try:
        from ml.utils.paths import PATHS
    except ImportError:
        # Fallback: construct paths manually
        class PATHS:
            processed = Path("data/processed")
            decks_all_final = processed / "decks_all_final.jsonl"
            decks_all_enhanced = processed / "decks_all_enhanced.jsonl"
            decks_all_unified = processed / "decks_all_unified.jsonl"
            pairs_large = processed / "pairs_large.csv"

    print("=" * 70)
    print("Data Pipeline Validation")
    print("=" * 70)
    print()

    checks = []

    # Check deck files
    print("Deck Files:")
    print("-" * 70)
    deck_files = [
        (PATHS.decks_all_final, "decks_all_final.jsonl (RECOMMENDED)"),
        (PATHS.decks_all_enhanced, "decks_all_enhanced.jsonl"),
        (PATHS.decks_all_unified, "decks_all_unified.jsonl"),
        (Path("data/processed/decks_pokemon.jsonl"), "decks_pokemon.jsonl"),
    ]

    for path, desc in deck_files:
        result = check_file(path, desc)
        checks.append(result)
        status = "✓" if result["exists"] else "✗"
        size_info = f" ({result.get('size_mb', 0):.1f} MB)" if result.get("size_mb") else ""
        line_info = f", {result.get('line_count', 0):,} lines" if result.get("line_count") else ""
        print(f"  {status} {desc}{size_info}{line_info}")
        if not result["exists"]:
            print(f"      Path: {path}")

    print()

    # Check pairs files
    print("Pairs Files:")
    print("-" * 70)
    pairs_files = [
        (PATHS.pairs_large, "pairs_large.csv"),
        (Path("data/processed/pairs_multi_game.csv"), "pairs_multi_game.csv"),
    ]

    for path, desc in pairs_files:
        result = check_file(path, desc)
        checks.append(result)
        status = "✓" if result["exists"] else "✗"
        size_info = f" ({result.get('size_mb', 0):.1f} MB)" if result.get("size_mb") else ""
        print(f"  {status} {desc}{size_info}")
        if not result["exists"]:
            print(f"      Path: {path}")

    print()

    # Check test sets
    print("Test Sets:")
    print("-" * 70)
    test_sets = [
        (Path("experiments/test_set_canonical_magic.json"), "test_set_canonical_magic.json"),
        (Path("experiments/test_set_unified_magic.json"), "test_set_unified_magic.json"),
        (Path("experiments/test_set_canonical_pokemon.json"), "test_set_canonical_pokemon.json"),
        (Path("experiments/test_set_canonical_yugioh.json"), "test_set_canonical_yugioh.json"),
    ]

    for path, desc in test_sets:
        result = check_file(path, desc)
        checks.append(result)
        status = "✓" if result["exists"] else "✗"
        size_info = f" ({result.get('size_mb', 0):.1f} MB)" if result.get("size_mb") else ""
        print(f"  {status} {desc}{size_info}")
        if not result["exists"]:
            print(f"      Path: {path}")

    print()

    # Summary
    print("=" * 70)
    print("Summary")
    print("=" * 70)

    existing = [c for c in checks if c["exists"]]
    missing = [c for c in checks if not c["exists"]]

    print(f"Existing: {len(existing)}/{len(checks)}")
    print(f"Missing: {len(missing)}/{len(checks)}")

    if missing:
        print("\nMissing files:")
        for c in missing:
            print(f"  - {c['description']}")
            print(f"    Path: {c['path']}")

    # Save report
    output_path = Path("experiments/data_pipeline_validation.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(
            {
                "summary": {
                    "total": len(checks),
                    "existing": len(existing),
                    "missing": len(missing),
                },
                "checks": checks,
            },
            f,
            indent=2,
        )

    print(f"\nReport saved to: {output_path}")

    return 0 if len(missing) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
