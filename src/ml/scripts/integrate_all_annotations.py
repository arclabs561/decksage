#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///
"""
Integrate all annotation types into training and evaluation.

Handles:
1. LLM annotations (JSONL) - annotations/*_llm_annotations.jsonl
2. Hand annotations (YAML) - annotations/hand_batch_*.yaml
3. LLM judgments (JSONL) - annotations/judgment_*.jsonl (unified format)
   - Backward compatibility: annotations/llm_judgments/judgment_*.json (old format)
4. S3-synced annotations - s3://games-collections/annotations/

Converts all to:
- Substitution pairs (for training)
- Test sets (for evaluation)
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    yaml = None

import sys

script_dir = Path(__file__).parent
src_dir = script_dir.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ml.utils.annotation_utils import (
    convert_annotations_to_substitution_pairs,
    convert_judgments_to_annotations,
    extract_substitution_pairs_from_annotations,
    load_judgment_files,
    load_similarity_annotations,
)
from ml.utils.paths import PATHS




def find_all_annotation_files(annotations_dir: Path) -> dict[str, list[Path]]:
    """Find all annotation files by type."""
    files = {
        "llm_jsonl": [],
        "hand_yaml": [],
        "judgments": [],
    }

    # LLM annotations (JSONL)
    for jsonl_file in annotations_dir.glob("*_llm_annotations.jsonl"):
        files["llm_jsonl"].append(jsonl_file)

    # Hand annotations (YAML)
    for yaml_file in annotations_dir.glob("hand_batch_*.yaml"):
        files["hand_yaml"].append(yaml_file)

    # LLM judgments (JSONL - unified format)
    # New format: judgment_*.jsonl in main annotations directory
    for jsonl_file in annotations_dir.glob("judgment_*.jsonl"):
        files["judgments"].append(jsonl_file)

    # Backward compatibility: old format in llm_judgments/ subdirectory
    judgments_dir = annotations_dir / "llm_judgments"
    if judgments_dir.exists():
        for json_file in judgments_dir.glob("judgment_*.json"):
            files["judgments"].append(json_file)

    return files


def integrate_all_annotations(
    annotations_dir: Path | None = None,
    output_substitution_pairs: Path | None = None,
    output_test_set: Path | None = None,
    min_similarity: float = 0.8,
    min_relevance: int = 4,
) -> dict[str, Any]:
    """Integrate all annotation types into unified outputs."""
    # Use PATHS utility for default annotations directory
    if annotations_dir is None:
        annotations_dir = PATHS.annotations

    print("=" * 70)
    print("INTEGRATING ALL ANNOTATION TYPES")
    print("=" * 70)
    print()

    # Find all annotation files
    all_files = find_all_annotation_files(annotations_dir)
    print(f"Found annotation files:")
    print(f"  LLM annotations (JSONL): {len(all_files['llm_jsonl'])}")
    print(f"  Hand annotations (YAML): {len(all_files['hand_yaml'])}")
    print(f"  LLM judgments (JSONL/JSON): {len(all_files['judgments'])}")
    print()

    # Load all annotations
    all_annotations = []
    seen_pairs: set[tuple[str, str]] = set()  # Track duplicates: (card1, card2)

    # Load LLM annotations (JSONL)
    for jsonl_file in all_files["llm_jsonl"]:
        print(f"Loading LLM annotations: {jsonl_file.name}...")
        annotations = load_similarity_annotations(jsonl_file)
        # Deduplicate: only add if not seen before
        new_count = 0
        for ann in annotations:
            pair = tuple(sorted([ann.get("card1", ""), ann.get("card2", "")]))
            if pair[0] and pair[1] and pair not in seen_pairs:
                all_annotations.append(ann)
                seen_pairs.add(pair)
                new_count += 1
        print(f"  Loaded {len(annotations)} annotations ({new_count} new, {len(annotations) - new_count} duplicates skipped)")

    # Load hand annotations (YAML)
    for yaml_file in all_files["hand_yaml"]:
        print(f"Loading hand annotations: {yaml_file.name}...")
        annotations = load_similarity_annotations(yaml_file)
        # Deduplicate
        new_count = 0
        for ann in annotations:
            pair = tuple(sorted([ann.get("card1", ""), ann.get("card2", "")]))
            if pair[0] and pair[1] and pair not in seen_pairs:
                all_annotations.append(ann)
                seen_pairs.add(pair)
                new_count += 1
        print(f"  Loaded {len(annotations)} annotations ({new_count} new)")

    # Load judgments (JSONL or JSON for backward compatibility)
    judgment_files = all_files["judgments"]
    if judgment_files:
        print(f"Loading LLM judgments ({len(judgment_files)} files)...")
        judgment_annotations = []

        for judgment_file in judgment_files:
            if judgment_file.suffix == ".jsonl":
                # New format: Already in annotation format (JSONL)
                print(f"  Loading annotations from {judgment_file.name}...")
                annotations = load_similarity_annotations(judgment_file)
                # Deduplicate
                new_count = 0
                for ann in annotations:
                    pair = tuple(sorted([ann.get("card1", ""), ann.get("card2", "")]))
                    if pair[0] and pair[1] and pair not in seen_pairs:
                        judgment_annotations.append(ann)
                        seen_pairs.add(pair)
                        new_count += 1
                print(f"    Added {new_count} new annotations (skipped {len(annotations) - new_count} duplicates)")
            else:
                # Old format: JSON judgment, need conversion
                print(f"  Converting judgment from {judgment_file.name}...")
                # Load just this file (more efficient than loading all)
                try:
                    with open(judgment_file) as f:
                        single_judgment = json.load(f)
                    converted = convert_judgments_to_annotations([single_judgment])
                    # Deduplicate
                    new_count = 0
                    for ann in converted:
                        pair = tuple(sorted([ann.get("card1", ""), ann.get("card2", "")]))
                        if pair[0] and pair[1] and pair not in seen_pairs:
                            judgment_annotations.append(ann)
                            seen_pairs.add(pair)
                            new_count += 1
                    print(f"    Added {new_count} new annotations (skipped {len(converted) - new_count} duplicates)")
                except Exception as e:
                    print(f"    Warning: Failed to convert {judgment_file.name}: {e}")
                    continue

        all_annotations.extend(judgment_annotations)
        print(f"  Loaded {len(judgment_annotations)} unique annotations from judgments")

    print()
    print(f"Total annotations loaded: {len(all_annotations)}")
    print()

    # Convert to substitution pairs
    pairs: list[tuple[str, str]] = []
    if output_substitution_pairs:
        print("Converting to substitution pairs...")
        # Extract pairs from loaded annotations
        pairs = extract_substitution_pairs_from_annotations(
            all_annotations,
            min_similarity=min_similarity,
            min_relevance=min_relevance,
            require_substitute_flag=True,
        )

        # Save pairs with atomic write
        output_substitution_pairs.parent.mkdir(parents=True, exist_ok=True)
        pairs_list = [[card1, card2] for card1, card2 in pairs]
        temp_path = output_substitution_pairs.with_suffix(output_substitution_pairs.suffix + ".tmp")
        try:
            with open(temp_path, "w") as f:
                json.dump(pairs_list, f, indent=2)
            temp_path.replace(output_substitution_pairs)
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise
        print(f"  Saved {len(pairs)} substitution pairs to {output_substitution_pairs}")

    # Convert to test set format
    test_set: dict[str, Any] = {"queries": {}}
    if output_test_set:
        print("Converting to test set format...")

        # Group by query card
        by_query = defaultdict(list)
        for ann in all_annotations:
            query = ann.get("card1")
            candidate = ann.get("card2")
            similarity_score = ann.get("similarity_score", 0.0)
            if query and candidate:
                by_query[query].append((candidate, similarity_score))

        # Convert to test set buckets
        for query, candidates in by_query.items():
            buckets = {
                "highly_relevant": [],
                "relevant": [],
                "somewhat_relevant": [],
                "marginally_relevant": [],
                "irrelevant": [],
            }

            # Deduplicate candidates (same card might appear multiple times with different scores)
            candidate_scores: dict[str, float] = {}
            for candidate, score in candidates:
                # Keep highest score if duplicate
                if candidate not in candidate_scores or score > candidate_scores[candidate]:
                    candidate_scores[candidate] = score

            for candidate, score in candidate_scores.items():
                # Validate and clamp score
                try:
                    score = max(0.0, min(1.0, float(score)))
                except (ValueError, TypeError):
                    score = 0.0
                
                # Convert similarity_score (0-1) to relevance (0-4)
                # Use consistent conversion function from annotation_utils
                from ml.utils.annotation_utils import convert_similarity_score_to_relevance
                relevance = convert_similarity_score_to_relevance(score, scale="0-4")
                relevance = max(0, min(4, relevance))  # Clamp to valid range

                if relevance >= 4:
                    buckets["highly_relevant"].append(candidate)
                elif relevance >= 3:
                    buckets["relevant"].append(candidate)
                elif relevance >= 2:
                    buckets["somewhat_relevant"].append(candidate)
                elif relevance >= 1:
                    buckets["marginally_relevant"].append(candidate)
                else:
                    buckets["irrelevant"].append(candidate)

            test_set["queries"][query] = buckets

        # Save test set with atomic write
        output_test_set.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_test_set.with_suffix(output_test_set.suffix + ".tmp")
        try:
            with open(temp_path, "w") as f:
                json.dump(test_set, f, indent=2)
            temp_path.replace(output_test_set)
        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise
        print(f"  Saved test set with {len(test_set['queries'])} queries to {output_test_set}")

    # Summary - compute pairs count if needed for stats
    pairs_count = 0
    if output_substitution_pairs:
        pairs_count = len(pairs)
    elif output_test_set:
        # Count pairs from test set for stats
        pairs_count = sum(len(buckets.get("highly_relevant", [])) for buckets in test_set["queries"].values())

    stats = {
        "total_annotations": len(all_annotations),
        "llm_jsonl_files": len(all_files["llm_jsonl"]),
        "hand_yaml_files": len(all_files["hand_yaml"]),
        "judgment_files": len(all_files["judgments"]),
        "substitution_pairs": pairs_count,
        "test_set_queries": len(test_set["queries"]) if output_test_set else 0,
    }

    print()
    print("=" * 70)
    print("INTEGRATION COMPLETE")
    print("=" * 70)
    print(f"Total annotations processed: {stats['total_annotations']}")
    if output_substitution_pairs:
        print(f"Substitution pairs created: {stats['substitution_pairs']}")
    if output_test_set:
        print(f"Test set queries created: {stats['test_set_queries']}")

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Integrate all annotation types")
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=None,
        help=f"Directory containing annotation files (default: {PATHS.annotations})",
    )
    parser.add_argument(
        "--output-substitution-pairs",
        type=Path,
        help="Output path for substitution pairs JSON",
    )
    parser.add_argument(
        "--output-test-set",
        type=Path,
        help="Output path for test set JSON",
    )
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=0.8,
        help="Minimum similarity score for substitution pairs (default: 0.8)",
    )
    parser.add_argument(
        "--min-relevance",
        type=int,
        default=4,
        help="Minimum relevance for hand annotations (default: 4)",
    )

    args = parser.parse_args()

    if not args.output_substitution_pairs and not args.output_test_set:
        parser.error("Must specify at least one of --output-substitution-pairs or --output-test-set")

    try:
        stats = integrate_all_annotations(
            annotations_dir=args.annotations_dir,
            output_substitution_pairs=args.output_substitution_pairs,
            output_test_set=args.output_test_set,
            min_similarity=args.min_similarity,
            min_relevance=args.min_relevance,
        )
        return 0
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

