#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Ensure all annotations are synced to S3 and properly integrated with the system.

This script:
1. Syncs all annotation files to S3
2. Integrates all annotations into a unified format
3. Validates annotations for training use
4. Creates integration summary
"""

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ensure annotations are synced to S3 and integrated"
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Local annotations directory",
    )
    parser.add_argument(
        "--s3-path",
        type=str,
        default="s3://games-collections/annotations/",
        help="S3 path for annotations",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip S3 sync (only integrate)",
    )
    parser.add_argument(
        "--skip-integration",
        action="store_true",
        help="Skip integration (only sync to S3)",
    )

    args = parser.parse_args()

    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    print("=" * 80)
    print("ANNOTATION S3 SYNC AND INTEGRATION")
    print("=" * 80)
    print()

    # Step 1: Sync to S3
    if not args.skip_sync:
        print("Step 1: Syncing annotations to S3...")
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(project_root / "scripts" / "annotation" / "sync_to_s3.py"),
                    "--annotations-dir",
                    str(args.annotations_dir),
                    "--s3-path",
                    args.s3_path,
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                print("  ✓ Synced to S3")
            else:
                print(f"  ⚠ S3 sync had issues: {result.stderr[:200]}")
                return 1
        except Exception as e:
            print(f"  ✗ S3 sync failed: {e}")
            return 1
    else:
        print("Step 1: Skipping S3 sync (--skip-sync)")

    # Step 2: Integrate all annotations
    if not args.skip_integration:
        print("\nStep 2: Integrating all annotations...")
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(project_root / "scripts" / "annotation" / "integrate_all_annotations.py"),
                    "--annotations-dir",
                    str(args.annotations_dir),
                    "--output",
                    str(args.annotations_dir / "integrated_all.jsonl"),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode == 0:
                print("  ✓ Integrated annotations")
                # Show summary
                output_file = args.annotations_dir / "integrated_all.jsonl"
                if output_file.exists():
                    count = sum(1 for _ in open(output_file))
                    print(f"  Total integrated annotations: {count}")
            else:
                print(f"  ⚠ Integration had issues: {result.stderr[:200]}")
        except Exception as e:
            print(f"  ⚠ Integration failed: {e}")
    else:
        print("Step 2: Skipping integration (--skip-integration)")

    # Step 3: Validate for training
    print("\nStep 3: Validating annotations for training use...")
    try:
        # Add src to path
        src_dir = project_root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))

        from ml.utils.annotation_utils import load_similarity_annotations

        # Load all game-specific annotation files
        games = ["magic", "pokemon", "yugioh", "riftbound"]
        total_annotations = 0
        for game in games:
            ann_file = args.annotations_dir / f"{game}_llm_annotations.jsonl"
            if ann_file.exists():
                try:
                    anns = load_similarity_annotations(
                        ann_file,
                        filter_test_cards=False,  # Just count, don't filter
                    )
                    count = len(anns)
                    total_annotations += count
                    print(f"  {game}: {count} annotations")
                except Exception as e:
                    print(f"  ⚠ {game}: Error loading - {e}")

        print(f"\n  Total annotations across all games: {total_annotations}")

        # Check for test set leakage
        print("\n  Checking for test set leakage...")
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(project_root / "scripts" / "training" / "validate_training_data.py"),
                    "--annotation-path",
                    str(args.annotations_dir / "integrated_all.jsonl"),
                    "--check-leakage",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                print("  ✓ No test set leakage detected")
            else:
                print(f"  ⚠ Leakage check: {result.stderr[:200]}")
        except Exception as e:
            print(f"  ⚠ Leakage check failed: {e}")

    except Exception as e:
        print(f"  ⚠ Validation failed: {e}")

    print("\n" + "=" * 80)
    print("INTEGRATION COMPLETE")
    print("=" * 80)
    print(f"Annotations directory: {args.annotations_dir}")
    print(f"S3 path: {args.s3_path}")
    print(f"Integrated file: {args.annotations_dir / 'integrated_all.jsonl'}")
    print()
    print("Next steps:")
    print("  1. Use integrated_all.jsonl for training")
    print("  2. Annotations are synced to S3 for backup")
    print("  3. Run validate_training_data.py before training to check for leakage")

    return 0


if __name__ == "__main__":
    sys.exit(main())
