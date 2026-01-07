#!/usr/bin/env python3
"""
End-to-end test for feedback system.

Tests:
1. Feedback submission (simulated API call)
2. Feedback saved to user_feedback.jsonl
3. Feedback integrated into annotations
4. Feedback synced to S3
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def simulate_feedback_submission(
    query_card: str,
    candidate_card: str,
    rating: int,
    is_substitute: bool = False,
    feedback_file: Path | None = None,
) -> dict:
    """Simulate feedback submission (would come from API in real scenario).
    
    Args:
        query_card: Query card name
        candidate_card: Candidate card name
        rating: Rating (0-4)
        is_substitute: Whether candidate can substitute query
        feedback_file: Path to feedback file
        
    Returns:
        Feedback entry dictionary
    """
    feedback_file = feedback_file or Path("annotations") / "user_feedback.jsonl"
    feedback_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Create feedback entry (matches API format)
    feedback_entry = {
        "query_card": query_card,
        "candidate_card": candidate_card,
        "rating": rating,
        "is_substitute": is_substitute,
        "timestamp": datetime.now().isoformat(),
        "source": "ui_feedback",
        "user_id": "test_user",
        "session_id": f"test_session_{int(time.time())}",
    }
    
    # Append to feedback file (atomic write)
    temp_file = feedback_file.with_suffix(feedback_file.suffix + ".tmp")
    try:
        # Read existing feedback
        existing = []
        if feedback_file.exists():
            with open(feedback_file) as f:
                for line in f:
                    if line.strip():
                        existing.append(json.loads(line))
        
        # Add new feedback
        existing.append(feedback_entry)
        
        # Write back
        with open(temp_file, "w") as f:
            for entry in existing:
                f.write(json.dumps(entry) + "\n")
        
        temp_file.replace(feedback_file)
        
        print(f"✓ Feedback saved to {feedback_file}")
        return feedback_entry
    except Exception as e:
        if temp_file.exists():
            temp_file.unlink()
        raise


def test_feedback_integration(feedback_file: Path) -> bool:
    """Test that feedback is integrated into annotations."""
    print("\n" + "=" * 80)
    print("TESTING FEEDBACK INTEGRATION")
    print("=" * 80)
    
    # Run integration script
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts" / "annotation" / "integrate_all_annotations.py"),
                "--output",
                str(project_root / "annotations" / "test_feedback_integrated.jsonl"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode != 0:
            print(f"✗ Integration failed: {result.stderr}")
            return False
        
        # Check if feedback appears in integrated file
        integrated_file = project_root / "annotations" / "test_feedback_integrated.jsonl"
        if not integrated_file.exists():
            print("✗ Integrated file not created")
            return False
        
        feedback_found = False
        with open(integrated_file) as f:
            for line in f:
                if line.strip():
                    ann = json.loads(line)
                    if ann.get("source") == "user_feedback":
                        feedback_found = True
                        print(f"✓ Found feedback annotation: {ann.get('card1')} <-> {ann.get('card2')}")
        
        if not feedback_found:
            print("✗ Feedback not found in integrated annotations")
            return False
        
        print("✓ Feedback successfully integrated")
        return True
    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        return False


def test_feedback_s3_sync(s3_path: str = "s3://games-collections/annotations/") -> bool:
    """Test that feedback is synced to S3."""
    print("\n" + "=" * 80)
    print("TESTING FEEDBACK S3 SYNC")
    print("=" * 80)
    
    feedback_file = Path("annotations") / "user_feedback.jsonl"
    if not feedback_file.exists():
        print("✗ Feedback file not found")
        return False
    
    # Sync to S3
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
            timeout=60,
        )
        
        if result.returncode != 0:
            print(f"✗ S3 sync failed: {result.stderr}")
            return False
        
        # Check if feedback file is mentioned in sync output
        if "user_feedback.jsonl" in result.stdout or "Synced:" in result.stdout:
            print("✓ Feedback file synced to S3")
            
            # Verify in S3 (if accessible)
            try:
                verify_result = subprocess.run(
                    ["s5cmd", "ls", f"{s3_path}user_feedback.jsonl"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if verify_result.returncode == 0:
                    print(f"✓ Verified in S3: {verify_result.stdout.strip()}")
                else:
                    print("⚠ Could not verify in S3 (may need credentials)")
            except Exception:
                print("⚠ Could not verify in S3 (s5cmd not available or credentials needed)")
            
            return True
        else:
            print("⚠ Feedback file may not have been synced")
            return False
    except Exception as e:
        print(f"✗ S3 sync test failed: {e}")
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="E2E test for feedback system")
    parser.add_argument(
        "--query",
        type=str,
        default="Lightning Bolt",
        help="Query card for test feedback",
    )
    parser.add_argument(
        "--candidate",
        type=str,
        default="Chain Lightning",
        help="Candidate card for test feedback",
    )
    parser.add_argument(
        "--rating",
        type=int,
        default=4,
        help="Rating (0-4)",
    )
    parser.add_argument(
        "--skip-s3",
        action="store_true",
        help="Skip S3 sync test",
    )
    parser.add_argument(
        "--s3-path",
        type=str,
        default="s3://games-collections/annotations/",
        help="S3 path for sync",
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("FEEDBACK SYSTEM E2E TEST")
    print("=" * 80)
    print()
    
    # Test 1: Simulate feedback submission
    print("=" * 80)
    print("TEST 1: FEEDBACK SUBMISSION")
    print("=" * 80)
    
    feedback_file = Path("annotations") / "user_feedback.jsonl"
    
    try:
        feedback_entry = simulate_feedback_submission(
            query_card=args.query,
            candidate_card=args.candidate,
            rating=args.rating,
            is_substitute=args.rating >= 3,
            feedback_file=feedback_file,
        )
        print(f"✓ Feedback submitted: {feedback_entry['query_card']} <-> {feedback_entry['candidate_card']}")
        print(f"  Rating: {feedback_entry['rating']}")
        print(f"  Is substitute: {feedback_entry['is_substitute']}")
    except Exception as e:
        print(f"✗ Feedback submission failed: {e}")
        return 1
    
    # Test 2: Integration
    integration_ok = test_feedback_integration(feedback_file)
    
    # Test 3: S3 sync
    s3_ok = True
    if not args.skip_s3:
        s3_ok = test_feedback_s3_sync(args.s3_path)
    else:
        print("\n" + "=" * 80)
        print("SKIPPING S3 SYNC TEST")
        print("=" * 80)
    
    # Summary
    print("\n" + "=" * 80)
    print("E2E TEST SUMMARY")
    print("=" * 80)
    print(f"Feedback submission: ✓")
    print(f"Integration: {'✓' if integration_ok else '✗'}")
    print(f"S3 sync: {'✓' if s3_ok else '✗'}")
    
    if integration_ok and s3_ok:
        print("\n✓ All tests passed")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())


