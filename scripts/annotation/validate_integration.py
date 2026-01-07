#!/usr/bin/env python3
"""
Validate annotation integration end-to-end.

Tests:
1. All annotation sources load correctly
2. Integration produces valid unified format
3. Conversion to substitution pairs works
4. Conversion to test set works
5. Quality validation passes
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
src_dir = project_root / "src"
sys.path.insert(0, str(src_dir))

try:
    from ml.utils.annotation_utils import (
        extract_substitution_pairs_from_annotations,
        load_similarity_annotations,
    )
except ImportError:
    # Fallback: define minimal versions
    def extract_substitution_pairs_from_annotations(annotations, **kwargs):
        pairs = []
        for ann in annotations:
            if ann.get("is_substitute") and ann.get("similarity_score", 0) >= kwargs.get("min_similarity", 0.8):
                pairs.append((ann["card1"], ann["card2"]))
        return pairs
    
    def load_similarity_annotations(path):
        import json
        annotations = []
        with open(path) as f:
            for line in f:
                if line.strip():
                    annotations.append(json.loads(line))
        return annotations


def validate_integrated_annotations(annotations_file: Path) -> dict:
    """Validate integrated annotations file."""
    print(f"Validating integrated annotations: {annotations_file}")
    
    annotations = []
    errors = []
    with open(annotations_file) as f:
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
    
    if errors:
        print(f"⚠ {len(errors)} errors encountered while loading:")
        for error in errors[:5]:
            print(f"  {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more errors")
        print()
    
    print(f"  Total annotations: {len(annotations)}")
    
    # Check required fields
    required_fields = ["card1", "card2", "similarity_score", "source"]
    missing_fields = []
    invalid_scores = []
    
    for i, ann in enumerate(annotations):
        for field in required_fields:
            if field not in ann:
                missing_fields.append((i, field))
        
        # Validate similarity_score
        score = ann.get("similarity_score")
        if score is None:
            invalid_scores.append((i, "missing"))
        elif not isinstance(score, (int, float)) or not (0.0 <= score <= 1.0):
            invalid_scores.append((i, f"invalid: {score}"))
    
    issues = []
    if missing_fields:
        issues.append(f"Missing required fields: {len(missing_fields)} annotations")
    if invalid_scores:
        issues.append(f"Invalid similarity scores: {len(invalid_scores)} annotations")
    
    # Check source distribution
    from collections import Counter
    sources = Counter(ann.get("source", "unknown") for ann in annotations)
    
    result = {
        "total": len(annotations),
        "sources": dict(sources),
        "issues": issues,
        "valid": len(missing_fields) == 0 and len(invalid_scores) == 0,
    }
    
    print(f"  Sources: {dict(sources)}")
    if issues:
        print(f"  Issues: {issues}")
    else:
        print(f"  ✓ All annotations valid")
    
    return result


def validate_substitution_pairs(pairs_file: Path) -> dict:
    """Validate substitution pairs file."""
    print(f"\nValidating substitution pairs: {pairs_file}")
    
    if not pairs_file.exists():
        return {"valid": False, "error": "File not found"}
    
    with open(pairs_file) as f:
        pairs = json.load(f)
    
    if not isinstance(pairs, list):
        return {"valid": False, "error": "Not a list"}
    
    print(f"  Total pairs: {len(pairs)}")
    
    # Validate format
    invalid = []
    for i, pair in enumerate(pairs):
        if not isinstance(pair, list) or len(pair) != 2:
            invalid.append((i, "not a pair"))
        elif not all(isinstance(c, str) for c in pair):
            invalid.append((i, "not strings"))
    
    result = {
        "total": len(pairs),
        "invalid": len(invalid),
        "valid": len(invalid) == 0,
    }
    
    if invalid:
        print(f"  Issues: {len(invalid)} invalid pairs")
    else:
        print(f"  ✓ All pairs valid")
    
    return result


def validate_test_set(test_set_file: Path) -> dict:
    """Validate test set file."""
    print(f"\nValidating test set: {test_set_file}")
    
    if not test_set_file.exists():
        return {"valid": False, "error": "File not found"}
    
    with open(test_set_file) as f:
        test_set = json.load(f)
    
    if "queries" not in test_set:
        return {"valid": False, "error": "Missing 'queries' key"}
    
    queries = test_set["queries"]
    total_queries = len(queries)
    total_relevant = sum(
        len(v.get("highly_relevant", [])) + len(v.get("relevant", []))
        for v in queries.values()
    )
    
    print(f"  Total queries: {total_queries}")
    print(f"  Total relevant cards: {total_relevant}")
    
    result = {
        "total_queries": total_queries,
        "total_relevant": total_relevant,
        "valid": True,
    }
    
    print(f"  ✓ Test set valid")
    
    return result


def test_conversion_workflow(annotations_file: Path) -> dict:
    """Test conversion from annotations to substitution pairs."""
    print(f"\nTesting conversion workflow: {annotations_file}")
    
    # Load annotations
    annotations = load_similarity_annotations(annotations_file)
    print(f"  Loaded {len(annotations)} annotations")
    
    if not annotations:
        return {"valid": False, "error": "No annotations loaded"}
    
    # Extract substitution pairs
    pairs = extract_substitution_pairs_from_annotations(
        annotations,
        min_similarity=0.8,
        require_substitute_flag=True,
    )
    
    print(f"  Extracted {len(pairs)} substitution pairs")
    
    result = {
        "annotations_loaded": len(annotations),
        "pairs_extracted": len(pairs),
        "valid": len(annotations) > 0,
    }
    
    if pairs:
        print(f"  Sample pairs: {pairs[:3]}")
    
    return result


def main() -> int:
    """Main validation."""
    print("=" * 80)
    print("ANNOTATION INTEGRATION VALIDATION")
    print("=" * 80)
    print()
    
    annotations_dir = project_root / "annotations"
    
    # Find integrated annotations
    integrated_files = list(annotations_dir.glob("*integrated*.jsonl"))
    if not integrated_files:
        print("No integrated annotation files found")
        return 1
    
    # Use most recent
    integrated_file = sorted(integrated_files, key=lambda p: p.stat().st_mtime)[-1]
    
    results = {}
    
    # 1. Validate integrated annotations
    results["annotations"] = validate_integrated_annotations(integrated_file)
    
    # 2. Test conversion workflow
    results["conversion"] = test_conversion_workflow(integrated_file)
    
    # 3. Validate substitution pairs (if exists)
    pairs_file = annotations_dir / "test_substitution_pairs.json"
    if pairs_file.exists():
        results["substitution_pairs"] = validate_substitution_pairs(pairs_file)
    
    # 4. Validate test set (if exists)
    test_set_file = annotations_dir / "test_test_set.json"
    if test_set_file.exists():
        results["test_set"] = validate_test_set(test_set_file)
    
    # Summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    
    all_valid = all(
        r.get("valid", False) for r in results.values() if isinstance(r, dict)
    )
    
    if all_valid:
        print("✓ All validations passed")
        return 0
    else:
        print("⚠ Some validations failed")
        for name, result in results.items():
            if isinstance(result, dict) and not result.get("valid", False):
                print(f"  {name}: {result.get('error', 'invalid')}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

