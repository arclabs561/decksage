#!/usr/bin/env python3
"""
Automated annotation pipeline.

Orchestrates the complete annotation workflow:
1. Generate annotation batches
2. Collect annotations (LLM, browser, user feedback)
3. Integrate and validate
4. Resolve conflicts
5. Generate analytics
6. Sync to S3
"""

import argparse
import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


async def run_annotation_pipeline(
    annotations_dir: Path,
    num_llm_annotations: int = 50,
    num_queries: int = 5,
    resolve_conflicts: bool = True,
    generate_analytics: bool = True,
    sync_to_s3: bool = True,
    s3_path: str = "s3://games-collections/annotations/",
) -> int:
    """Run complete automated annotation pipeline."""
    print("=" * 80)
    print("AUTOMATED ANNOTATION PIPELINE")
    print("=" * 80)
    print()
    
    annotations_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Generate LLM annotations
    print("Step 1: Generating LLM annotations...")
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts" / "annotation" / "expand_annotations_parallel.py"),
                "--num-llm-annotations",
                str(num_llm_annotations),
                "--num-queries",
                str(num_queries),
                "--skip-browser",
                "--validate",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            print("  ✓ LLM annotations generated")
        else:
            print(f"  ⚠ LLM annotation generation had issues: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ⚠ LLM annotation generation failed: {e}")
    
    # Step 2: Integrate all annotations
    print("\nStep 2: Integrating all annotations...")
    integrated_file = annotations_dir / "pipeline_integrated.jsonl"
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts" / "annotation" / "integrate_all_annotations.py"),
                "--output",
                str(integrated_file),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print(f"  ✓ Annotations integrated: {integrated_file}")
        else:
            print(f"  ✗ Integration failed: {result.stderr[:200]}")
            return 1
    except Exception as e:
        print(f"  ✗ Integration failed: {e}")
        return 1
    
    # Step 3: Resolve conflicts
    if resolve_conflicts:
        print("\nStep 3: Resolving conflicts...")
        resolved_file = annotations_dir / "pipeline_resolved.jsonl"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(project_root / "scripts" / "annotation" / "conflict_resolution.py"),
                    "--input",
                    str(integrated_file),
                    "--output",
                    str(resolved_file),
                    "--strategy",
                    "weighted_consensus",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                print(f"  ✓ Conflicts resolved: {resolved_file}")
                integrated_file = resolved_file  # Use resolved version for next steps
            else:
                print(f"  ⚠ Conflict resolution had issues: {result.stderr[:200]}")
        except Exception as e:
            print(f"  ⚠ Conflict resolution failed: {e}")
    
    # Step 4: Generate analytics
    if generate_analytics:
        print("\nStep 4: Generating analytics...")
        analytics_file = annotations_dir / "pipeline_analytics.json"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(project_root / "scripts" / "annotation" / "annotation_analytics.py"),
                    "--input",
                    str(integrated_file),
                    "--output",
                    str(analytics_file),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                print(f"  ✓ Analytics generated: {analytics_file}")
            else:
                print(f"  ⚠ Analytics generation had issues: {result.stderr[:200]}")
        except Exception as e:
            print(f"  ⚠ Analytics generation failed: {e}")
    
    # Step 5: Validate
    print("\nStep 5: Validating annotations...")
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts" / "annotation" / "validate_integration.py"),
                "--input",
                str(integrated_file),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print("  ✓ Validation passed")
        else:
            print(f"  ⚠ Validation had issues: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ⚠ Validation failed: {e}")
    
    # Step 6: Sync to S3
    if sync_to_s3:
        print("\nStep 6: Syncing to S3...")
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(project_root / "scripts" / "annotation" / "sync_to_s3.py"),
                    "--s3-path",
                    s3_path,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                print("  ✓ Synced to S3")
            else:
                print(f"  ⚠ S3 sync had issues: {result.stderr[:200]}")
        except Exception as e:
            print(f"  ⚠ S3 sync failed: {e}")
    
    print("\n" + "=" * 80)
    print("PIPELINE COMPLETE")
    print("=" * 80)
    print(f"Final integrated file: {integrated_file}")
    
    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Run automated annotation pipeline")
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Annotations directory",
    )
    parser.add_argument(
        "--num-llm-annotations",
        type=int,
        default=50,
        help="Number of LLM annotations to generate",
    )
    parser.add_argument(
        "--num-queries",
        type=int,
        default=5,
        help="Number of queries for multi-judge",
    )
    parser.add_argument(
        "--skip-conflict-resolution",
        action="store_true",
        help="Skip conflict resolution",
    )
    parser.add_argument(
        "--skip-analytics",
        action="store_true",
        help="Skip analytics generation",
    )
    parser.add_argument(
        "--skip-s3",
        action="store_true",
        help="Skip S3 sync",
    )
    parser.add_argument(
        "--s3-path",
        type=str,
        default="s3://games-collections/annotations/",
        help="S3 path for sync",
    )
    
    args = parser.parse_args()
    
    return asyncio.run(
        run_annotation_pipeline(
            annotations_dir=args.annotations_dir,
            num_llm_annotations=args.num_llm_annotations,
            num_queries=args.num_queries,
            resolve_conflicts=not args.skip_conflict_resolution,
            generate_analytics=not args.skip_analytics,
            sync_to_s3=not args.skip_s3,
            s3_path=args.s3_path,
        )
    )


if __name__ == "__main__":
    sys.exit(main())


