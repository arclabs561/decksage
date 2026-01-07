#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Expand test set using high-quality user feedback.

Converts feedback with rating >= 3 to test set entries.
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths

setup_project_paths()

from ml.utils.paths import PATHS


def load_feedback_annotations(feedback_path: Path) -> list[dict]:
    """Load feedback annotations."""
    annotations = []
    if not feedback_path.exists():
        return annotations
    
    with open(feedback_path) as f:
        for line in f:
            if line.strip():
                try:
                    annotations.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    
    return annotations


def convert_feedback_to_test_set_entry(annotation: dict) -> dict | None:
    """Convert feedback annotation to test set entry format."""
    card1 = annotation.get("card1")
    card2 = annotation.get("card2")
    similarity_score = annotation.get("similarity_score", 0.0)
    similarity_type = annotation.get("similarity_type", "substitute")
    is_substitute = annotation.get("is_substitute", False)
    
    if not card1 or not card2:
        return None
    
    # Only use high-quality feedback (rating >= 3, score >= 0.75)
    if similarity_score < 0.75:
        return None
    
    # Determine relevance level based on score
    if similarity_score >= 0.9:
        relevance_level = "highly_relevant"
    elif similarity_score >= 0.8:
        relevance_level = "relevant"
    elif similarity_score >= 0.75:
        relevance_level = "somewhat_relevant"
    else:
        return None
    
    return {
        "card1": card1,
        "card2": card2,
        "relevance_level": relevance_level,
        "similarity_type": similarity_type,
        "is_substitute": is_substitute,
        "source": "user_feedback",
        "feedback_metadata": annotation.get("feedback_metadata", {}),
    }


def expand_test_set(
    test_set_path: Path,
    feedback_path: Path,
    output_path: Path | None = None,
    min_rating: float = 0.75,
) -> dict:
    """Expand test set with feedback entries."""
    
    # Load existing test set
    with open(test_set_path) as f:
        test_set = json.load(f)
    
    queries = test_set.get("queries", test_set) if isinstance(test_set, dict) else test_set
    
    # Load feedback annotations
    feedback_annotations = load_feedback_annotations(feedback_path)
    print(f"Loaded {len(feedback_annotations)} feedback annotations")
    
    # Convert feedback to test set entries
    new_entries = []
    for annotation in feedback_annotations:
        entry = convert_feedback_to_test_set_entry(annotation)
        if entry:
            # Check similarity_score from original annotation
            similarity_score = annotation.get("similarity_score", 0.0)
            if similarity_score >= min_rating:
                new_entries.append(entry)
    
    print(f"Found {len(new_entries)} high-quality feedback entries (score >= {min_rating})")
    
    # Group by query card
    query_groups = {}
    for entry in new_entries:
        query = entry["card1"]
        if query not in query_groups:
            query_groups[query] = {
                "highly_relevant": [],
                "relevant": [],
                "somewhat_relevant": [],
                "marginally_relevant": [],
                "irrelevant": [],
            }
        
        relevance_level = entry["relevance_level"]
        candidate = entry["card2"]
        
        # Avoid duplicates
        if candidate not in query_groups[query][relevance_level]:
            query_groups[query][relevance_level].append(candidate)
    
    # Merge into test set
    added_queries = 0
    updated_queries = 0
    
    for query, labels in query_groups.items():
        if query not in queries:
            # New query - create entry
            queries[query] = {
                "type": "unknown",
                "sources": ["user_feedback"],
                "highly_relevant": labels["highly_relevant"],
                "relevant": labels["relevant"],
                "somewhat_relevant": labels["somewhat_relevant"],
                "marginally_relevant": labels["marginally_relevant"],
                "irrelevant": labels["irrelevant"],
            }
            added_queries += 1
        else:
            # Existing query - merge labels
            existing = queries[query]
            for level in ["highly_relevant", "relevant", "somewhat_relevant"]:
                for candidate in labels[level]:
                    if candidate not in existing.get(level, []):
                        if level not in existing:
                            existing[level] = []
                        existing[level].append(candidate)
            
            # Update sources
            if "sources" not in existing:
                existing["sources"] = []
            if "user_feedback" not in existing["sources"]:
                existing["sources"].append("user_feedback")
            
            updated_queries += 1
    
    # Prepare output
    if isinstance(test_set, dict) and "queries" in test_set:
        test_set["queries"] = queries
        output_data = test_set
    else:
        output_data = {"version": "unified_v1", "game": "magic", "queries": queries}
    
    # Save
    if output_path is None:
        output_path = test_set_path.parent / f"{test_set_path.stem}_expanded.json"
    
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"\nExpanded test set:")
    print(f"  Added {added_queries} new queries")
    print(f"  Updated {updated_queries} existing queries")
    print(f"  Total queries: {len(queries)}")
    print(f"  Saved to {output_path}")
    
    return {
        "added_queries": added_queries,
        "updated_queries": updated_queries,
        "total_queries": len(queries),
        "output_path": str(output_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Expand test set from user feedback")
    parser.add_argument(
        "--test-set",
        type=str,
        default=str(PATHS.test_magic),
        help="Path to test set JSON",
    )
    parser.add_argument(
        "--feedback",
        type=str,
        default=str(PATHS.data / "annotations" / "user_feedback_annotations.jsonl"),
        help="Path to feedback annotations JSONL",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output path (default: test_set_expanded.json)",
    )
    parser.add_argument(
        "--min-rating",
        type=float,
        default=0.75,
        help="Minimum similarity score to include (default: 0.75)",
    )
    
    args = parser.parse_args()
    
    result = expand_test_set(
        Path(args.test_set),
        Path(args.feedback),
        Path(args.output) if args.output else None,
        min_rating=args.min_rating,
    )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

