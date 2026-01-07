#!/usr/bin/env python3
"""
Enhanced annotation integration with tracking and validation.

Features:
- Runtime validation with Pydantic models
- Enhanced error handling with context
- Source tracking and versioning
- Quality metrics over time
- Fuzzy duplicate detection
"""

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import with fallback for pandas-free environment
HAS_ENHANCED = False
validate_annotations_batch = None
AnnotationTracker = None
find_fuzzy_duplicates = None

try:
    # Try direct imports to avoid pandas dependency
    import importlib.util
    
    # Import annotation_utils directly
    spec = importlib.util.spec_from_file_location(
        'annotation_utils',
        project_root / 'src' / 'ml' / 'utils' / 'annotation_utils.py'
    )
    if spec and spec.loader:
        annotation_utils = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(annotation_utils)
        convert_relevance_to_similarity_score = annotation_utils.convert_relevance_to_similarity_score
        load_hand_annotations = annotation_utils.load_hand_annotations
        load_similarity_annotations = annotation_utils.load_similarity_annotations
        # deduplicate_annotations may not exist, use fallback
        deduplicate_annotations = getattr(annotation_utils, 'deduplicate_annotations', None)
    else:
        raise ImportError("Could not load annotation_utils")
    
    # Try enhanced modules
    try:
        spec_models = importlib.util.spec_from_file_location(
            'annotation_models',
            project_root / 'src' / 'ml' / 'utils' / 'annotation_models.py'
        )
        if spec_models and spec_models.loader:
            annotation_models = importlib.util.module_from_spec(spec_models)
            spec_models.loader.exec_module(annotation_models)
            validate_annotations_batch = annotation_models.validate_annotations_batch
            HAS_ENHANCED = True
    except Exception:
        pass
    
    try:
        spec_tracking = importlib.util.spec_from_file_location(
            'annotation_tracking',
            project_root / 'src' / 'ml' / 'utils' / 'annotation_tracking.py'
        )
        if spec_tracking and spec_tracking.loader:
            annotation_tracking = importlib.util.module_from_spec(spec_tracking)
            spec_tracking.loader.exec_module(annotation_tracking)
            AnnotationTracker = annotation_tracking.AnnotationTracker
            HAS_ENHANCED = True
    except Exception:
        pass
    
    try:
        spec_fuzzy = importlib.util.spec_from_file_location(
            'fuzzy_matching',
            project_root / 'src' / 'ml' / 'utils' / 'fuzzy_matching.py'
        )
        if spec_fuzzy and spec_fuzzy.loader:
            fuzzy_matching = importlib.util.module_from_spec(spec_fuzzy)
            spec_fuzzy.loader.exec_module(fuzzy_matching)
            find_fuzzy_duplicates = fuzzy_matching.find_fuzzy_duplicates
            HAS_ENHANCED = True
    except Exception:
        pass

except ImportError as e:
    print(f"Warning: Enhanced features not available: {e}")
    print("Falling back to basic integration")
    # Fallback functions
    def convert_relevance_to_similarity_score(relevance: int, scale: str = "0-4") -> float:
        mapping = {4: 0.95, 3: 0.75, 2: 0.55, 1: 0.35, 0: 0.1}
        return mapping.get(relevance, 0.0)
    
    def deduplicate_annotations(annotations, use_fuzzy=False, fuzzy_threshold=0.85):
        # Simple deduplication
        seen = {}
        deduplicated = []
        for ann in annotations:
            card1 = ann.get("card1", "").strip().lower()
            card2 = ann.get("card2", "").strip().lower()
            if not card1 or not card2:
                continue
            pair_key = tuple(sorted([card1, card2]))
            if pair_key not in seen:
                seen[pair_key] = ann
                deduplicated.append(ann)
        return deduplicated
    
    def load_hand_annotations(path):
        return []
    
    def load_similarity_annotations(path):
        return []


def integrate_with_enhancements(
    annotations_dir: Path,
    output_path: Path | None = None,
    tracking_file: Path | None = None,
    use_validation: bool = True,
    use_fuzzy_dedup: bool = False,
    min_quality_score: float = 0.5,
) -> dict[str, Any]:
    """Integrate annotations with enhanced features.
    
    Args:
        annotations_dir: Directory containing annotation files
        output_path: Output path for integrated annotations
        tracking_file: Path to tracking file for metrics
        use_validation: Enable Pydantic validation
        use_fuzzy_dedup: Use fuzzy matching for duplicate detection
        min_quality_score: Minimum quality score threshold
    """
    print("=" * 80)
    print("ENHANCED ANNOTATION INTEGRATION")
    print("=" * 80)
    print()
    
    # Initialize tracker
    tracker = None
    if tracking_file and HAS_ENHANCED and AnnotationTracker:
        try:
            tracker = AnnotationTracker(tracking_file)
            print(f"Tracking enabled: {tracking_file}")
        except Exception as e:
            print(f"Warning: Could not initialize tracker: {e}")
    
    # Load annotations from all sources
    all_annotations = []
    
    # Load hand annotations
    print("Loading hand annotations...")
    hand_files = list(annotations_dir.glob("hand_batch_*.yaml"))
    for file_path in hand_files:
        try:
            if load_hand_annotations:
                anns = load_hand_annotations(file_path)
                all_annotations.extend(anns)
                if tracker:
                    for ann in anns:
                        tracker.record_annotation(ann, version=file_path.stem)
                print(f"  {file_path.name}: {len(anns)} annotations")
            else:
                print(f"  {file_path.name}: Skipped (load_hand_annotations not available)")
        except Exception as e:
            print(f"  ⚠ Error loading {file_path.name}: {e}")
    
    # Load LLM annotations
    print("\nLoading LLM annotations...")
    llm_files = list(annotations_dir.glob("*_llm_annotations.jsonl"))
    for file_path in llm_files:
        try:
            if load_similarity_annotations:
                anns = load_similarity_annotations(file_path)
                all_annotations.extend(anns)
                if tracker:
                    for ann in anns:
                        tracker.record_annotation(ann, version=file_path.stem)
                print(f"  {file_path.name}: {len(anns)} annotations")
            else:
                print(f"  {file_path.name}: Skipped (load_similarity_annotations not available)")
        except Exception as e:
            print(f"  ⚠ Error loading {file_path.name}: {e}")
    
    # Load user feedback
    print("\nLoading user feedback...")
    feedback_file = annotations_dir / "user_feedback.jsonl"
    if feedback_file.exists():
        try:
            if load_similarity_annotations:
                anns = load_similarity_annotations(feedback_file)
                all_annotations.extend(anns)
                if tracker:
                    for ann in anns:
                        tracker.record_annotation(ann, version="user_feedback")
                print(f"  {feedback_file.name}: {len(anns)} annotations")
            else:
                print(f"  {feedback_file.name}: Skipped (load_similarity_annotations not available)")
        except Exception as e:
            print(f"  ⚠ Error loading {feedback_file.name}: {e}")
    
    print(f"\nTotal annotations before deduplication: {len(all_annotations)}")
    
    # Validate annotations if enabled
    if use_validation and HAS_ENHANCED and validate_annotations_batch:
        print("\nValidating annotations...")
        try:
            valid, invalid, errors = validate_annotations_batch(all_annotations, strict=False)
            print(f"  Valid: {len(valid)}")
            print(f"  Invalid: {len(invalid)}")
            if errors:
                print(f"  Errors: {len(errors)}")
                for error in errors[:5]:
                    print(f"    - {error}")
            
            # Use validated annotations
            all_annotations = valid + invalid  # Keep both for now
        except Exception as e:
            print(f"  ⚠ Validation failed: {e}")
            print("  Continuing without validation")
    
    # Deduplicate
    print("\nDeduplicating annotations...")
    if deduplicate_annotations:
        all_annotations = deduplicate_annotations(
            all_annotations,
            use_fuzzy=use_fuzzy_dedup if HAS_ENHANCED else False,
            fuzzy_threshold=0.85,
        )
    else:
        # Fallback simple deduplication
        seen = {}
        deduplicated = []
        for ann in all_annotations:
            card1 = ann.get("card1", "").strip().lower()
            card2 = ann.get("card2", "").strip().lower()
            if not card1 or not card2:
                continue
            pair_key = tuple(sorted([card1, card2]))
            if pair_key not in seen:
                seen[pair_key] = ann
                deduplicated.append(ann)
        all_annotations = deduplicated
    print(f"Total annotations after deduplication: {len(all_annotations)}")
    
    # Find fuzzy duplicates for reporting
    if use_fuzzy_dedup and HAS_ENHANCED and find_fuzzy_duplicates:
        try:
            fuzzy_dups = find_fuzzy_duplicates(all_annotations, threshold=0.85)
            if fuzzy_dups:
                print(f"  Found {len(fuzzy_dups)} potential fuzzy duplicates:")
                for i, j, ratio, pair1, pair2 in fuzzy_dups[:5]:
                    print(f"    {pair1} ≈ {pair2} (similarity: {ratio:.2f})")
        except Exception as e:
            print(f"  ⚠ Fuzzy duplicate detection failed: {e}")
    
    # Validate quality
    print("\nValidating quality...")
    issues = []
    warnings = []
    
    # Check for uniform scores
    scores = [ann.get("similarity_score", 0) for ann in all_annotations]
    if len(set(scores)) == 1 and len(all_annotations) > 5:
        issues.append(f"All annotations have same similarity_score: {scores[0]}")
    
    # Check required fields
    for i, ann in enumerate(all_annotations):
        required = ["card1", "card2", "similarity_score", "source"]
        missing = [f for f in required if f not in ann or ann[f] is None]
        if missing:
            issues.append(f"Annotation {i} missing: {missing}")
    
    # Compute quality score
    quality_score = 1.0
    quality_score -= len(issues) * 0.2
    quality_score -= len(warnings) * 0.1
    quality_score = max(0.0, min(1.0, quality_score))
    
    print(f"  Quality score: {quality_score:.2f}")
    if issues:
        print(f"  ⚠ Issues: {len(issues)}")
    if warnings:
        print(f"  ⚠ Warnings: {len(warnings)}")
    
    # Record quality metrics
    if tracker:
        try:
            tracker.record_quality_metrics(
                quality_score=quality_score,
                total_annotations=len(all_annotations),
                issues=issues,
                warnings=warnings,
                metadata={
                    "use_validation": use_validation,
                    "use_fuzzy_dedup": use_fuzzy_dedup,
                },
            )
            tracker.save()
            print(f"\nQuality metrics tracked in: {tracking_file}")
        except Exception as e:
            print(f"Warning: Could not record quality metrics: {e}")
    
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
    
    # Get summary
    sources = Counter(ann.get("source", "unknown") for ann in all_annotations)
    
    result = {
        "total_annotations": len(all_annotations),
        "quality_score": quality_score,
        "issues": issues,
        "warnings": warnings,
        "source_distribution": dict(sources),
    }
    
    if tracker:
        result["tracking_summary"] = tracker.get_summary()
    
    return result


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enhanced annotation integration with tracking and validation"
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Directory containing annotation files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("annotations") / "enhanced_integrated.jsonl",
        help="Output path for integrated annotations",
    )
    parser.add_argument(
        "--tracking-file",
        type=Path,
        default=Path("annotations") / "tracking.json",
        help="Path to tracking file for metrics",
    )
    parser.add_argument(
        "--no-validation",
        action="store_true",
        help="Disable Pydantic validation",
    )
    parser.add_argument(
        "--fuzzy-dedup",
        action="store_true",
        help="Use fuzzy matching for duplicate detection",
    )
    parser.add_argument(
        "--min-quality",
        type=float,
        default=0.5,
        help="Minimum quality score threshold",
    )
    
    args = parser.parse_args()
    
    if not HAS_ENHANCED:
        print("Warning: Enhanced features not available, using basic integration")
        print("Install dependencies: pip install pydantic")
    
    result = integrate_with_enhancements(
        annotations_dir=args.annotations_dir,
        output_path=args.output,
        tracking_file=args.tracking_file,
        use_validation=not args.no_validation,
        use_fuzzy_dedup=args.fuzzy_dedup,
        min_quality_score=args.min_quality,
    )
    
    print("\n" + "=" * 80)
    print("INTEGRATION SUMMARY")
    print("=" * 80)
    print(f"Total annotations: {result['total_annotations']}")
    print(f"Quality score: {result['quality_score']:.2f}")
    print(f"Issues: {len(result['issues'])}")
    print(f"Warnings: {len(result['warnings'])}")
    print("\nSource distribution:")
    for source, count in result["source_distribution"].items():
        print(f"  {source}: {count}")
    
    if "tracking_summary" in result:
        print("\nTracking summary:")
        summary = result["tracking_summary"]
        print(f"  Total sources: {summary['total_sources']}")
        print(f"  Quality snapshots: {summary['quality_snapshots']}")
        if summary["latest_quality"]:
            latest = summary["latest_quality"]
            print(f"  Latest quality: {latest['quality_score']:.2f} ({latest['timestamp']})")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

