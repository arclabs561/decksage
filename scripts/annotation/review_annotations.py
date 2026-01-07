#!/usr/bin/env python3
"""Review and analyze annotation quality across all annotation files."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def analyze_hand_annotations(file_path: Path) -> dict:
    """Analyze hand annotation YAML file."""
    with open(file_path) as f:
        data = yaml.safe_load(f)

    tasks = data.get("tasks", [])
    metadata = data.get("metadata", {})

    stats = {
        "file": str(file_path),
        "game": metadata.get("game", "unknown"),
        "total_queries": len(tasks),
        "total_candidates": 0,
        "graded_candidates": 0,
        "ungraded_candidates": 0,
        "relevance_distribution": Counter(),
        "queries_completed": 0,
        "queries_partial": 0,
        "queries_empty": 0,
        "has_enhanced_fields": False,
        "validation_errors": [],
    }

    for task in tasks:
        query = task.get("query", "unknown")
        candidates = task.get("candidates", [])
        stats["total_candidates"] += len(candidates)

        graded_count = 0
        for cand in candidates:
            relevance = cand.get("relevance")
            if relevance is None:
                stats["ungraded_candidates"] += 1
            else:
                stats["graded_candidates"] += 1
                graded_count += 1
                try:
                    rel_int = int(relevance)
                    if 0 <= rel_int <= 4:
                        stats["relevance_distribution"][rel_int] += 1
                    else:
                        stats["validation_errors"].append(
                            f"{query}: Invalid relevance {rel_int} (must be 0-4)"
                        )
                except (ValueError, TypeError):
                    stats["validation_errors"].append(
                        f"{query}: Non-numeric relevance '{relevance}'"
                    )

            # Check for enhanced fields
            if any(
                cand.get(field) is not None
                for field in [
                    "similarity_type",
                    "is_substitute",
                    "role_match",
                    "archetype_context",
                ]
            ):
                stats["has_enhanced_fields"] = True

        if graded_count == len(candidates) and len(candidates) > 0:
            stats["queries_completed"] += 1
        elif graded_count > 0:
            stats["queries_partial"] += 1
        else:
            stats["queries_empty"] += 1

    stats["completion_rate"] = (
        stats["graded_candidates"] / stats["total_candidates"]
        if stats["total_candidates"] > 0
        else 0.0
    )

    return stats


def analyze_user_feedback(file_path: Path) -> dict:
    """Analyze user feedback JSONL file."""
    annotations = []
    errors = []
    with open(file_path) as f:
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

    if not annotations:
        return {
            "file": str(file_path),
            "type": "user_feedback",
            "total": 0,
            "error": "Empty file",
        }

    rating_dist = Counter()
    substitute_dist = Counter()
    task_type_dist = Counter()
    authors = Counter()
    sessions = Counter()

    for ann in annotations:
        rating_dist[ann.get("rating", "missing")] += 1
        substitute_dist[ann.get("is_substitute", "missing")] += 1
        task_type_dist[ann.get("task_type", "missing")] += 1
        context = ann.get("context", {})
        authors[context.get("author", "unknown")] += 1
        sessions[ann.get("session_id", "unknown")] += 1

    stats = {
        "file": str(file_path),
        "type": "user_feedback",
        "total": len(annotations),
        "rating_distribution": dict(rating_dist),
        "substitute_distribution": dict(substitute_dist),
        "task_type_distribution": dict(task_type_dist),
        "authors": dict(authors),
        "unique_sessions": len(sessions),
    }

    # Check for issues
    issues = []
    if len(rating_dist) == 1:
        issues.append(f"All feedback has same rating: {list(rating_dist.keys())[0]}")
    if len(annotations) < 5:
        issues.append("Very few feedback entries (< 5)")

    stats["issues"] = issues
    return stats


def analyze_llm_annotations(file_path: Path) -> dict:
    """Analyze LLM annotation JSONL file."""
    annotations = []
    errors = []
    with open(file_path) as f:
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

    if not annotations:
        return {
            "file": str(file_path),
            "type": "llm_jsonl",
            "total": 0,
            "error": "Empty file",
        }

    # Analyze structure
    relevance_dist = Counter()
    similarity_dist = Counter()
    substitute_dist = Counter()
    confidence_dist = []
    games = Counter()

    for ann in annotations:
        relevance_dist[ann.get("relevance", "missing")] += 1
        similarity_dist[ann.get("similarity", "missing")] += 1
        substitute_dist[ann.get("is_substitute", "missing")] += 1
        games[ann.get("game", "missing")] += 1
        if "confidence" in ann:
            conf = ann["confidence"]
            if isinstance(conf, (int, float)):
                confidence_dist.append(conf)

    stats = {
        "file": str(file_path),
        "type": "llm_jsonl",
        "total": len(annotations),
        "relevance_distribution": dict(relevance_dist),
        "similarity_distribution": dict(similarity_dist),
        "substitute_distribution": dict(substitute_dist),
        "games": dict(games),
        "avg_confidence": (
            sum(confidence_dist) / len(confidence_dist) if confidence_dist else None
        ),
    }

    # Check for suspicious patterns
    issues = []
    if len(relevance_dist) == 1:
        issues.append(f"All annotations have same relevance: {list(relevance_dist.keys())[0]}")
    if len(similarity_dist) == 1:
        issues.append(f"All annotations have same similarity: {list(similarity_dist.keys())[0]}")
    if stats["avg_confidence"] and stats["avg_confidence"] == 0.7:
        issues.append("All confidence scores are 0.7 (suspicious default value)")

    stats["issues"] = issues
    return stats


def analyze_judgment_file(file_path: Path) -> dict:
    """Analyze LLM judgment JSON file."""
    with open(file_path) as f:
        data = json.load(f)

    evaluations = data.get("evaluations", [])
    bias_checks = data.get("bias_checks", {})

    relevance_dist = Counter()
    confidence_dist = []
    method_votes = Counter()

    for eval_item in evaluations:
        relevance_dist[eval_item.get("relevance", "missing")] += 1
        if "confidence" in eval_item:
            conf = eval_item["confidence"]
            if isinstance(conf, (int, float)):
                confidence_dist.append(conf)
        for method in eval_item.get("method_votes", []):
            method_votes[method] += 1

    stats = {
        "file": str(file_path),
        "type": "judgment_json",
        "query_card": data.get("query_card", "unknown"),
        "total_evaluations": len(evaluations),
        "relevance_distribution": dict(relevance_dist),
        "methods_used": data.get("methods_used", []),
        "method_votes": dict(method_votes),
        "bias_flags": {
            "groupthink_candidates": len(bias_checks.get("groupthink_candidates", [])),
            "low_confidence": len(bias_checks.get("low_confidence", [])),
        },
        "avg_confidence": (
            sum(confidence_dist) / len(confidence_dist) if confidence_dist else None
        ),
    }

    # Check for issues
    issues = []
    if len(relevance_dist) == 1:
        issues.append(
            f"All evaluations have same relevance: {list(relevance_dist.keys())[0]}"
        )
    if stats["bias_flags"]["groupthink_candidates"] == len(evaluations):
        issues.append("All candidates flagged for groupthink (suspicious)")
    if stats["avg_confidence"] == 1.0:
        issues.append("All confidence scores are 1.0 (suspicious)")

    stats["issues"] = issues
    return stats


def main() -> int:
    """Review all annotation files."""
    annotations_dir = project_root / "annotations"

    print("=" * 80)
    print("ANNOTATION REVIEW")
    print("=" * 80)
    print()

    all_stats = []

    # Analyze hand annotation YAML files
    hand_files = list(annotations_dir.glob("hand_batch_*.yaml"))
    if hand_files:
        print("HAND ANNOTATIONS (YAML)")
        print("-" * 80)
        for file_path in sorted(hand_files):
            stats = analyze_hand_annotations(file_path)
            all_stats.append(stats)

            print(f"\n{file_path.name}")
            print(f"  Game: {stats['game']}")
            print(f"  Queries: {stats['total_queries']}")
            print(f"  Candidates: {stats['total_candidates']}")
            print(f"  Completion: {stats['graded_candidates']}/{stats['total_candidates']} ({stats['completion_rate']:.1%})")
            print(f"  Queries completed: {stats['queries_completed']}")
            print(f"  Queries partial: {stats['queries_partial']}")
            print(f"  Queries empty: {stats['queries_empty']}")
            if stats["relevance_distribution"]:
                print(f"  Relevance distribution: {dict(stats['relevance_distribution'])}")
            if stats["has_enhanced_fields"]:
                print(f"  ✓ Has enhanced fields (similarity_type, is_substitute, etc.)")
            if stats["validation_errors"]:
                print(f"  ⚠ Validation errors: {len(stats['validation_errors'])}")
                for err in stats["validation_errors"][:5]:
                    print(f"    - {err}")
            if stats["completion_rate"] == 0.0:
                print(f"  ⚠ No annotations completed")
        print()

    # Analyze user feedback files
    feedback_files = list((project_root / "data" / "annotations").glob("user_feedback*.jsonl"))
    if feedback_files:
        print("USER FEEDBACK (JSONL)")
        print("-" * 80)
        for file_path in sorted(feedback_files):
            stats = analyze_user_feedback(file_path)
            all_stats.append(stats)

            print(f"\n{file_path.name}")
            print(f"  Total feedback: {stats['total']}")
            if "error" in stats:
                print(f"  ⚠ {stats['error']}")
            else:
                print(f"  Rating distribution: {stats['rating_distribution']}")
                print(f"  Task types: {stats['task_type_distribution']}")
                print(f"  Authors: {stats['authors']}")
                print(f"  Unique sessions: {stats['unique_sessions']}")
                if stats["issues"]:
                    print(f"  ⚠ Issues:")
                    for issue in stats["issues"]:
                        print(f"    - {issue}")
        print()

    # Analyze LLM annotation JSONL files
    llm_files = list(annotations_dir.glob("*_llm_annotations.jsonl"))
    if llm_files:
        print("LLM ANNOTATIONS (JSONL)")
        print("-" * 80)
        for file_path in sorted(llm_files):
            stats = analyze_llm_annotations(file_path)
            all_stats.append(stats)

            print(f"\n{file_path.name}")
            print(f"  Total annotations: {stats['total']}")
            if "error" in stats:
                print(f"  ⚠ {stats['error']}")
            else:
                print(f"  Relevance distribution: {stats['relevance_distribution']}")
                print(f"  Games: {stats['games']}")
                if stats["avg_confidence"]:
                    print(f"  Avg confidence: {stats['avg_confidence']:.2f}")
                if stats["issues"]:
                    print(f"  ⚠ Issues:")
                    for issue in stats["issues"]:
                        print(f"    - {issue}")
        print()

    # Analyze judgment files
    judgment_files = list((annotations_dir / "llm_judgments").glob("*.json"))
    if judgment_files:
        print("LLM JUDGMENTS (JSON)")
        print("-" * 80)
        for file_path in sorted(judgment_files):
            stats = analyze_judgment_file(file_path)
            all_stats.append(stats)

            print(f"\n{file_path.name}")
            print(f"  Query: {stats['query_card']}")
            print(f"  Evaluations: {stats['total_evaluations']}")
            print(f"  Relevance distribution: {stats['relevance_distribution']}")
            print(f"  Methods used: {stats['methods_used']}")
            print(f"  Bias flags: {stats['bias_flags']}")
            if stats["issues"]:
                print(f"  ⚠ Issues:")
                for issue in stats["issues"]:
                    print(f"    - {issue}")
        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    hand_stats = [s for s in all_stats if "completion_rate" in s]
    if hand_stats:
        total_queries = sum(s["total_queries"] for s in hand_stats)
        total_candidates = sum(s["total_candidates"] for s in hand_stats)
        total_graded = sum(s["graded_candidates"] for s in hand_stats)
        overall_completion = (
            total_graded / total_candidates if total_candidates > 0 else 0.0
        )

        print(f"\nHand Annotations:")
        print(f"  Total queries: {total_queries}")
        print(f"  Total candidates: {total_candidates}")
        print(f"  Graded: {total_graded} ({overall_completion:.1%})")
        print(f"  Completed queries: {sum(s['queries_completed'] for s in hand_stats)}")
        print(f"  Empty queries: {sum(s['queries_empty'] for s in hand_stats)}")

    feedback_stats = [s for s in all_stats if s.get("type") == "user_feedback"]
    if feedback_stats:
        total_feedback = sum(s["total"] for s in feedback_stats)
        print(f"\nUser Feedback:")
        print(f"  Total feedback entries: {total_feedback}")

    llm_stats = [s for s in all_stats if s.get("type") == "llm_jsonl"]
    if llm_stats:
        total_llm = sum(s["total"] for s in llm_stats)
        print(f"\nLLM Annotations:")
        print(f"  Total annotations: {total_llm}")

    judgment_stats = [s for s in all_stats if s.get("type") == "judgment_json"]
    if judgment_stats:
        print(f"\nJudgment Files:")
        print(f"  Total files: {len(judgment_stats)}")

    # Key issues
    print(f"\n⚠ KEY ISSUES:")
    issues_found = False

    for stats in all_stats:
        if "completion_rate" in stats and stats["completion_rate"] == 0.0:
            print(f"  - {Path(stats['file']).name}: No annotations completed")
            issues_found = True
        if stats.get("issues"):
            for issue in stats["issues"]:
                print(f"  - {Path(stats['file']).name}: {issue}")
                issues_found = True
        if stats.get("validation_errors"):
            print(f"  - {Path(stats['file']).name}: {len(stats['validation_errors'])} validation errors")
            issues_found = True

    if not issues_found:
        print("  None found")

    return 0


if __name__ == "__main__":
    sys.exit(main())

