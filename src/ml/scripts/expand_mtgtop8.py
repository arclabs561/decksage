#!/usr/bin/env python3
"""
Expand MTGTop8 Collection

Strategic expansion of MTGTop8 to fill archetype gaps.

Current: 4,718 decks from MTGTop8
Target: 8,000-10,000 decks
Focus: Fill underrepresented archetypes identified in gap analysis

Approach:
1. Load scraping targets (436 underrepresented archetypes)
2. Determine how many more pages to scrape from MTGTop8
3. Run targeted extraction
4. Validate quality
"""

import json
from pathlib import Path


def analyze_current_coverage():
    """Understand current MTGTop8 coverage."""

    data_path = Path("../../data/processed/decks_with_metadata.jsonl")
    targets_path = Path("../../data/scraping_targets.json")

    # Current coverage
    current_archetypes = {}
    with open(data_path) as f:
        for line in f:
            deck = json.loads(line)
            arch = deck.get("archetype", "unknown")
            fmt = deck.get("format", "unknown")
            key = f"{fmt}::{arch}"
            current_archetypes[key] = current_archetypes.get(key, 0) + 1

    # Load targets
    with open(targets_path) as f:
        targets = json.load(f)

    # How many are critical?
    critical = [t for t in targets if t["current"] < 10]
    moderate = [t for t in targets if 10 <= t["current"] < 20]

    print("=" * 60)
    print("MTGTOP8 EXPANSION ANALYSIS")
    print("=" * 60)
    print("Current decks: 4,718")
    print(f"Current archetypes: {len(current_archetypes)}")
    print()
    print("Underrepresented:")
    print(f"  Critical (1-9 decks):   {len(critical)} archetypes")
    print(f"  Moderate (10-19 decks): {len(moderate)} archetypes")
    print()
    print("Decks needed to fill critical gaps:")
    critical_needed = sum(t["needed"] for t in critical)
    print(f"  {critical_needed} decks for critical targets")
    print()
    print("Expansion Strategy:")
    print("  1. Scrape +200 pages from MTGTop8 (~2,000 decks)")
    print("  2. Will naturally fill some gaps")
    print("  3. Re-assess which gaps remain")
    print("  4. Targeted scraping for stubborn gaps")

    return {
        "current_total": 4718,
        "critical_targets": len(critical),
        "moderate_targets": len(moderate),
        "decks_needed": critical_needed,
    }


def create_expansion_command():
    """Generate command for expansion."""

    print(f"\n{'=' * 60}")
    print("EXPANSION COMMANDS")
    print(f"{'=' * 60}")
    print()
    print("Option 1: Broad expansion (+2,000 decks)")
    print("```bash")
    print("cd /Users/henry/Documents/dev/decksage/src/backend")
    print("go run cmd/dataset/main.go extract mtgtop8 \\")
    print("  --bucket=file://./data-full \\")
    print("  --pages=200 \\")
    print("  --start=50")
    print("```")
    print()
    print("Option 2: Conservative test (+200 decks)")
    print("```bash")
    print("go run cmd/dataset/main.go extract mtgtop8 \\")
    print("  --bucket=file://./data-full \\")
    print("  --pages=20 \\")
    print("  --start=50")
    print("```")
    print()
    print("After scraping:")
    print("```bash")
    print("# Export new data")
    print("go run cmd/export-hetero/main.go \\")
    print("  data-full/games/magic/mtgtop8/collections \\")
    print("  ../../data/processed/decks_mtgtop8_expanded.jsonl")
    print()
    print("# Integrate (replace old with new)")
    print("mv ../../data/processed/decks_mtgtop8_expanded.jsonl \\")
    print("   ../../data/processed/decks_with_metadata.jsonl")
    print()
    print("# Re-assess health")
    print("cd ../../src/ml")
    print("uv run python data_gardening.py")
    print("```")


def main():
    analyze_current_coverage()
    create_expansion_command()

    print(f"\n{'=' * 60}")
    print("RECOMMENDATIONS")
    print(f"{'=' * 60}")
    print("1. Start with conservative expansion (+200 decks)")
    print("2. Validate quality remains high")
    print("3. Scale to full expansion if quality holds")
    print("4. Monitor for diminishing returns")
    print()
    print("Gardening principle: Grow thoughtfully, not recklessly")


if __name__ == "__main__":
    main()
