#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Compare annotation quality before and after fixes to prove improvements.

Analyzes:
1. Score distribution (clustering reduction)
2. Field completeness (card_comparison, reasoning, thinking)
3. Score diversity improvements
4. Mean score shifts (especially for Magic)
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.path_setup import setup_project_paths

    setup_project_paths()
except ImportError:
    # If ml module not available, continue without it
    pass


def load_annotations(file_path: Path) -> list[dict[str, Any]]:
    """Load annotations from JSONL file."""
    annotations = []
    if not file_path.exists():
        return annotations

    with open(file_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ann = json.loads(line)
                annotations.append(ann)
            except json.JSONDecodeError:
                continue
    return annotations


def analyze_score_distribution(
    annotations: list[dict[str, Any]], game: str | None = None
) -> dict[str, Any]:
    """Analyze score distribution and clustering."""
    if game:
        game_anns = [a for a in annotations if a.get("game", "").lower() == game.lower()]
    else:
        game_anns = annotations

    if not game_anns:
        return {}

    scores = [a.get("similarity_score", 0.0) for a in game_anns if "similarity_score" in a]
    if not scores:
        return {}

    # Score ranges
    ranges = {
        "0.0-0.2": sum(1 for s in scores if 0.0 <= s < 0.2),
        "0.2-0.4": sum(1 for s in scores if 0.2 <= s < 0.4),
        "0.4-0.6": sum(1 for s in scores if 0.4 <= s < 0.6),
        "0.6-0.8": sum(1 for s in scores if 0.6 <= s < 0.8),
        "0.8-1.0": sum(1 for s in scores if 0.8 <= s <= 1.0),
    }

    # Calculate diversity (std dev)
    import statistics

    diversity = statistics.stdev(scores) if len(scores) > 1 else 0.0

    # Clustering detection
    low_cluster_pct = ranges["0.0-0.2"] / len(scores) * 100 if scores else 0
    high_cluster_pct = ranges["0.8-1.0"] / len(scores) * 100 if scores else 0

    return {
        "count": len(scores),
        "mean": statistics.mean(scores) if scores else 0.0,
        "median": statistics.median(scores) if scores else 0.0,
        "diversity": diversity,
        "min": min(scores) if scores else 0.0,
        "max": max(scores) if scores else 0.0,
        "ranges": ranges,
        "range_percentages": {k: v / len(scores) * 100 if scores else 0 for k, v in ranges.items()},
        "low_cluster_pct": low_cluster_pct,
        "high_cluster_pct": high_cluster_pct,
    }


def analyze_field_completeness(
    annotations: list[dict[str, Any]], game: str | None = None
) -> dict[str, Any]:
    """Analyze field completeness."""
    if game:
        game_anns = [a for a in annotations if a.get("game", "").lower() == game.lower()]
    else:
        game_anns = annotations

    if not game_anns:
        return {}

    total = len(game_anns)

    # Check card_comparison
    has_card_comparison = sum(1 for a in game_anns if a.get("card_comparison"))
    has_meaningful_card_data = sum(
        1
        for a in game_anns
        if a.get("card_comparison")
        and a.get("card_comparison", {}).get("card1_attrs")
        and a.get("card_comparison", {}).get("card2_attrs")
    )

    # Check reasoning
    has_reasoning = sum(
        1
        for a in game_anns
        if a.get("reasoning") and len(str(a.get("reasoning", "")).strip()) >= 10
    )

    # Check thinking
    has_thinking = sum(
        1 for a in game_anns if a.get("thinking") and len(str(a.get("thinking", "")).strip()) >= 10
    )

    return {
        "total": total,
        "card_comparison": {
            "has_field": has_card_comparison,
            "coverage": has_card_comparison / total * 100 if total > 0 else 0,
            "has_meaningful_data": has_meaningful_card_data,
            "meaningful_coverage": has_meaningful_card_data / total * 100 if total > 0 else 0,
        },
        "reasoning": {
            "has_field": has_reasoning,
            "coverage": has_reasoning / total * 100 if total > 0 else 0,
        },
        "thinking": {
            "has_field": has_thinking,
            "coverage": has_thinking / total * 100 if total > 0 else 0,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze annotation improvements after fixes.")
    parser.add_argument(
        "--annotation-path",
        type=Path,
        default=Path("annotations/integrated_all.jsonl"),
        help="Path to integrated annotations",
    )
    parser.add_argument("--game", type=str, help="Filter by game (magic, pokemon, yugioh)")
    args = parser.parse_args()

    print("=" * 80)
    print("ANNOTATION IMPROVEMENTS ANALYSIS")
    print("=" * 80)
    print()

    annotations = load_annotations(args.annotation_path)
    print(f"Loaded {len(annotations)} total annotations")

    if args.game:
        game_anns = [a for a in annotations if a.get("game", "").lower() == args.game.lower()]
        print(f"Filtered to {len(game_anns)} {args.game} annotations")
        annotations = game_anns

    # Analyze score distribution
    print("\n" + "=" * 80)
    print("SCORE DISTRIBUTION ANALYSIS")
    print("=" * 80)

    for game in ["magic", "pokemon", "yugioh"]:
        game_stats = analyze_score_distribution(annotations, game)
        if not game_stats:
            continue

        print(f"\n{game.upper()}:")
        print(f"  Count: {game_stats['count']}")
        print(f"  Mean: {game_stats['mean']:.3f}")
        print(f"  Diversity (std): {game_stats['diversity']:.3f}")
        print(f"  Range: {game_stats['min']:.3f} - {game_stats['max']:.3f}")
        print("  Score Distribution:")
        for range_name, pct in game_stats["range_percentages"].items():
            print(f"    {range_name}: {pct:.1f}% ({game_stats['ranges'][range_name]} annotations)")

        # Clustering analysis
        if game_stats["low_cluster_pct"] > 60:
            print(f"  ⚠️  LOW CLUSTERING: {game_stats['low_cluster_pct']:.1f}% in 0.0-0.2 range")
        elif game_stats["high_cluster_pct"] > 60:
            print(f"  ⚠️  HIGH CLUSTERING: {game_stats['high_cluster_pct']:.1f}% in 0.8-1.0 range")
        else:
            print("  ✅ Good distribution (no extreme clustering)")

    # Overall stats
    overall_stats = analyze_score_distribution(annotations)
    if overall_stats:
        print("\nOVERALL:")
        print(f"  Count: {overall_stats['count']}")
        print(f"  Mean: {overall_stats['mean']:.3f}")
        print(f"  Diversity: {overall_stats['diversity']:.3f}")

    # Analyze field completeness
    print("\n" + "=" * 80)
    print("FIELD COMPLETENESS ANALYSIS")
    print("=" * 80)

    for game in ["magic", "pokemon", "yugioh"]:
        completeness = analyze_field_completeness(annotations, game)
        if not completeness or completeness["total"] == 0:
            continue

        print(f"\n{game.upper()}:")
        print(f"  Total: {completeness['total']}")
        print("  card_comparison:")
        print(
            f"    Has field: {completeness['card_comparison']['has_field']}/{completeness['total']} ({completeness['card_comparison']['coverage']:.1f}%)"
        )
        print(
            f"    Has meaningful data: {completeness['card_comparison']['has_meaningful_data']}/{completeness['total']} ({completeness['card_comparison']['meaningful_coverage']:.1f}%)"
        )
        print("  reasoning:")
        print(
            f"    Has field (>=10 chars): {completeness['reasoning']['has_field']}/{completeness['total']} ({completeness['reasoning']['coverage']:.1f}%)"
        )
        print("  thinking:")
        print(
            f"    Has field (>=10 chars): {completeness['thinking']['has_field']}/{completeness['total']} ({completeness['thinking']['coverage']:.1f}%)"
        )

        # Check if all fields are present
        all_complete = (
            completeness["card_comparison"]["has_field"] == completeness["total"]
            and completeness["reasoning"]["has_field"] == completeness["total"]
            and completeness["thinking"]["has_field"] == completeness["total"]
        )
        if all_complete:
            print("  ✅ All required fields present!")
        else:
            print("  ⚠️  Some fields missing")

    # Overall completeness
    overall_completeness = analyze_field_completeness(annotations)
    if overall_completeness:
        print("\nOVERALL:")
        print(f"  card_comparison: {overall_completeness['card_comparison']['coverage']:.1f}%")
        print(f"  reasoning: {overall_completeness['reasoning']['coverage']:.1f}%")
        print(f"  thinking: {overall_completeness['thinking']['coverage']:.1f}%")

    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
