#!/usr/bin/env python3
"""
Analyze quality trends over time from tracking data.

Shows quality metrics, source distribution changes, and recommendations.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.annotation_tracking import AnnotationTracker

    HAS_TRACKING = True
except ImportError:
    HAS_TRACKING = False
    print("Warning: Tracking not available")


def analyze_quality_trends(tracking_file: Path) -> dict[str, Any]:
    """Analyze quality trends from tracking data."""
    if not HAS_TRACKING:
        return {"error": "Tracking not available"}
    
    tracker = AnnotationTracker(tracking_file)
    
    quality_history = tracker.get_quality_trend()
    source_dist = tracker.get_source_distribution()
    summary = tracker.get_summary()
    
    # Analyze trends
    if len(quality_history) >= 2:
        first = quality_history[0]
        latest = quality_history[-1]
        
        quality_change = latest["quality_score"] - first["quality_score"]
        annotation_growth = latest["total_annotations"] - first["total_annotations"]
        
        trend = "improving" if quality_change > 0 else "declining" if quality_change < 0 else "stable"
    else:
        quality_change = 0
        annotation_growth = 0
        trend = "insufficient_data"
    
    return {
        "summary": summary,
        "source_distribution": source_dist,
        "quality_trend": trend,
        "quality_change": quality_change,
        "annotation_growth": annotation_growth,
        "quality_history": quality_history[-10:],  # Last 10 snapshots
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze annotation quality trends")
    parser.add_argument(
        "--tracking-file",
        type=Path,
        default=Path("annotations") / "tracking.json",
        help="Path to tracking file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file for analysis results",
    )
    
    args = parser.parse_args()
    
    if not args.tracking_file.exists():
        print(f"Error: Tracking file not found: {args.tracking_file}")
        return 1
    
    print("=" * 80)
    print("QUALITY TRENDS ANALYSIS")
    print("=" * 80)
    print()
    
    analysis = analyze_quality_trends(args.tracking_file)
    
    if "error" in analysis:
        print(f"Error: {analysis['error']}")
        return 1
    
    # Display results
    print("SUMMARY")
    print("-" * 80)
    summary = analysis["summary"]
    print(f"Total sources: {summary['total_sources']}")
    print(f"Quality snapshots: {summary['quality_snapshots']}")
    
    if summary["latest_quality"]:
        latest = summary["latest_quality"]
        print(f"\nLatest Quality Snapshot:")
        print(f"  Timestamp: {latest['timestamp']}")
        print(f"  Quality Score: {latest['quality_score']:.2f}")
        print(f"  Total Annotations: {latest['total_annotations']}")
        print(f"  Issues: {latest['issues_count']}")
        print(f"  Warnings: {latest['warnings_count']}")
    
    print(f"\nQuality Trend: {analysis['quality_trend']}")
    if analysis['quality_change'] != 0:
        change_str = f"{analysis['quality_change']:+.2f}"
        print(f"Quality Change: {change_str}")
    print(f"Annotation Growth: {analysis['annotation_growth']:+d}")
    
    print("\nSOURCE DISTRIBUTION")
    print("-" * 80)
    for source, count in analysis["source_distribution"].items():
        print(f"  {source}: {count}")
    
    if analysis["quality_history"]:
        print("\nRECENT QUALITY HISTORY")
        print("-" * 80)
        for snapshot in analysis["quality_history"][-5:]:
            print(
                f"  {snapshot['timestamp'][:19]}: "
                f"score={snapshot['quality_score']:.2f}, "
                f"annotations={snapshot['total_annotations']}, "
                f"issues={snapshot['issues_count']}"
            )
    
    # Save if requested
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(analysis, f, indent=2)
        print(f"\n✓ Saved analysis to {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


