#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Convert similarity annotations to training data format.

This script:
1. Loads similarity annotations (from integrated_all.jsonl or individual files)
2. Filters out test set cards (prevents data leakage)
3. Converts to training example format
4. Saves in format ready for training scripts
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def convert_annotation_to_training_example(annotation: dict[str, Any]) -> dict[str, Any] | None:
    """Convert similarity annotation to training example format."""
    card1 = annotation.get("card1")
    card2 = annotation.get("card2")
    similarity_score = annotation.get("similarity_score", 0.0)
    similarity_type = annotation.get("similarity_type", "functional")
    is_substitute = annotation.get("is_substitute", False)
    source = annotation.get("source", "unknown")
    game = annotation.get("game", "unknown")

    if not card1 or not card2:
        return None

    # Create training example
    example = {
        "card1": card1,
        "card2": card2,
        "similarity_score": float(similarity_score),
        "similarity_type": similarity_type,
        "is_substitute": bool(is_substitute),
        "source": source,
        "game": game,
        # Include metadata for tracking
        "metadata": {
            "model_name": annotation.get("model_name"),
            "annotator_id": annotation.get("annotator_id"),
            "timestamp": annotation.get("timestamp"),
            "reasoning": annotation.get("reasoning", "")[:200],  # Truncate for size
        },
    }

    # Add weight based on source (higher quality = higher weight)
    if "agentic" in source or "multi_annotator" in source:
        example["weight"] = 1.5  # Multi-annotator consensus is higher quality
    elif source == "hand":
        example["weight"] = 2.0  # Hand annotations are highest quality
    elif source == "user_feedback":
        example["weight"] = 2.0  # User feedback is highest quality
    else:
        example["weight"] = 1.0  # Default weight

    return example


def convert_annotations_to_training_data(
    annotation_path: Path,
    output_path: Path,
    min_score: float = 0.0,
    filter_test_cards: bool = True,
    game: str | None = None,
) -> dict[str, Any]:
    """Convert annotations to training data format."""
    print("=" * 80)
    print("CONVERTING ANNOTATIONS TO TRAINING DATA")
    print("=" * 80)
    print(f"Input: {annotation_path}")
    print(f"Output: {output_path}")
    print(f"Min score: {min_score}")
    print(f"Filter test cards: {filter_test_cards}")
    print()

    # Load annotations
    print("Loading annotations...")
    annotations = []
    with open(annotation_path) as f:
        for line in f:
            if line.strip():
                try:
                    ann = json.loads(line)
                    annotations.append(ann)
                except json.JSONDecodeError:
                    continue

    print(f"  Loaded {len(annotations)} annotations")

    # Filter by game if specified
    if game:
        annotations = [a for a in annotations if a.get("game", "").lower() == game.lower()]
        print(f"  Filtered to {len(annotations)} {game} annotations")

    # Filter test set cards if requested
    if filter_test_cards:
        print("\nFiltering test set cards (preventing data leakage)...")
        try:
            # Add src to path
            project_root = Path(__file__).parent.parent.parent
            src_dir = project_root / "src"
            if str(src_dir) not in sys.path:
                sys.path.insert(0, str(src_dir))

            from ml.utils.annotation_utils import filter_annotations_for_training

            filtered, stats = filter_annotations_for_training(
                annotations,
                test_set_path=None,  # Use default test sets
                game=game,
                strict=True,
            )
            annotations = filtered
            print(f"  Filtered {stats['filtered']} annotations with test set cards")
            print(f"  Remaining: {len(annotations)} annotations safe for training")
        except Exception as e:
            print(f"  ⚠ Could not filter test cards: {e}")
            print("  Proceeding without filtering (WARNING: may cause data leakage)")

    # Convert to training examples
    print("\nConverting to training examples...")
    training_examples = []
    for ann in annotations:
        score = ann.get("similarity_score", 0.0)
        if score < min_score:
            continue

        example = convert_annotation_to_training_example(ann)
        if example:
            training_examples.append(example)

    print(f"  Created {len(training_examples)} training examples (score >= {min_score})")

    # Save training data
    print(f"\nSaving to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for example in training_examples:
            f.write(json.dumps(example) + "\n")

    # Summary statistics
    sources = {}
    games = {}
    score_ranges = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}

    for ex in training_examples:
        source = ex.get("source", "unknown")
        sources[source] = sources.get(source, 0) + 1

        game = ex.get("game", "unknown")
        games[game] = games.get(game, 0) + 1

        score = ex.get("similarity_score", 0.0)
        if score < 0.2:
            score_ranges["0.0-0.2"] += 1
        elif score < 0.4:
            score_ranges["0.2-0.4"] += 1
        elif score < 0.6:
            score_ranges["0.4-0.6"] += 1
        elif score < 0.8:
            score_ranges["0.6-0.8"] += 1
        else:
            score_ranges["0.8-1.0"] += 1

    print("\n" + "=" * 80)
    print("CONVERSION SUMMARY")
    print("=" * 80)
    print(f"Total training examples: {len(training_examples)}")
    print("\nBy source:")
    for source, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {source}: {count}")
    print("\nBy game:")
    for game, count in sorted(games.items(), key=lambda x: -x[1]):
        print(f"  {game}: {count}")
    print("\nBy score range:")
    for range_name, count in sorted(score_ranges.items()):
        print(f"  {range_name}: {count}")

    return {
        "total_examples": len(training_examples),
        "sources": sources,
        "games": games,
        "score_ranges": score_ranges,
        "output_path": str(output_path),
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Convert similarity annotations to training data format"
    )
    parser.add_argument(
        "--annotation-path",
        type=Path,
        default=Path("annotations/integrated_all.jsonl"),
        help="Path to annotation file (JSONL)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/training_data_from_annotations.jsonl"),
        help="Output path for training data",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum similarity score to include (default: 0.0)",
    )
    parser.add_argument(
        "--no-filter-test-cards",
        action="store_true",
        help="Don't filter test set cards (WARNING: may cause data leakage)",
    )
    parser.add_argument(
        "--game",
        type=str,
        help="Filter by game (magic, pokemon, yugioh)",
    )

    args = parser.parse_args()

    if not args.annotation_path.exists():
        print(f"Error: Annotation file not found: {args.annotation_path}")
        return 1

    result = convert_annotations_to_training_data(
        annotation_path=args.annotation_path,
        output_path=args.output,
        min_score=args.min_score,
        filter_test_cards=not args.no_filter_test_cards,
        game=args.game,
    )

    print(f"\n✓ Training data ready: {result['output_path']}")
    print("\nNext steps:")
    print("  1. Use this file with training scripts")
    print("  2. Run validate_training_data.py to verify no leakage")
    print("  3. Check score distribution matches expectations")

    return 0


if __name__ == "__main__":
    sys.exit(main())
