#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai",
#     "pandas",
# ]
# ///
"""
Standalone meta-judge script for evaluating annotation files.

Can be run on existing annotation files to get quality feedback.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add src to path
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

try:
    from ml.annotation.meta_judge import meta_judge_annotations
    HAS_META_JUDGE = True
except ImportError as e:
    HAS_META_JUDGE = False
    print(f"Error: {e}")


async def main():
    parser = argparse.ArgumentParser(description="Meta-judge annotation files for quality")
    parser.add_argument(
        "annotation_file",
        type=Path,
        help="Annotation file to evaluate (JSONL)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for meta-judgment (JSON)",
    )
    parser.add_argument(
        "--game",
        type=str,
        help="Game name (auto-detected from file if not provided)",
    )

    args = parser.parse_args()

    if not HAS_META_JUDGE:
        print("Error: Meta-judge not available")
        return 1

    if not args.annotation_file.exists():
        print(f"Error: File not found: {args.annotation_file}")
        return 1

    # Load annotations
    annotations = []
    with open(args.annotation_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ann = json.loads(line)
                annotations.append(ann)
            except json.JSONDecodeError:
                continue

    if not annotations:
        print(f"Error: No valid annotations found in {args.annotation_file}")
        return 1

    # Detect game if not provided
    game = args.game
    if not game:
        # Try to detect from annotations
        games = set(ann.get("game") for ann in annotations if ann.get("game"))
        if len(games) == 1:
            game = list(games)[0]
        else:
            game = "unknown"

    print(f"Meta-judging {len(annotations)} annotations for {game}...")
    print("=" * 80)

    # Run meta-judge
    judgment = await meta_judge_annotations(
        annotations,
        game=game,
        batch_id=args.annotation_file.stem,
    )

    # Print results
    print(f"\nOverall Quality: {judgment.overall_quality:.2f}")
    print(f"\nMetrics:")
    print(f"  Score Diversity: {judgment.metrics.score_diversity:.2f}")
    print(f"  Score Range Utilization: {judgment.metrics.score_range_utilization:.2f}")
    print(f"  Reasoning Quality: {judgment.metrics.reasoning_quality:.2f}")
    print(f"  Consistency: {judgment.metrics.consistency_score:.2f}")
    print(f"  Completeness: {judgment.metrics.completeness:.2f}")

    if judgment.issues:
        print(f"\nIssues ({len(judgment.issues)}):")
        for issue in judgment.issues:
            print(f"  [{issue.severity}/4] {issue.issue_type}: {issue.description}")
            if issue.suggested_fix:
                print(f"    Fix: {issue.suggested_fix}")

    if judgment.strengths:
        print(f"\nStrengths:")
        for strength in judgment.strengths:
            print(f"  - {strength}")

    if judgment.recommendations:
        print(f"\nRecommendations:")
        for rec in judgment.recommendations:
            print(f"  - {rec}")

    print(f"\nFeedback:")
    print(judgment.feedback)

    # Save output
    if args.output:
        output_data = {
            "overall_quality": judgment.overall_quality,
            "metrics": judgment.metrics.model_dump(),
            "issues": [issue.model_dump() for issue in judgment.issues],
            "strengths": judgment.strengths,
            "feedback": judgment.feedback,
            "context_injections": judgment.context_injections,
            "recommendations": judgment.recommendations,
            "timestamp": judgment.model_dump().get("timestamp", ""),
        }
        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\nSaved meta-judgment to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

