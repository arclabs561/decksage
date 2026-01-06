#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "boto3",
#   "requests",
# ]
# ///

"""
Submit Comparison Tasks to MTurk and Scale AI

Submits the same test tasks to both services for quality/price comparison.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load .env
env_file = project_root / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

from src.ml.annotation.human_annotation_services import (
    AnnotationTask,
    get_annotation_service,
)
from src.ml.annotation.human_annotation_queue import (
    AnnotationPriority,
    HumanAnnotationQueue,
    AnnotationStatus,
)


def create_improved_instructions(card1: str, card2: str, game: str) -> str:
    """Create improved task instructions with examples."""
    return f"""
CARD SIMILARITY ANNOTATION TASK

Your task: Rate how similar two {game} cards are to each other.

CARDS TO COMPARE:
- Card 1: {card1}
- Card 2: {card2}

SCORING GUIDELINES (0.0 - 1.0):

0.9 - 1.0: Nearly identical (direct substitutes, same function)
  Example: "Lightning Bolt" vs "Shock" (both deal 3 damage)
  
0.7 - 0.8: Very similar (same role, minor differences)
  Example: "Counterspell" vs "Mana Leak" (both counter spells)
  
0.5 - 0.6: Moderately similar (related function, same archetype)
  Example: "Lightning Bolt" vs "Lava Spike" (both burn spells)
  
0.3 - 0.4: Somewhat similar (loose connection, shared theme)
  Example: "Lightning Bolt" vs "Bolt of Keranos" (both red damage)
  
0.1 - 0.2: Marginally similar (minimal connection)
  Example: "Lightning Bolt" vs "Shocklands" (both red, different purpose)
  
0.0 - 0.1: Unrelated (different function, color, archetype)
  Example: "Lightning Bolt" vs "Plains" (completely different)

SIMILARITY TYPES:
- functional: Cards serve the same function (can replace each other)
- synergy: Cards work well together (combo, synergy)
- archetype: Cards belong to same deck type/strategy
- manabase: Cards are both lands/mana sources
- unrelated: No clear relationship

SUBSTITUTION:
- YES: Card 2 can reasonably replace Card 1 in most decks
- NO: Cards are different enough that substitution is not appropriate

REASONING:
Provide 2-3 sentences explaining:
- Why you chose this score
- What similarities/differences you noticed
- Context where they might be used together

IMPORTANT:
- Be consistent: Similar cards should get similar scores
- Use the full range: Don't cluster scores at 0.0 or 1.0
- Consider context: Some cards are similar in specific decks only
"""


def submit_comparison_tasks(
    submit_mturk: bool = True,
    submit_scale: bool = True,
    num_tasks: int = 2,
) -> dict:
    """Submit same tasks to both services for comparison."""
    print("="*70)
    print("Submitting Comparison Tasks")
    print("="*70)
    print()
    
    # Test pairs (same for both services)
    test_pairs = [
        ("Lightning Bolt", "Shock", "magic", "High similarity - both deal 3 damage"),
        ("Counterspell", "Mana Leak", "magic", "High similarity - both counter spells"),
    ][:num_tasks]
    
    queue = HumanAnnotationQueue()
    results = {
        "mturk": {"submitted": [], "failed": []},
        "scale": {"submitted": [], "failed": []},
    }
    
    # Submit to MTurk
    if submit_mturk:
        print("Submitting to MTurk...")
        print("-" * 70)
        try:
            mturk_service = get_annotation_service("mturk")
            
            # Check balance
            try:
                balance = mturk_service.get_account_balance()
                print(f"  Account balance: ${balance['available']:.2f}")
                if balance['available'] < 0.12 * num_tasks:
                    print(f"  ⚠ Low balance - need ${0.12 * num_tasks:.2f} for {num_tasks} tasks")
                    print(f"  Add balance: https://requester.mturk.com/account")
            except Exception as e:
                print(f"  ⚠ Could not check balance: {e}")
            
            for card1, card2, game, reason in test_pairs:
                try:
                    task_id = f"compare_mturk_{card1}_{card2}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    # Queue first
                    queue.queue_for_human_annotation(
                        card1=card1,
                        card2=card2,
                        game=game,
                        priority=AnnotationPriority.HIGH,
                        reason=f"Comparison test: {reason}",
                    )
                    
                    # Create task
                    task = AnnotationTask(
                        task_id=task_id,
                        card1=card1,
                        card2=card2,
                        game=game,
                        instructions=create_improved_instructions(card1, card2, game),
                        context={"reason": reason, "comparison_test": True},
                    )
                    
                    # Submit
                    external_id = mturk_service.submit_task(task)
                    
                    # Update queue
                    queue.update_task_status(
                        task_id,
                        AnnotationStatus.SUBMITTED,
                        external_task_id=external_id,
                        annotation_service="mturk",
                    )
                    
                    results["mturk"]["submitted"].append({
                        "card1": card1,
                        "card2": card2,
                        "external_id": external_id,
                        "task_id": task_id,
                    })
                    print(f"  ✓ Submitted: {card1} vs {card2}")
                    print(f"    HIT ID: {external_id}")
                    print(f"    Cost: $0.12")
                    
                except Exception as e:
                    results["mturk"]["failed"].append({
                        "card1": card1,
                        "card2": card2,
                        "error": str(e),
                    })
                    print(f"  ✗ Failed: {card1} vs {card2} - {e}")
                    import traceback
                    traceback.print_exc()
        except Exception as e:
            print(f"  ✗ MTurk service error: {e}")
            import traceback
            traceback.print_exc()
        print()
    
    # Submit to Scale AI
    if submit_scale:
        print("Submitting to Scale AI...")
        print("-" * 70)
        try:
            scale_service = get_annotation_service("scale")
            
            for card1, card2, game, reason in test_pairs:
                try:
                    task_id = f"compare_scale_{card1}_{card2}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    # Queue first
                    queue.queue_for_human_annotation(
                        card1=card1,
                        card2=card2,
                        game=game,
                        priority=AnnotationPriority.HIGH,
                        reason=f"Comparison test: {reason}",
                    )
                    
                    # Create task
                    task = AnnotationTask(
                        task_id=task_id,
                        card1=card1,
                        card2=card2,
                        game=game,
                        instructions=create_improved_instructions(card1, card2, game),
                        context={"reason": reason, "comparison_test": True},
                    )
                    
                    # Submit
                    external_id = scale_service.submit_task(task)
                    
                    # Update queue
                    queue.update_task_status(
                        task_id,
                        AnnotationStatus.SUBMITTED,
                        external_task_id=external_id,
                        annotation_service="scale",
                    )
                    
                    results["scale"]["submitted"].append({
                        "card1": card1,
                        "card2": card2,
                        "external_id": external_id,
                        "task_id": task_id,
                    })
                    print(f"  ✓ Submitted: {card1} vs {card2}")
                    print(f"    Task ID: {external_id}")
                    print(f"    Cost: $0.50")
                    
                except Exception as e:
                    results["scale"]["failed"].append({
                        "card1": card1,
                        "card2": card2,
                        "error": str(e),
                    })
                    print(f"  ✗ Failed: {card1} vs {card2} - {e}")
                    import traceback
                    traceback.print_exc()
        except Exception as e:
            print(f"  ✗ Scale AI service error: {e}")
            import traceback
            traceback.print_exc()
        print()
    
    # Summary
    print("="*70)
    print("Submission Summary")
    print("="*70)
    print()
    
    mturk_submitted = len(results["mturk"]["submitted"])
    scale_submitted = len(results["scale"]["submitted"])
    
    print(f"MTurk: {mturk_submitted} submitted, {len(results['mturk']['failed'])} failed")
    print(f"Scale AI: {scale_submitted} submitted, {len(results['scale']['failed'])} failed")
    print()
    
    if mturk_submitted > 0 or scale_submitted > 0:
        print("Next steps:")
        print("  1. Wait for annotations to complete (MTurk: hours-days, Scale AI: minutes-hours)")
        print("  2. Retrieve results:")
        print("     python scripts/annotation/submit_human_annotations.py retrieve \\")
        print("         --service mturk --limit 10")
        print("     python scripts/annotation/submit_human_annotations.py retrieve \\")
        print("         --service scale --limit 10")
        print("  3. Compare quality and cost")
    
    # Save results
    import json
    results_file = project_root / "annotations" / "comparison_submission_results.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n✓ Results saved to: {results_file}")
    
    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Submit comparison tasks to MTurk and Scale AI",
    )
    parser.add_argument(
        "--mturk-only",
        action="store_true",
        help="Only submit to MTurk",
    )
    parser.add_argument(
        "--scale-only",
        action="store_true",
        help="Only submit to Scale AI",
    )
    parser.add_argument(
        "--num-tasks",
        type=int,
        default=2,
        help="Number of test tasks per service",
    )

    args = parser.parse_args()

    submit_mturk = not args.scale_only
    submit_scale = not args.mturk_only

    results = submit_comparison_tasks(
        submit_mturk=submit_mturk,
        submit_scale=submit_scale,
        num_tasks=args.num_tasks,
    )

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

