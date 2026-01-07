#!/usr/bin/env python3
"""
Unified annotation quality monitoring dashboard.

Tracks quality metrics across all annotation sources over time.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.annotation.review_annotations import (
    analyze_hand_annotations,
    analyze_llm_annotations,
    analyze_user_feedback,
    analyze_judgment_file,
)


def generate_quality_report(
    annotations_dir: Path,
    output_file: Path | None = None,
) -> dict[str, Any]:
    """Generate comprehensive quality report."""
    print("=" * 80)
    print("ANNOTATION QUALITY MONITORING DASHBOARD")
    print("=" * 80)
    print()
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "sources": {},
        "quality_metrics": {},
        "issues": [],
        "recommendations": [],
    }
    
    # Analyze all sources
    all_stats = []
    
    # Hand annotations
    hand_files = list(annotations_dir.glob("hand_batch_*.yaml"))
    hand_stats = []
    for file_path in sorted(hand_files):
        stats = analyze_hand_annotations(file_path)
        all_stats.append(stats)
        hand_stats.append(stats)
    
    if hand_stats:
        total_queries = sum(s["total_queries"] for s in hand_stats)
        total_candidates = sum(s["total_candidates"] for s in hand_stats)
        total_graded = sum(s["graded_candidates"] for s in hand_stats)
        overall_completion = total_graded / total_candidates if total_candidates > 0 else 0.0
        
        report["sources"]["hand_annotations"] = {
            "total_queries": total_queries,
            "total_candidates": total_candidates,
            "graded": total_graded,
            "completion_rate": overall_completion,
            "files": len(hand_stats),
        }
        
        if overall_completion == 0.0:
            report["issues"].append("All hand annotation batches are empty (0% completion)")
            report["recommendations"].append("Complete at least one batch using browser annotation tool")
    
    # LLM annotations
    llm_files = list(annotations_dir.glob("*_llm_annotations.jsonl"))
    llm_stats = []
    for file_path in sorted(llm_files):
        stats = analyze_llm_annotations(file_path)
        all_stats.append(stats)
        llm_stats.append(stats)
    
    if llm_stats:
        total_llm = sum(s["total"] for s in llm_stats if "total" in s)
        uniform_score_issues = sum(1 for s in llm_stats if s.get("issues"))
        
        report["sources"]["llm_annotations"] = {
            "total": total_llm,
            "files": len(llm_stats),
            "uniform_score_issues": uniform_score_issues,
        }
        
        if uniform_score_issues > 0:
            report["issues"].append(f"{uniform_score_issues} LLM annotation files have uniform scores (suspicious)")
            report["recommendations"].append("Regenerate LLM annotations using generate_llm_annotations.py")
    
    # User feedback
    feedback_dir = project_root / "data" / "annotations"
    feedback_files = list(feedback_dir.glob("user_feedback*.jsonl"))
    feedback_stats = []
    for file_path in sorted(feedback_files):
        stats = analyze_user_feedback(file_path)
        all_stats.append(stats)
        feedback_stats.append(stats)
    
    if feedback_stats:
        total_feedback = sum(s["total"] for s in feedback_stats if "total" in s)
        
        report["sources"]["user_feedback"] = {
            "total": total_feedback,
            "files": len(feedback_stats),
        }
    
    # Judgment files
    judgment_dir = annotations_dir / "llm_judgments"
    if judgment_dir.exists():
        judgment_files = list(judgment_dir.glob("*.json"))
        judgment_stats = []
        for file_path in sorted(judgment_files):
            stats = analyze_judgment_file(file_path)
            all_stats.append(stats)
            judgment_stats.append(stats)
        
        if judgment_stats:
            uniform_issues = sum(1 for s in judgment_stats if s.get("issues"))
            
            report["sources"]["llm_judgments"] = {
                "total_files": len(judgment_stats),
                "uniform_score_issues": uniform_issues,
            }
            
            if uniform_issues > 0:
                report["issues"].append(f"{uniform_issues} judgment files have uniform scores")
    
    # Compute overall quality score
    quality_score = 1.0
    
    # Penalize for empty hand annotations
    if report["sources"].get("hand_annotations", {}).get("completion_rate", 1.0) == 0.0:
        quality_score -= 0.3
    
    # Penalize for uniform LLM scores
    if report["sources"].get("llm_annotations", {}).get("uniform_score_issues", 0) > 0:
        quality_score -= 0.2
    
    # Penalize for judgment issues
    if report["sources"].get("llm_judgments", {}).get("uniform_score_issues", 0) > 0:
        quality_score -= 0.2
    
    quality_score = max(0.0, min(1.0, quality_score))
    
    report["quality_metrics"] = {
        "overall_score": quality_score,
        "total_sources": len(report["sources"]),
        "total_issues": len(report["issues"]),
    }
    
    # Print report
    print("QUALITY METRICS")
    print("-" * 80)
    print(f"Overall Quality Score: {quality_score:.2f}")
    print(f"Total Sources: {len(report['sources'])}")
    print(f"Total Issues: {len(report['issues'])}")
    print()
    
    print("SOURCE BREAKDOWN")
    print("-" * 80)
    for source, data in report["sources"].items():
        print(f"\n{source}:")
        for key, value in data.items():
            print(f"  {key}: {value}")
    
    if report["issues"]:
        print("\nISSUES")
        print("-" * 80)
        for issue in report["issues"]:
            print(f"  ⚠ {issue}")
    
    if report["recommendations"]:
        print("\nRECOMMENDATIONS")
        print("-" * 80)
        for rec in report["recommendations"]:
            print(f"  → {rec}")
    
    # Save report
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n✓ Saved quality report: {output_file}")
    
    return report


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Annotation quality monitoring dashboard"
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=project_root / "annotations",
        help="Annotations directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON report file",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode: regenerate report when files change",
    )
    
    args = parser.parse_args()
    
    if args.watch:
        print("Watch mode not yet implemented")
        return 1
    
    report = generate_quality_report(args.annotations_dir, args.output)
    
    return 0 if report["quality_metrics"]["overall_score"] >= 0.7 else 1


if __name__ == "__main__":
    sys.exit(main())

