#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
Integrate user feedback into training pipeline.

Converts feedback annotations to training examples and adds them to training data.
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


def convert_to_training_example(annotation: dict) -> dict | None:
    """Convert feedback annotation to training example format."""
    card1 = annotation.get("card1")
    card2 = annotation.get("card2")
    similarity_score = annotation.get("similarity_score", 0.0)
    similarity_type = annotation.get("similarity_type", "substitute")
    is_substitute = annotation.get("is_substitute", False)
    
    if not card1 or not card2:
        return None
    
    # Create training example
    example = {
        "card1": card1,
        "card2": card2,
        "similarity_score": similarity_score,
        "similarity_type": similarity_type,
        "is_substitute": is_substitute,
        "source": "user_feedback",
        "weight": 2.0,  # Higher weight for user feedback (more reliable)
        "metadata": annotation.get("feedback_metadata", {}),
    }
    
    return example


def integrate_feedback(
    feedback_path: Path,
    training_data_path: Path | None = None,
    output_path: Path | None = None,
    min_rating: float = 0.5,
) -> dict:
    """Integrate feedback into training data."""
    
    # Load feedback
    feedback_annotations = load_feedback_annotations(feedback_path)
    print(f"Loaded {len(feedback_annotations)} feedback annotations")
    
    # Convert to training examples
    training_examples = []
    for annotation in feedback_annotations:
        example = convert_to_training_example(annotation)
        if example and example["similarity_score"] >= min_rating:
            training_examples.append(example)
    
    print(f"Created {len(training_examples)} training examples (score >= {min_rating})")
    
    # Load existing training data if provided
    existing_examples = []
    if training_data_path and training_data_path.exists():
        with open(training_data_path) as f:
            if training_data_path.suffix == ".jsonl":
                for line in f:
                    if line.strip():
                        existing_examples.append(json.loads(line))
            else:
                data = json.load(f)
                existing_examples = data.get("examples", data.get("pairs", []))
        print(f"Loaded {len(existing_examples)} existing training examples")
    
    # Merge (feedback examples first, higher weight)
    all_examples = training_examples + existing_examples
    
    # Save
    if output_path is None:
        output_path = PATHS.experiments / "training_data_with_feedback.jsonl"
    
    with open(output_path, "w") as f:
        for example in all_examples:
            f.write(json.dumps(example) + "\n")
    
    print(f"\nIntegrated training data:")
    print(f"  Feedback examples: {len(training_examples)}")
    print(f"  Existing examples: {len(existing_examples)}")
    print(f"  Total examples: {len(all_examples)}")
    print(f"  Saved to {output_path}")
    
    return {
        "feedback_examples": len(training_examples),
        "existing_examples": len(existing_examples),
        "total_examples": len(all_examples),
        "output_path": str(output_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Integrate user feedback into training")
    parser.add_argument(
        "--feedback",
        type=str,
        default=str(PATHS.data / "annotations" / "user_feedback_annotations.jsonl"),
        help="Path to feedback annotations JSONL",
    )
    parser.add_argument(
        "--training-data",
        type=str,
        help="Path to existing training data (optional)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output path (default: training_data_with_feedback.jsonl)",
    )
    parser.add_argument(
        "--min-rating",
        type=float,
        default=0.5,
        help="Minimum similarity score to include (default: 0.5)",
    )
    
    args = parser.parse_args()
    
    result = integrate_feedback(
        Path(args.feedback),
        Path(args.training_data) if args.training_data else None,
        Path(args.output) if args.output else None,
        min_rating=args.min_rating,
    )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

