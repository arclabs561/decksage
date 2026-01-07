#!/usr/bin/env python3
"""
Comprehensive annotation integration from all sources.

Integrates:
1. Hand annotations (YAML)
2. LLM annotations (JSONL)
3. UI feedback (JSONL)
4. Multi-judge annotations
5. Multi-perspective annotations
6. Browser-based annotations (via MCP)
7. Synthetic annotations

Validates quality, converts to unified format, and integrates into training/evaluation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.paths import PATHS
except ImportError:
    PATHS = None

# Import annotation_utils directly to avoid pandas dependency
try:
    from ml.utils.annotation_utils import (
        convert_relevance_to_similarity_score,
        load_hand_annotations,
    )
except ImportError:
    # Fallback: try direct import
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'annotation_utils',
        project_root / 'src' / 'ml' / 'utils' / 'annotation_utils.py'
    )
    if spec and spec.loader:
        annotation_utils = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(annotation_utils)
        convert_relevance_to_similarity_score = annotation_utils.convert_relevance_to_similarity_score
        load_hand_annotations = annotation_utils.load_hand_annotations
    else:
        # Final fallback: define minimal version
        def convert_relevance_to_similarity_score(relevance: int, scale: str = "0-4") -> float:
            mapping = {4: 0.95, 3: 0.75, 2: 0.55, 1: 0.35, 0: 0.1}
            return mapping.get(relevance, 0.0)
        
        def load_hand_annotations(path):
            return []


def load_hand_annotations_from_file(file_path: Path) -> list[dict]:
    """Load hand annotations from YAML file."""
    try:
        if PATHS and hasattr(load_hand_annotations, "__call__"):
            return load_hand_annotations(file_path)
    except Exception:
        pass

    # Fallback implementation
    with open(file_path) as f:
        data = yaml.safe_load(f)

    annotations = []
    for task in data.get("tasks", []):
        query = task.get("query", "")
        if not query:
            continue

        for cand in task.get("candidates", []):
            relevance = cand.get("relevance")
            if relevance is None:
                continue

            try:
                rel_int = int(relevance)
                if not (0 <= rel_int <= 4):
                    continue
            except (ValueError, TypeError):
                continue

            card = cand.get("card", "")
            if not card:
                continue

            similarity_score = convert_relevance_to_similarity_score(rel_int, scale="0-4")
            is_substitute = rel_int == 4 and cand.get("similarity_type") == "substitute"

            annotations.append(
                {
                    "card1": query,
                    "card2": card,
                    "similarity_score": similarity_score,
                    "similarity_type": cand.get("similarity_type", "functional"),
                    "is_substitute": is_substitute,
                    "source": "hand_annotation",
                    "relevance": rel_int,
                    "notes": cand.get("notes", ""),
                    "metadata": {
                        "batch_id": data.get("metadata", {}).get("batch_id", "unknown"),
                        "game": data.get("metadata", {}).get("game", "unknown"),
                    },
                }
            )

    return annotations


def load_llm_annotations(file_path: Path) -> list[dict]:
    """Load LLM annotations from JSONL file."""
    annotations = []
    with open(file_path) as f:
        for line in f:
            if line.strip():
                try:
                    ann = json.loads(line)
                    # Normalize field names
                    if "similarity" in ann and "similarity_score" not in ann:
                        ann["similarity_score"] = ann.pop("similarity")
                    # Ensure source is set
                    if "source" not in ann:
                        ann["source"] = "llm_annotation"
                    # Ensure similarity_score is float
                    if "similarity_score" in ann:
                        try:
                            ann["similarity_score"] = float(ann["similarity_score"])
                        except (ValueError, TypeError):
                            # Convert relevance to similarity_score if needed
                            if "relevance" in ann:
                                rel = ann.get("relevance", 0)
                                ann["similarity_score"] = convert_relevance_to_similarity_score(
                                    int(rel) if isinstance(rel, (int, float)) else 0, scale="0-4"
                                )
                            else:
                                ann["similarity_score"] = 0.5  # Default fallback
                    annotations.append(ann)
                except json.JSONDecodeError:
                    continue
    return annotations


def convert_relevance_to_similarity_score(relevance: int, scale: str = "0-4") -> float:
    """Convert relevance score (0-4) to similarity score (0-1)."""
    mapping = {4: 0.95, 3: 0.75, 2: 0.55, 1: 0.35, 0: 0.1}
    return mapping.get(relevance, 0.0)


def load_user_feedback(file_path: Path) -> list[dict]:
    """Load user feedback and convert to annotations."""
    try:
        from scripts.annotation.convert_feedback_to_annotations import (
            convert_feedback_to_annotation,
        )

        annotations = []
        with open(file_path) as f:
            for line in f:
                if line.strip():
                    try:
                        feedback = json.loads(line)
                        ann = convert_feedback_to_annotation(feedback)
                        annotations.append(ann)
                    except json.JSONDecodeError:
                        continue
        return annotations
    except ImportError:
        # Fallback implementation
        annotations = []
        with open(file_path) as f:
            for line in f:
                if line.strip():
                    try:
                        feedback = json.loads(line)
                        rating = feedback.get("rating", 0)
                        similarity_score = convert_relevance_to_similarity_score(
                            rating, scale="0-4"
                        )

                        annotations.append(
                            {
                                "card1": feedback.get("query_card", ""),
                                "card2": feedback.get("suggested_card", ""),
                                "similarity_score": similarity_score,
                                "similarity_type": "functional" if rating >= 3 else "synergy",
                                "is_substitute": feedback.get("is_substitute", False),
                                "source": "user_feedback",
                                "feedback_metadata": {
                                    "rating": rating,
                                    "session_id": feedback.get("session_id"),
                                    "timestamp": feedback.get("timestamp"),
                                },
                            }
                        )
                    except json.JSONDecodeError:
                        continue
        return annotations


def load_multi_judge_annotations(annotations_dir: Path) -> list[dict]:
    """Load multi-judge annotations (from parallel_multi_judge or multi_perspective_judge)."""
    annotations = []

    # Look for judgment files
    judgment_files = list(annotations_dir.glob("judgment_*.jsonl"))
    judgment_files.extend(list((annotations_dir / "llm_judgments").glob("*.json")))

    for file_path in judgment_files:
        try:
            if file_path.suffix == ".jsonl":
                with open(file_path) as f:
                    for line in f:
                        if line.strip():
                            ann = json.loads(line)
                            if "source" not in ann:
                                ann["source"] = "llm_judgment"
                            annotations.append(ann)
            else:
                with open(file_path) as f:
                    data = json.load(f)
                    # Convert judgment format to annotation format
                    query = data.get("query_card", "")
                    for eval_item in data.get("evaluations", []):
                        card = eval_item.get("card", "")
                        relevance = eval_item.get("relevance", 0)
                        similarity_score = convert_relevance_to_similarity_score(
                            int(relevance) if isinstance(relevance, (int, float)) else 0, scale="0-4"
                        )

                        annotations.append(
                            {
                                "card1": query,
                                "card2": card,
                                "similarity_score": similarity_score,
                                "similarity_type": "functional" if relevance >= 3 else "synergy",
                                "is_substitute": relevance == 4,
                                "source": "llm_judgment",
                                "judgment_metadata": {
                                    "relevance": relevance,
                                    "confidence": eval_item.get("confidence", 1.0),
                                    "methods_used": data.get("methods_used", []),
                                },
                            }
                        )
        except Exception as e:
            print(f"Warning: Could not load {file_path}: {e}")
            continue

    return annotations


def validate_annotation_quality(annotations: list[dict]) -> dict[str, Any]:
    """Validate annotation quality and detect issues."""
    issues = []
    warnings = []

    if not annotations:
        issues.append("No annotations found")
        return {"issues": issues, "warnings": warnings, "quality_score": 0.0}

    # Check for uniform scores (suspicious)
    similarity_scores = [ann.get("similarity_score", 0) for ann in annotations]
    if len(set(similarity_scores)) == 1 and len(annotations) > 5:
        issues.append(f"All annotations have same similarity_score: {similarity_scores[0]}")

    # Check for missing required fields
    required_fields = ["card1", "card2", "similarity_score"]
    for i, ann in enumerate(annotations):
        for field in required_fields:
            if field not in ann or ann[field] is None:
                issues.append(f"Annotation {i} missing required field: {field}")

    # Check for invalid similarity scores
    for i, ann in enumerate(annotations):
        score = ann.get("similarity_score", 0)
        if not (0.0 <= score <= 1.0):
            issues.append(f"Annotation {i} has invalid similarity_score: {score}")

    # Check source diversity
    sources = Counter(ann.get("source", "unknown") for ann in annotations)
    if len(sources) == 1 and len(annotations) > 10:
        warnings.append(f"All annotations from single source: {list(sources.keys())[0]}")

    # Compute quality score (0-1)
    quality_score = 1.0
    quality_score -= len(issues) * 0.2  # Each issue reduces score
    quality_score -= len(warnings) * 0.1  # Each warning reduces score
    quality_score = max(0.0, min(1.0, quality_score))

    return {
        "issues": issues,
        "warnings": warnings,
        "quality_score": quality_score,
        "source_distribution": dict(sources),
        "total_annotations": len(annotations),
    }


def deduplicate_annotations(
    annotations: list[dict],
    use_fuzzy: bool = False,
    fuzzy_threshold: float = 0.85,
) -> list[dict]:
    """Remove duplicate annotations (same card1, card2 pair).
    
    Args:
        annotations: List of annotation dictionaries
        use_fuzzy: If True, use fuzzy matching for duplicate detection
        fuzzy_threshold: Similarity threshold for fuzzy matching (0-1)
    """
    seen = {}
    deduplicated = []
    
    # Try to use annotation_utils deduplication if available
    try:
        from ml.utils.annotation_utils import deduplicate_annotations as utils_dedup
        return utils_dedup(annotations, use_fuzzy=use_fuzzy, fuzzy_threshold=fuzzy_threshold)
    except (ImportError, AttributeError):
        # Fallback to simple deduplication
        pass

    for ann in annotations:
        card1 = ann.get("card1", "").strip().lower()
        card2 = ann.get("card2", "").strip().lower()

        if not card1 or not card2:
            continue

        # Create canonical pair (order-independent)
        pair_key = tuple(sorted([card1, card2]))

        if pair_key not in seen:
            seen[pair_key] = ann
            deduplicated.append(ann)
        else:
            # Keep the one with higher similarity_score or more metadata
            existing = seen[pair_key]
            existing_score = existing.get("similarity_score", 0)
            new_score = ann.get("similarity_score", 0)

            if new_score > existing_score:
                seen[pair_key] = ann
                # Replace in deduplicated list
                deduplicated = [a for a in deduplicated if a != existing]
                deduplicated.append(ann)

    return deduplicated


def integrate_all_annotations(
    annotations_dir: Path,
    output_path: Path | None = None,
    min_quality_score: float = 0.5,
) -> dict[str, Any]:
    """Integrate annotations from all sources."""
    print("=" * 80)
    print("COMPREHENSIVE ANNOTATION INTEGRATION")
    print("=" * 80)
    print()

    all_annotations = []

    # 1. Hand annotations
    print("Loading hand annotations...")
    hand_files = list(annotations_dir.glob("hand_batch_*.yaml"))
    for file_path in hand_files:
        try:
            anns = load_hand_annotations_from_file(file_path)
            print(f"  {file_path.name}: {len(anns)} annotations")
            all_annotations.extend(anns)
        except Exception as e:
            print(f"  ⚠ {file_path.name}: Error - {e}")

    # 2. LLM annotations
    print("\nLoading LLM annotations...")
    llm_files = list(annotations_dir.glob("*_llm_annotations.jsonl"))
    for file_path in llm_files:
        try:
            anns = load_llm_annotations(file_path)
            print(f"  {file_path.name}: {len(anns)} annotations")
            all_annotations.extend(anns)
        except Exception as e:
            print(f"  ⚠ {file_path.name}: Error - {e}")

    # 3. User feedback
    print("\nLoading user feedback...")
    feedback_dir = project_root / "data" / "annotations"
    feedback_files = list(feedback_dir.glob("user_feedback.jsonl"))
    for file_path in feedback_files:
        try:
            anns = load_user_feedback(file_path)
            print(f"  {file_path.name}: {len(anns)} annotations")
            all_annotations.extend(anns)
        except Exception as e:
            print(f"  ⚠ {file_path.name}: Error - {e}")

    # 4. Multi-judge annotations
    print("\nLoading multi-judge annotations...")
    try:
        anns = load_multi_judge_annotations(annotations_dir)
        print(f"  Found {len(anns)} multi-judge annotations")
        all_annotations.extend(anns)
    except Exception as e:
        print(f"  ⚠ Error loading multi-judge: {e}")

    print(f"\nTotal annotations before deduplication: {len(all_annotations)}")

    # Deduplicate (with optional fuzzy matching)
    use_fuzzy = os.getenv("ANNOTATION_FUZZY_DEDUP", "false").lower() == "true"
    all_annotations = deduplicate_annotations(
        all_annotations,
        use_fuzzy=use_fuzzy,
        fuzzy_threshold=0.85,
    )
    print(f"Total annotations after deduplication: {len(all_annotations)}")
    if use_fuzzy:
        print("  (Used fuzzy matching for duplicate detection)")

    # Validate quality
    print("\nValidating quality...")
    quality = validate_annotation_quality(all_annotations)
    print(f"  Quality score: {quality['quality_score']:.2f}")
    if quality["issues"]:
        print(f"  ⚠ Issues: {len(quality['issues'])}")
        for issue in quality["issues"][:5]:
            print(f"    - {issue}")
    if quality["warnings"]:
        print(f"  ⚠ Warnings: {len(quality['warnings'])}")
        for warning in quality["warnings"][:5]:
            print(f"    - {warning}")

    print(f"\nSource distribution:")
    for source, count in quality["source_distribution"].items():
        print(f"  {source}: {count}")

    # Filter by quality if requested
    if quality["quality_score"] < min_quality_score:
        print(f"\n⚠ Quality score {quality['quality_score']:.2f} below threshold {min_quality_score}")
        print("  Consider fixing issues before using annotations")

    # Save integrated annotations
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

        try:
            with open(temp_path, "w") as f:
                for ann in all_annotations:
                    f.write(json.dumps(ann, ensure_ascii=False) + "\n")
            temp_path.replace(output_path)
            print(f"\n✓ Saved {len(all_annotations)} annotations to {output_path}")
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise

    return {
        "total_annotations": len(all_annotations),
        "quality": quality,
        "annotations": all_annotations,
    }


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Integrate annotations from all sources"
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=project_root / "annotations",
        help="Directory containing annotation files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root / "annotations" / "integrated_annotations.jsonl",
        help="Output path for integrated annotations",
    )
    parser.add_argument(
        "--min-quality",
        type=float,
        default=0.5,
        help="Minimum quality score threshold (0-1)",
    )

    args = parser.parse_args()

    result = integrate_all_annotations(
        args.annotations_dir,
        args.output,
        args.min_quality,
    )

    return 0 if result["quality"]["quality_score"] >= args.min_quality else 1


if __name__ == "__main__":
    sys.exit(main())

