#!/usr/bin/env python3
"""
Annotation analytics and insights.

Provides detailed analytics on annotation quality, coverage, trends, and patterns.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def analyze_annotation_coverage(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze coverage of annotations."""
    cards = set()
    pairs = set()
    sources = Counter()
    games = Counter()
    
    for ann in annotations:
        card1 = ann.get("card1", "")
        card2 = ann.get("card2", "")
        if card1:
            cards.add(card1)
        if card2:
            cards.add(card2)
        if card1 and card2:
            pairs.add(tuple(sorted([card1, card2])))
        
        sources[ann.get("source", "unknown")] += 1
        games[ann.get("game", "unknown")] += 1
    
    return {
        "unique_cards": len(cards),
        "unique_pairs": len(pairs),
        "total_annotations": len(annotations),
        "sources": dict(sources),
        "games": dict(games),
        "avg_annotations_per_card": len(annotations) / len(cards) if cards else 0,
    }


def analyze_quality_distribution(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze quality score distribution."""
    scores = [ann.get("similarity_score", 0) for ann in annotations]
    substitutes = [ann.get("is_substitute", False) for ann in annotations]
    
    if not scores:
        return {}
    
    score_ranges = {
        "high": sum(1 for s in scores if s >= 0.8),
        "medium": sum(1 for s in scores if 0.5 <= s < 0.8),
        "low": sum(1 for s in scores if s < 0.5),
    }
    
    return {
        "min_score": min(scores),
        "max_score": max(scores),
        "avg_score": sum(scores) / len(scores),
        "median_score": sorted(scores)[len(scores) // 2],
        "score_distribution": score_ranges,
        "substitute_rate": sum(substitutes) / len(substitutes) if substitutes else 0,
        "total_substitutes": sum(substitutes),
    }


def analyze_temporal_trends(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze temporal trends in annotations."""
    timestamps = []
    for ann in annotations:
        ts = ann.get("timestamp")
        if ts:
            try:
                if isinstance(ts, str):
                    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                else:
                    timestamps.append(ts)
            except Exception:
                pass
    
    if not timestamps:
        return {}
    
    timestamps.sort()
    
    # Group by day
    daily_counts = Counter()
    for ts in timestamps:
        day = ts.date()
        daily_counts[day] += 1
    
    return {
        "first_annotation": timestamps[0].isoformat() if timestamps else None,
        "last_annotation": timestamps[-1].isoformat() if timestamps else None,
        "total_days": len(daily_counts),
        "avg_per_day": len(timestamps) / len(daily_counts) if daily_counts else 0,
        "daily_counts": {str(k): v for k, v in sorted(daily_counts.items())},
    }


def analyze_source_agreement(annotations: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze agreement between different annotation sources."""
    # Group by card pair
    pairs = defaultdict(list)
    for ann in annotations:
        card1 = ann.get("card1", "")
        card2 = ann.get("card2", "")
        if card1 and card2:
            pair = tuple(sorted([card1, card2]))
            pairs[pair].append(ann)
    
    # Find pairs with multiple sources
    multi_source_pairs = {k: v for k, v in pairs.items() if len(v) > 1}
    
    agreements = []
    disagreements = []
    
    for pair, anns in multi_source_pairs.items():
        sources = [ann.get("source") for ann in anns]
        scores = [ann.get("similarity_score", 0) for ann in anns]
        
        # Check agreement (within 0.1)
        score_range = max(scores) - min(scores)
        if score_range <= 0.1:
            agreements.append({
                "pair": pair,
                "sources": sources,
                "scores": scores,
                "range": score_range,
            })
        else:
            disagreements.append({
                "pair": pair,
                "sources": sources,
                "scores": scores,
                "range": score_range,
            })
    
    return {
        "total_pairs": len(pairs),
        "multi_source_pairs": len(multi_source_pairs),
        "agreements": len(agreements),
        "disagreements": len(disagreements),
        "agreement_rate": len(agreements) / len(multi_source_pairs) if multi_source_pairs else 0,
        "sample_agreements": agreements[:5],
        "sample_disagreements": disagreements[:5],
    }


def generate_analytics_report(
    annotations: list[dict[str, Any]],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Generate comprehensive analytics report."""
    print("=" * 80)
    print("ANNOTATION ANALYTICS")
    print("=" * 80)
    print()
    
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_annotations": len(annotations),
    }
    
    # Coverage analysis
    print("Analyzing coverage...")
    coverage = analyze_annotation_coverage(annotations)
    report["coverage"] = coverage
    print(f"  Unique cards: {coverage['unique_cards']}")
    print(f"  Unique pairs: {coverage['unique_pairs']}")
    print(f"  Sources: {coverage['sources']}")
    
    # Quality distribution
    print("\nAnalyzing quality distribution...")
    quality = analyze_quality_distribution(annotations)
    report["quality"] = quality
    if quality:
        print(f"  Avg score: {quality['avg_score']:.3f}")
        print(f"  Substitute rate: {quality['substitute_rate']:.2%}")
        print(f"  Score distribution: {quality['score_distribution']}")
    
    # Temporal trends
    print("\nAnalyzing temporal trends...")
    trends = analyze_temporal_trends(annotations)
    report["temporal"] = trends
    if trends:
        print(f"  First annotation: {trends.get('first_annotation')}")
        print(f"  Last annotation: {trends.get('last_annotation')}")
        print(f"  Avg per day: {trends.get('avg_per_day', 0):.1f}")
    
    # Source agreement
    print("\nAnalyzing source agreement...")
    agreement = analyze_source_agreement(annotations)
    report["agreement"] = agreement
    if agreement:
        print(f"  Multi-source pairs: {agreement['multi_source_pairs']}")
        print(f"  Agreement rate: {agreement['agreement_rate']:.2%}")
        print(f"  Disagreements: {agreement['disagreements']}")
    
    # Save report (atomic write)
    if output_path:
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        try:
            with open(temp_path, "w") as f:
                json.dump(report, f, indent=2)
            temp_path.replace(output_path)
            print(f"\n✓ Saved analytics report: {output_path}")
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise
    
    return report


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate annotation analytics")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input integrated annotations JSONL file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output analytics report JSON file",
    )
    
    args = parser.parse_args()
    
    # Load annotations
    annotations = []
    errors = []
    with open(args.input) as f:
        for line_num, line in enumerate(f, 1):
            if line.strip():
                try:
                    annotations.append(json.loads(line))
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {e}")
                    continue
                except Exception as e:
                    errors.append(f"Line {line_num}: Error - {e}")
                    continue
    
    if errors:
        print(f"⚠ {len(errors)} errors encountered while loading:")
        for error in errors[:5]:
            print(f"  {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more errors")
        print()
    
    # Generate report
    output_path = args.output or args.input.parent / f"{args.input.stem}_analytics.json"
    generate_analytics_report(annotations, output_path)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

