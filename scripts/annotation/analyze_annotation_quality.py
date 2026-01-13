#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Analyze annotation quality across all games and sources.

Provides:
- Score distribution analysis
- Source quality comparison
- Game-specific quality metrics
- Meta-judge feedback trends
- Recommendations for improvement
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def analyze_score_distribution(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze score distribution."""
    scores = [
        float(a.get("similarity_score", 0.0))
        for a in annotations
        if a.get("similarity_score") is not None
    ]

    if not scores:
        return {"error": "No scores found"}

    # Score ranges
    ranges = {
        "0.0-0.2": 0,
        "0.2-0.4": 0,
        "0.4-0.6": 0,
        "0.6-0.8": 0,
        "0.8-1.0": 0,
    }

    for score in scores:
        if score < 0.2:
            ranges["0.0-0.2"] += 1
        elif score < 0.4:
            ranges["0.2-0.4"] += 1
        elif score < 0.6:
            ranges["0.4-0.6"] += 1
        elif score < 0.8:
            ranges["0.6-0.8"] += 1
        else:
            ranges["0.8-1.0"] += 1

    # Statistics
    mean = sum(scores) / len(scores)
    min_score = min(scores)
    max_score = max(scores)

    # Standard deviation
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    std_dev = variance**0.5

    # Diversity metric (normalized std dev)
    diversity = min(1.0, std_dev * 2.0)

    return {
        "count": len(scores),
        "mean": mean,
        "min": min_score,
        "max": max_score,
        "std_dev": std_dev,
        "diversity": diversity,
        "ranges": ranges,
        "range_utilization": max_score - min_score,
    }


def analyze_by_source(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze quality by annotation source."""
    by_source = defaultdict(list)

    for ann in annotations:
        source = ann.get("source", "unknown")
        by_source[source].append(ann)

    results = {}
    for source, anns in by_source.items():
        score_dist = analyze_score_distribution(anns)
        results[source] = {
            "count": len(anns),
            "score_distribution": score_dist,
            "games": Counter(a.get("game", "unknown") for a in anns),
        }

    return results


def analyze_by_game(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze quality by game."""
    by_game = defaultdict(list)

    for ann in annotations:
        game = ann.get("game", "unknown")
        by_game[game].append(ann)

    results = {}
    for game, anns in by_game.items():
        score_dist = analyze_score_distribution(anns)
        results[game] = {
            "count": len(anns),
            "score_distribution": score_dist,
            "sources": Counter(a.get("source", "unknown") for a in anns),
        }

    return results


def analyze_quality_issues(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Identify quality issues."""
    issues = {
        "missing_card_data": 0,
        "low_score_diversity": 0,
        "missing_reasoning": 0,
        "missing_thinking": 0,
        "missing_graph_features": 0,
    }

    scores = [
        float(a.get("similarity_score", 0.0))
        for a in annotations
        if a.get("similarity_score") is not None
    ]

    # Check for score clustering (low diversity)
    if scores:
        std_dev = (sum((s - sum(scores) / len(scores)) ** 2 for s in scores) / len(scores)) ** 0.5
        if std_dev < 0.15:  # Low diversity threshold
            issues["low_score_diversity"] = len(annotations)

    for ann in annotations:
        # Check card data
        card_comp = ann.get("card_comparison", {})
        if not card_comp or not card_comp.get("card1_attrs") or not card_comp.get("card2_attrs"):
            issues["missing_card_data"] += 1

        # Check reasoning
        if not ann.get("reasoning") or len(ann.get("reasoning", "")) < 20:
            issues["missing_reasoning"] += 1

        # Check thinking
        if not ann.get("thinking") or len(ann.get("thinking", "")) < 10:
            issues["missing_thinking"] += 1

        # Check graph features
        if not ann.get("graph_features"):
            issues["missing_graph_features"] += 1

    return issues


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze annotation quality")
    parser.add_argument(
        "--annotation-path",
        type=Path,
        default=Path("annotations/integrated_all.jsonl"),
        help="Path to annotation file (JSONL)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for analysis report (JSON)",
    )
    parser.add_argument(
        "--game",
        type=str,
        help="Filter by game",
    )

    args = parser.parse_args()

    if not args.annotation_path.exists():
        print(f"Error: Annotation file not found: {args.annotation_path}")
        return 1

    # Load annotations
    print("Loading annotations...")
    annotations = []
    with open(args.annotation_path) as f:
        for line in f:
            if line.strip():
                try:
                    ann = json.loads(line)
                    if args.game:
                        if ann.get("game", "").lower() != args.game.lower():
                            continue
                    annotations.append(ann)
                except json.JSONDecodeError:
                    continue

    print(f"Loaded {len(annotations)} annotations")

    # Analyze
    print("\nAnalyzing quality...")

    overall_dist = analyze_score_distribution(annotations)
    by_source = analyze_by_source(annotations)
    by_game = analyze_by_game(annotations)
    issues = analyze_quality_issues(annotations)

    # Print summary
    print("\n" + "=" * 80)
    print("ANNOTATION QUALITY ANALYSIS")
    print("=" * 80)

    print("\nOverall Score Distribution:")
    print(f"  Count: {overall_dist['count']}")
    print(f"  Mean: {overall_dist['mean']:.3f}")
    print(f"  Range: {overall_dist['min']:.3f} - {overall_dist['max']:.3f}")
    print(f"  Std Dev: {overall_dist['std_dev']:.3f}")
    print(f"  Diversity: {overall_dist['diversity']:.3f}")
    print(f"  Range Utilization: {overall_dist['range_utilization']:.3f}")

    print("\n  Score Ranges:")
    for range_name, count in overall_dist["ranges"].items():
        pct = (count / overall_dist["count"] * 100) if overall_dist["count"] > 0 else 0
        print(f"    {range_name}: {count} ({pct:.1f}%)")

    print("\nBy Source:")
    for source, data in sorted(by_source.items(), key=lambda x: -x[1]["count"]):
        print(f"  {source}:")
        print(f"    Count: {data['count']}")
        print(f"    Mean Score: {data['score_distribution'].get('mean', 0):.3f}")
        print(f"    Diversity: {data['score_distribution'].get('diversity', 0):.3f}")

    print("\nBy Game (All Games Analyzed):")
    # Ensure we analyze all known games, even if they have 0 annotations
    known_games = ["magic", "pokemon", "yugioh", "riftbound", "unknown"]
    for game in known_games:
        if game in by_game:
            data = by_game[game]
            print(f"  {game.upper()}:")
            print(f"    Count: {data['count']}")
            print(f"    Mean Score: {data['score_distribution'].get('mean', 0):.3f}")
            print(f"    Diversity: {data['score_distribution'].get('diversity', 0):.3f}")
            # Show score distribution
            ranges = data["score_distribution"].get("ranges", {})
            if ranges:
                print("    Distribution:")
                for range_name, count in ranges.items():
                    pct = (count / data["count"] * 100) if data["count"] > 0 else 0
                    print(f"      {range_name}: {count} ({pct:.1f}%)")
        else:
            # Game has no annotations yet
            print(f"  {game.upper()}:")
            print("    Count: 0 (no annotations yet)")

    # Also show any other games found
    other_games = [g for g in by_game.keys() if g.lower() not in [kg.lower() for kg in known_games]]
    for game in other_games:
        data = by_game[game]
        print(f"  {game.upper()}:")
        print(f"    Count: {data['count']}")
        print(f"    Mean Score: {data['score_distribution'].get('mean', 0):.3f}")
        print(f"    Diversity: {data['score_distribution'].get('diversity', 0):.3f}")

    print("\nQuality Issues:")
    total = len(annotations)
    for issue, count in issues.items():
        pct = (count / total * 100) if total > 0 else 0
        print(f"  {issue}: {count}/{total} ({pct:.1f}%)")

    # Save report
    report = {
        "overall": overall_dist,
        "by_source": {k: v for k, v in by_source.items()},
        "by_game": {k: v for k, v in by_game.items()},
        "issues": issues,
        "total_annotations": len(annotations),
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n✓ Report saved to {args.output}")
    else:
        print("\n(Use --output to save report)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
