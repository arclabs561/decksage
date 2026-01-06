#!/usr/bin/env python3
"""Fix missing required fields in annotation files.

Adds missing 'source' and 'similarity_score' fields to annotations
that are missing them, based on available metadata.
"""

import argparse
import json
import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def infer_source(annotation: dict) -> str:
    """Infer source field from annotation metadata."""
    if "source" in annotation and annotation["source"]:
        return annotation["source"]
    
    # Check for model_name (LLM annotation)
    if annotation.get("model_name"):
        return "llm"
    
    # Check for annotator_id (multi-judge)
    if annotation.get("annotator_id"):
        return "multi_judge"
    
    # Check for relevance (hand annotation)
    if "relevance" in annotation:
        return "hand"
    
    # Check for user_id (user feedback)
    if annotation.get("user_id"):
        return "user_feedback"
    
    # Default based on file name patterns
    return "llm"  # Most common case


def infer_similarity_score(annotation: dict) -> float | None:
    """Infer similarity_score from annotation data."""
    if "similarity_score" in annotation:
        val = annotation["similarity_score"]
        if val is not None:
            return float(val)
    
    # Try to convert from relevance (0-4) to similarity (0-1)
    if "relevance" in annotation:
        relevance = annotation["relevance"]
        if isinstance(relevance, (int, float)):
            return relevance / 4.0
    
    # Try to extract from confidence
    if "confidence" in annotation:
        conf = annotation["confidence"]
        if isinstance(conf, (int, float)):
            return float(conf)
    
    return None


def fix_annotation(annotation: dict, file_path: Path) -> dict:
    """Fix a single annotation by adding missing required fields."""
    fixed = annotation.copy()
    fixes = []
    
    # Fix source
    if "source" not in fixed or not fixed["source"]:
        fixed["source"] = infer_source(fixed)
        fixes.append("source")
    
    # Fix similarity_score
    if "similarity_score" not in fixed or fixed["similarity_score"] is None:
        inferred = infer_similarity_score(fixed)
        if inferred is not None:
            fixed["similarity_score"] = inferred
            fixes.append("similarity_score")
        else:
            # Default to 0.5 if we can't infer
            fixed["similarity_score"] = 0.5
            fixes.append("similarity_score (defaulted)")
    
    # Ensure card1 and card2 exist
    if "card1" not in fixed or "card2" not in fixed:
        # Can't fix this - skip
        return None
    
    return fixed, fixes


def fix_annotations_file(input_path: Path, output_path: Path | None = None, dry_run: bool = False) -> dict:
    """Fix annotations in a file."""
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        return {"error": "file_not_found"}
    
    output_path = output_path or input_path
    
    stats = {
        "total": 0,
        "fixed": 0,
        "skipped": 0,
        "errors": 0,
        "fixes_applied": defaultdict(int),
    }
    
    fixed_annotations = []
    
    with open(input_path, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                annotation = json.loads(line)
                stats["total"] += 1
                
                result = fix_annotation(annotation, input_path)
                if result is None:
                    stats["skipped"] += 1
                    continue
                
                fixed_ann, fixes = result
                
                if fixes:
                    stats["fixed"] += 1
                    for fix in fixes:
                        stats["fixes_applied"][fix] += 1
                    fixed_annotations.append(fixed_ann)
                else:
                    fixed_annotations.append(fixed_ann)
                    
            except json.JSONDecodeError as e:
                print(f"  Line {line_num}: JSON decode error: {e}")
                stats["errors"] += 1
            except Exception as e:
                print(f"  Line {line_num}: Error: {e}")
                stats["errors"] += 1
    
    if not dry_run and fixed_annotations:
        # Use atomic write
        temp_file = output_path.with_suffix(output_path.suffix + ".tmp")
        with open(temp_file, "w") as f:
            for ann in fixed_annotations:
                f.write(json.dumps(ann, ensure_ascii=False) + "\n")
        temp_file.replace(output_path)
        print(f"  Saved {len(fixed_annotations)} annotations to {output_path}")
    elif dry_run:
        print(f"  [DRY RUN] Would save {len(fixed_annotations)} annotations")
    
    return stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix missing required fields in annotations")
    parser.add_argument(
        "--input",
        type=Path,
        help="Input annotation file",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="Input directory (processes all *_llm_annotations.jsonl files)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory (default: same as input)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write files, just report what would be fixed",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup before modifying",
    )
    
    args = parser.parse_args()
    
    if not args.input and not args.input_dir:
        parser.error("Must specify --input or --input-dir")
    
    print("=" * 80)
    print("FIXING MISSING FIELDS IN ANNOTATIONS")
    print("=" * 80)
    print()
    
    if args.dry_run:
        print("DRY RUN MODE - No files will be modified")
        print()
    
    files_to_process = []
    if args.input:
        files_to_process = [args.input]
    elif args.input_dir:
        files_to_process = list(args.input_dir.glob("*_llm_annotations.jsonl"))
        # Exclude enriched files
        files_to_process = [f for f in files_to_process if "enriched" not in str(f)]
    
    if not files_to_process:
        print("No annotation files found")
        return 1
    
    total_stats = {
        "files": 0,
        "total": 0,
        "fixed": 0,
        "skipped": 0,
        "errors": 0,
        "fixes_applied": defaultdict(int),
    }
    
    for input_file in files_to_process:
        print(f"Processing: {input_file.name}")
        
        if args.backup and not args.dry_run:
            backup_path = input_file.with_suffix(input_file.suffix + ".bak")
            import shutil
            shutil.copy2(input_file, backup_path)
            print(f"  Backup created: {backup_path}")
        
        output_file = input_file
        if args.output_dir:
            output_file = args.output_dir / input_file.name
        
        stats = fix_annotations_file(input_file, output_file, dry_run=args.dry_run)
        
        if "error" in stats:
            print(f"  Error: {stats['error']}")
            continue
        
        total_stats["files"] += 1
        total_stats["total"] += stats["total"]
        total_stats["fixed"] += stats["fixed"]
        total_stats["skipped"] += stats["skipped"]
        total_stats["errors"] += stats["errors"]
        for fix, count in stats["fixes_applied"].items():
            total_stats["fixes_applied"][fix] += count
        
        print(f"  Total: {stats['total']}, Fixed: {stats['fixed']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")
        if stats["fixes_applied"]:
            print(f"  Fixes: {dict(stats['fixes_applied'])}")
        print()
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Files processed: {total_stats['files']}")
    print(f"Total annotations: {total_stats['total']}")
    print(f"Fixed: {total_stats['fixed']}")
    print(f"Skipped: {total_stats['skipped']}")
    print(f"Errors: {total_stats['errors']}")
    if total_stats["fixes_applied"]:
        print(f"Fixes applied: {dict(total_stats['fixes_applied'])}")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


