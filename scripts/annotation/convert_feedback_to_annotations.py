#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pathlib",
# ]
# ///
"""
Convert user feedback (from API) to unified annotation format.

User feedback format (user_feedback.jsonl):
{
    "query_card": str,
    "suggested_card": str,
    "task_type": str,
    "rating": int (0-4),
    "is_substitute": bool,
    "timestamp": str,
    "feedback_id": str,
    "session_id": str,
    "context": dict
}

Converts to unified annotation format (JSONL):
{
    "card1": str,
    "card2": str,
    "similarity_score": float (0-1),
    "similarity_type": str,
    "is_substitute": bool,
    "source": "user_feedback",
    "reasoning": str,
    "feedback_metadata": {
        "rating": int,
        "task_type": str,
        "session_id": str,
        "timestamp": str,
        "feedback_id": str
    }
}
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths
from ml.utils.paths import PATHS
from ml.utils.annotation_utils import convert_relevance_to_similarity_score

setup_project_paths()


def convert_feedback_to_annotation(feedback: dict) -> dict:
    """Convert single feedback entry to annotation format."""
    query_card = feedback.get("query_card", "")
    suggested_card = feedback.get("suggested_card", "")
    rating = feedback.get("rating", 0)
    is_substitute = feedback.get("is_substitute", False)
    task_type = feedback.get("task_type", "similarity")
    context = feedback.get("context", {})

    # Convert rating (0-4) to similarity_score (0-1)
    similarity_score = convert_relevance_to_similarity_score(rating, scale="0-4")

    # Infer similarity_type from rating
    if rating >= 4:
        similarity_type = "substitute"
    elif rating >= 3:
        similarity_type = "functional"
    elif rating >= 2:
        similarity_type = "synergy"
    elif rating >= 1:
        similarity_type = "related"
    else:
        similarity_type = "unrelated"

    # Build reasoning
    reasoning_parts = [f"User rating: {rating}/4"]
    if is_substitute:
        reasoning_parts.append("Marked as substitute")
    if context.get("similarity"):
        reasoning_parts.append(f"Model similarity: {context.get('similarity'):.2f}")
    reasoning = ". ".join(reasoning_parts)

    annotation = {
        "card1": query_card,
        "card2": suggested_card,
        "similarity_score": similarity_score,
        "similarity_type": similarity_type,
        "is_substitute": is_substitute,
        "source": "user_feedback",
        "reasoning": reasoning,
        "feedback_metadata": {
            "rating": rating,
            "task_type": task_type,
            "session_id": feedback.get("session_id"),
            "timestamp": feedback.get("timestamp"),
            "feedback_id": feedback.get("feedback_id"),
            "user_id": feedback.get("user_id"),
            "context": context,
        },
    }

    return annotation


def convert_feedback_file(
    feedback_path: Path,
    output_path: Path | None = None,
    min_rating: int = 0,
) -> list[dict]:
    """Convert feedback JSONL file to annotation JSONL format."""
    if not feedback_path.exists():
        print(f"Feedback file not found: {feedback_path}")
        return []

    annotations = []
    with open(feedback_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                feedback = json.loads(line)
                rating = feedback.get("rating", 0)
                if rating >= min_rating:
                    annotation = convert_feedback_to_annotation(feedback)
                    annotations.append(annotation)
            except json.JSONDecodeError as e:
                print(f"Skipping malformed line: {e}")
                continue

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write for annotations
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                for ann in annotations:
                    f.write(json.dumps(ann, ensure_ascii=False) + "\n")
            temp_path.replace(output_path)
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise
        print(f"Converted {len(annotations)} feedback entries to {output_path}")

    return annotations


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert user feedback to unified annotation format"
    )
    parser.add_argument(
        "--feedback",
        type=Path,
        default=PATHS.data / "annotations" / "user_feedback.jsonl",
        help="Path to user feedback JSONL file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PATHS.data / "annotations" / "user_feedback_annotations.jsonl",
        help="Output path for annotations JSONL",
    )
    parser.add_argument(
        "--min-rating",
        type=int,
        default=0,
        help="Minimum rating to include (0-4)",
    )

    args = parser.parse_args()

    annotations = convert_feedback_file(
        args.feedback,
        args.output,
        min_rating=args.min_rating,
    )

    print(f"Total annotations: {len(annotations)}")
    if annotations:
        rating_dist = {}
        substitute_count = 0
        for ann in annotations:
            rating = ann["feedback_metadata"]["rating"]
            rating_dist[rating] = rating_dist.get(rating, 0) + 1
            if ann["is_substitute"]:
                substitute_count += 1

        print(f"\nRating distribution:")
        for rating in sorted(rating_dist.keys()):
            print(f"  {rating}: {rating_dist[rating]}")
        print(f"\nSubstitutes: {substitute_count}/{len(annotations)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

