#!/usr/bin/env python3
"""
Analyze quality trends across annotation batches.

Tracks meta-judge scores, issues, and recommendations over time.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime

# Add src to path
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def load_meta_judgments(annotations_dir: Path) -> list[dict]:
    """Load all meta-judgment files."""
    judgments = []
    for judgment_file in annotations_dir.glob("*_meta_judgment.json"):
        try:
            with open(judgment_file) as f:
                data = json.load(f)
                # Extract game from filename
                game = judgment_file.stem.replace("_meta_judgment", "")
                data["game"] = game
                data["file"] = str(judgment_file)
                judgments.append(data)
        except Exception as e:
            print(f"Warning: Could not load {judgment_file}: {e}")
    return judgments


def analyze_trends(judgments: list[dict]) -> dict:
    """Analyze quality trends across batches."""
    trends = {
        "overall": {
            "quality_scores": [],
            "avg_quality": 0.0,
            "quality_trend": "stable",  # improving, declining, stable
        },
        "by_game": defaultdict(lambda: {
            "quality_scores": [],
            "issues": defaultdict(list),
            "recommendations": [],
        }),
        "common_issues": defaultdict(int),
        "common_recommendations": defaultdict(int),
        "metrics_trends": {
            "score_diversity": [],
            "reasoning_quality": [],
            "completeness": [],
        },
    }

    for judgment in judgments:
        quality = judgment.get("overall_quality", 0.0)
        trends["overall"]["quality_scores"].append(quality)
        game = judgment.get("game", "unknown")
        trends["by_game"][game]["quality_scores"].append(quality)

        # Track issues
        for issue in judgment.get("issues", []):
            issue_type = issue.get("issue_type", "unknown")
            trends["common_issues"][issue_type] += 1
            trends["by_game"][game]["issues"][issue_type].append(issue.get("severity", 0))

        # Track recommendations
        for rec in judgment.get("recommendations", []):
            trends["common_recommendations"][rec] += 1
            trends["by_game"][game]["recommendations"].append(rec)

        # Track metrics
        metrics = judgment.get("metrics", {})
        if metrics:
            trends["metrics_trends"]["score_diversity"].append(metrics.get("score_diversity", 0.0))
            trends["metrics_trends"]["reasoning_quality"].append(metrics.get("reasoning_quality", 0.0))
            trends["metrics_trends"]["completeness"].append(metrics.get("completeness", 0.0))

    # Calculate averages
    if trends["overall"]["quality_scores"]:
        trends["overall"]["avg_quality"] = sum(trends["overall"]["quality_scores"]) / len(trends["overall"]["quality_scores"])
        
        # Determine trend
        if len(trends["overall"]["quality_scores"]) >= 2:
            recent = trends["overall"]["quality_scores"][-3:]  # Last 3
            older = trends["overall"]["quality_scores"][:-3] if len(trends["overall"]["quality_scores"]) > 3 else []
            if older:
                recent_avg = sum(recent) / len(recent)
                older_avg = sum(older) / len(older)
                if recent_avg > older_avg + 0.1:
                    trends["overall"]["quality_trend"] = "improving"
                elif recent_avg < older_avg - 0.1:
                    trends["overall"]["quality_trend"] = "declining"
                else:
                    trends["overall"]["quality_trend"] = "stable"

    # Calculate game averages
    for game, data in trends["by_game"].items():
        if data["quality_scores"]:
            data["avg_quality"] = sum(data["quality_scores"]) / len(data["quality_scores"])

    return trends


def print_report(trends: dict):
    """Print quality trends report."""
    print("=" * 80)
    print("ANNOTATION QUALITY TRENDS REPORT")
    print("=" * 80)

    # Overall quality
    print(f"\nOverall Quality:")
    print(f"  Average: {trends['overall']['avg_quality']:.2f}")
    print(f"  Trend: {trends['overall']['quality_trend']}")
    print(f"  Batches analyzed: {len(trends['overall']['quality_scores'])}")
    if trends['overall']['quality_scores']:
        print(f"  Range: {min(trends['overall']['quality_scores']):.2f} - {max(trends['overall']['quality_scores']):.2f}")

    # By game
    print(f"\nQuality by Game:")
    for game, data in sorted(trends["by_game"].items()):
        if data["quality_scores"]:
            print(f"  {game.upper()}:")
            print(f"    Average: {data.get('avg_quality', 0.0):.2f}")
            print(f"    Batches: {len(data['quality_scores'])}")
            print(f"    Range: {min(data['quality_scores']):.2f} - {max(data['quality_scores']):.2f}")

    # Common issues
    print(f"\nMost Common Issues:")
    for issue_type, count in sorted(trends["common_issues"].items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {issue_type}: {count} occurrences")

    # Common recommendations
    print(f"\nMost Common Recommendations:")
    for rec, count in sorted(trends["common_recommendations"].items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {rec}: {count} occurrences")

    # Metrics trends
    print(f"\nMetrics Trends:")
    for metric, values in trends["metrics_trends"].items():
        if values:
            print(f"  {metric}:")
            print(f"    Average: {sum(values) / len(values):.2f}")
            print(f"    Range: {min(values):.2f} - {max(values):.2f}")
            if len(values) >= 2:
                recent = values[-3:] if len(values) >= 3 else values
                older = values[:-3] if len(values) > 3 else []
                if older:
                    recent_avg = sum(recent) / len(recent)
                    older_avg = sum(older) / len(older)
                    change = recent_avg - older_avg
                    direction = "↑" if change > 0 else "↓" if change < 0 else "→"
                    print(f"    Trend: {direction} {change:+.2f}")


def main():
    parser = argparse.ArgumentParser(description="Analyze annotation quality trends")
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Directory containing annotation files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for trends JSON",
    )

    args = parser.parse_args()

    if not args.annotations_dir.exists():
        print(f"Error: Directory not found: {args.annotations_dir}")
        return 1

    # Load all meta-judgments
    judgments = load_meta_judgments(args.annotations_dir)
    
    if not judgments:
        print(f"No meta-judgment files found in {args.annotations_dir}")
        return 1

    print(f"Loaded {len(judgments)} meta-judgment files")

    # Analyze trends
    trends = analyze_trends(judgments)

    # Print report
    print_report(trends)

    # Save output
    if args.output:
        with open(args.output, "w") as f:
            json.dump(trends, f, indent=2, ensure_ascii=False)
        print(f"\nSaved trends to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

