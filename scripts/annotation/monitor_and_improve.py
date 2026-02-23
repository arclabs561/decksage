#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Monitor annotation generation and continuously improve.

This script:
1. Monitors annotation files for new annotations
2. Analyzes quality trends
3. Identifies issues (score clustering, missing data)
4. Suggests improvements
5. Can trigger re-generation with improvements
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


def load_annotations(file_path: Path) -> list[dict[str, Any]]:
    """Load annotations from JSONL file."""
    annotations = []
    if not file_path.exists():
        return annotations

    with open(file_path) as f:
        for line in f:
            if line.strip():
                try:
                    annotations.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return annotations


def analyze_trends(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze quality trends."""
    if not annotations:
        return {"error": "No annotations"}

    scores = [
        float(a.get("similarity_score", 0.0))
        for a in annotations
        if a.get("similarity_score") is not None
    ]

    if not scores:
        return {"error": "No scores"}

    # Score distribution
    ranges = {
        "0.0-0.2": sum(1 for s in scores if 0.0 <= s < 0.2),
        "0.2-0.4": sum(1 for s in scores if 0.2 <= s < 0.4),
        "0.4-0.6": sum(1 for s in scores if 0.4 <= s < 0.6),
        "0.6-0.8": sum(1 for s in scores if 0.6 <= s < 0.8),
        "0.8-1.0": sum(1 for s in scores if 0.8 <= s <= 1.0),
    }

    mean = sum(scores) / len(scores)
    std_dev = (sum((s - mean) ** 2 for s in scores) / len(scores)) ** 0.5

    # Issues
    issues = []

    # Check clustering
    low_pct = ranges["0.0-0.2"] / len(scores) * 100
    _mid_pct = (ranges["0.2-0.4"] + ranges["0.4-0.6"]) / len(scores) * 100
    high_pct = (ranges["0.6-0.8"] + ranges["0.8-1.0"]) / len(scores) * 100

    if low_pct > 40:
        issues.append(f"Score clustering in low range ({low_pct:.1f}%)")
    if high_pct > 60:
        issues.append(f"Score clustering in high range ({high_pct:.1f}%)")
    if std_dev < 0.15:
        issues.append(f"Low diversity (std={std_dev:.3f})")

    # Check missing data
    missing_data = sum(
        1 for a in annotations if not a.get("card_comparison", {}).get("card1_attrs")
    )
    if missing_data > len(annotations) * 0.2:
        issues.append(f"Missing card data ({missing_data}/{len(annotations)})")

    missing_reasoning = sum(
        1 for a in annotations if not a.get("reasoning") or len(a.get("reasoning", "")) < 20
    )
    if missing_reasoning > len(annotations) * 0.2:
        issues.append(f"Missing/incomplete reasoning ({missing_reasoning}/{len(annotations)})")

    return {
        "count": len(annotations),
        "mean_score": mean,
        "std_dev": std_dev,
        "diversity": min(1.0, std_dev * 2.0),
        "ranges": ranges,
        "range_utilization": max(scores) - min(scores),
        "issues": issues,
        "sources": Counter(a.get("source", "unknown") for a in annotations),
        "games": Counter(a.get("game", "unknown") for a in annotations),
    }


def monitor_annotations(
    annotations_dir: Path,
    games: list[str] | None = None,
    check_interval: int = 30,
    max_iterations: int | None = None,
) -> None:
    """Monitor annotation files and analyze trends."""
    if games is None:
        games = ["magic", "pokemon", "yugioh", "riftbound"]

    print("=" * 80)
    print("ANNOTATION MONITORING AND IMPROVEMENT")
    print("=" * 80)
    print(f"Monitoring: {annotations_dir}")
    print(f"Games: {', '.join(games)}")
    print(f"Check interval: {check_interval}s")
    print()

    iteration = 0
    last_counts = {}

    try:
        while max_iterations is None or iteration < max_iterations:
            iteration += 1
            print(f"\n[{iteration}] Checking annotations... ({time.strftime('%H:%M:%S')})")

            all_annotations = []
            game_stats = {}

            for game in games:
                ann_file = annotations_dir / f"{game}_llm_annotations.jsonl"
                if ann_file.exists():
                    anns = load_annotations(ann_file)
                    count = len(anns)
                    last_count = last_counts.get(game, 0)

                    if count > last_count:
                        new_count = count - last_count
                        print(f"  {game}: {count} annotations (+{new_count} new)")
                    else:
                        print(f"  {game}: {count} annotations")

                    last_counts[game] = count
                    all_annotations.extend(anns)

                    # Analyze this game
                    trends = analyze_trends(anns)
                    game_stats[game] = trends

                    if trends.get("issues"):
                        print(f"    Issues: {', '.join(trends['issues'])}")

            # Overall analysis
            if all_annotations:
                overall = analyze_trends(all_annotations)
                print(f"\n  Overall: {overall['count']} annotations")
                print(f"    Mean score: {overall['mean_score']:.3f}")
                print(f"    Diversity: {overall['diversity']:.3f}")
                print(f"    Range utilization: {overall['range_utilization']:.3f}")

                if overall.get("issues"):
                    print(f"    ⚠ Issues: {', '.join(overall['issues'])}")

            # Wait before next check
            if max_iterations is None or iteration < max_iterations:
                time.sleep(check_interval)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
        return


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Monitor and improve annotations")
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Annotations directory",
    )
    parser.add_argument(
        "--games",
        nargs="+",
        default=["magic", "pokemon", "yugioh", "riftbound"],
        help="Games to monitor (default: all games)",
    )
    parser.add_argument(
        "--check-interval",
        type=int,
        default=30,
        help="Check interval in seconds",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        help="Maximum number of check iterations",
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Just analyze current state, don't monitor",
    )

    args = parser.parse_args()

    if args.analyze_only:
        # Just analyze current state
        print("Analyzing current annotation state...")
        all_annotations = []
        for game in args.games:
            ann_file = args.annotations_dir / f"{game}_llm_annotations.jsonl"
            if ann_file.exists():
                anns = load_annotations(ann_file)
                all_annotations.extend(anns)
                trends = analyze_trends(anns)
                print(f"\n{game.upper()}:")
                print(f"  Count: {trends['count']}")
                print(f"  Mean: {trends['mean_score']:.3f}")
                print(f"  Diversity: {trends['diversity']:.3f}")
                if trends.get("issues"):
                    print(f"  Issues: {', '.join(trends['issues'])}")

        if all_annotations:
            overall = analyze_trends(all_annotations)
            print("\nOVERALL:")
            print(f"  Total: {overall['count']}")
            print(f"  Mean: {overall['mean_score']:.3f}")
            print(f"  Diversity: {overall['diversity']:.3f}")
            if overall.get("issues"):
                print(f"  Issues: {', '.join(overall['issues'])}")
    else:
        # Monitor continuously
        monitor_annotations(
            args.annotations_dir,
            args.games,
            args.check_interval,
            args.max_iterations,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
