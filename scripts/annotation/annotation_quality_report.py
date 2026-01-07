#!/usr/bin/env python3
"""Generate comprehensive annotation quality report.

Identifies issues, missing fields, validation errors, and provides
actionable recommendations for improvement.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.annotation_utils import load_similarity_annotations


def analyze_annotation_quality(annotations_dir: Path) -> dict:
    """Analyze quality of all annotation files."""
    report = {
        "files": {},
        "summary": {
            "total_files": 0,
            "total_annotations": 0,
            "valid_annotations": 0,
            "invalid_annotations": 0,
            "issues": defaultdict(int),
        },
    }
    
    annotation_files = list(annotations_dir.glob("*_llm_annotations.jsonl"))
    annotation_files = [f for f in annotation_files if "enriched" not in str(f) and ".bak" not in str(f)]
    
    for ann_file in annotation_files:
        try:
            annotations = load_similarity_annotations(ann_file)
            
            file_report = {
                "total": len(annotations),
                "valid": 0,
                "invalid": 0,
                "issues": defaultdict(int),
                "missing_fields": defaultdict(int),
            }
            
            for ann in annotations:
                # Check required fields
                if "source" not in ann or not ann.get("source"):
                    file_report["missing_fields"]["source"] += 1
                    file_report["issues"]["missing_source"] += 1
                if "similarity_score" not in ann or ann.get("similarity_score") is None:
                    file_report["missing_fields"]["similarity_score"] += 1
                    file_report["issues"]["missing_similarity_score"] += 1
                if "card1" not in ann or "card2" not in ann:
                    file_report["issues"]["missing_cards"] += 1
                else:
                    file_report["valid"] += 1
                    report["summary"]["valid_annotations"] += 1
            
            file_report["invalid"] = file_report["total"] - file_report["valid"]
            
            # Aggregate issues
            for issue, count in file_report["issues"].items():
                report["summary"]["issues"][issue] += count
            
            report["files"][ann_file.name] = file_report
            report["summary"]["total_files"] += 1
            report["summary"]["total_annotations"] += len(annotations)
            report["summary"]["invalid_annotations"] += file_report["invalid"]
            
        except Exception as e:
            report["files"][ann_file.name] = {"error": str(e)}
    
    return report


def print_report(report: dict) -> None:
    """Print quality report."""
    print("=" * 80)
    print("ANNOTATION QUALITY REPORT")
    print("=" * 80)
    print()
    
    summary = report["summary"]
    print(f"Summary:")
    print(f"  Total files: {summary['total_files']}")
    print(f"  Total annotations: {summary['total_annotations']}")
    print(f"  Valid: {summary['valid_annotations']} ({summary['valid_annotations']/summary['total_annotations']*100:.1f}%)" if summary['total_annotations'] > 0 else "  Valid: 0")
    print(f"  Invalid: {summary['invalid_annotations']} ({summary['invalid_annotations']/summary['total_annotations']*100:.1f}%)" if summary['total_annotations'] > 0 else "  Invalid: 0")
    print()
    
    if summary["issues"]:
        print("Issues found:")
        for issue, count in sorted(summary["issues"].items(), key=lambda x: x[1], reverse=True):
            pct = (count / summary["total_annotations"] * 100) if summary["total_annotations"] > 0 else 0
            print(f"  {issue}: {count} ({pct:.1f}%)")
        print()
    
    print("File Details:")
    for filename, file_report in sorted(report["files"].items()):
        if "error" in file_report:
            print(f"  {filename}: ERROR - {file_report['error']}")
            continue
        
        status = "✅" if file_report["invalid"] == 0 else "⚠️"
        print(f"  {status} {filename}:")
        print(f"    Total: {file_report['total']}, Valid: {file_report['valid']}, Invalid: {file_report['invalid']}")
        if file_report["missing_fields"]:
            print(f"    Missing fields: {dict(file_report['missing_fields'])}")
    
    print()
    print("=" * 80)
    
    # Recommendations
    if summary["issues"]:
        print()
        print("RECOMMENDATIONS:")
        if summary["issues"].get("missing_source"):
            print("  1. Run: uv run python3 scripts/annotation/fix_missing_fields.py --input-dir annotations/")
        if summary["issues"].get("missing_similarity_score"):
            print("  2. Check Yu-Gi-Oh annotations - they may use 'confidence' instead of 'similarity_score'")
        print("  3. Re-generate annotations with updated llm_annotator.py (includes source field)")
        print("  4. Re-enrich annotations after fixing: uv run python3 scripts/annotation/enrich_existing_annotations.py")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate annotation quality report")
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Annotations directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON report file",
    )
    
    args = parser.parse_args()
    
    report = analyze_annotation_quality(args.annotations_dir)
    print_report(report)
    
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Convert defaultdict to dict for JSON
        report_json = json.loads(json.dumps(report, default=str))
        with open(args.output, "w") as f:
            json.dump(report_json, f, indent=2, ensure_ascii=False)
        print(f"\nReport saved to: {args.output}")
    
    return 0 if report["summary"]["invalid_annotations"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())


