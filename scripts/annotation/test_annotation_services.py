#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "boto3",
#   "requests",
# ]
# ///

"""
Test and Compare Annotation Services

Tests all annotation services (MTurk, Scale AI, Custom) with a small batch
and analyzes quality vs price.
"""

import argparse
import asyncio
import json
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
    MTurkService,
    ScaleAIService,
    CustomAnnotationService,
)
from src.ml.annotation.human_annotation_queue import (
    AnnotationPriority,
    HumanAnnotationQueue,
)


def test_service(
    service_name: str,
    num_tasks: int = 3,
    dry_run: bool = True,
) -> dict:
    """Test an annotation service with a small batch.

    Args:
        service_name: Service name ("mturk", "scale", "custom")
        num_tasks: Number of test tasks
        dry_run: If True, don't actually submit (just test setup)

    Returns:
        Test results dict
    """
    print(f"\n{'='*70}")
    print(f"Testing {service_name.upper()} Service")
    print(f"{'='*70}\n")

    results = {
        "service": service_name,
        "available": False,
        "cost_per_task": 0.0,
        "estimated_total": 0.0,
        "setup_ok": False,
        "error": None,
    }

    try:
        # Get service
        service = get_annotation_service(service_name)
        results["setup_ok"] = True
        print(f"✓ Service initialized")

        # Estimate cost
        estimated_cost = service.estimate_cost(num_tasks)
        results["cost_per_task"] = estimated_cost / num_tasks if num_tasks > 0 else 0.0
        results["estimated_total"] = estimated_cost
        print(f"  Cost per task: ${results['cost_per_task']:.2f}")
        print(f"  Estimated total ({num_tasks} tasks): ${estimated_cost:.2f}")

        if dry_run:
            print(f"\n  [DRY RUN - Not actually submitting]")
            results["available"] = True
            return results

        # Create test tasks
        test_pairs = [
            ("Lightning Bolt", "Shock", "magic"),
            ("Counterspell", "Mana Leak", "magic"),
            ("Black Lotus", "Mox Pearl", "magic"),
        ][:num_tasks]

        submitted = []
        for i, (card1, card2, game) in enumerate(test_pairs, 1):
            try:
                task = AnnotationTask(
                    task_id=f"test_{service_name}_{i}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    card1=card1,
                    card2=card2,
                    game=game,
                    instructions=f"""
Rate the similarity between these two {game} cards:

Card 1: {card1}
Card 2: {card2}

Consider:
- Functional similarity (can they replace each other?)
- Synergy (do they work well together?)
- Archetype (same deck type?)
- Power level (similar strength?)

Provide:
1. Similarity score (0.0-1.0)
2. Similarity type (functional, synergy, archetype, manabase, unrelated)
3. Can Card 2 substitute for Card 1? (yes/no)
4. Reasoning (why this score?)
""",
                )

                external_id = service.submit_task(task)
                submitted.append({
                    "task_id": task.task_id,
                    "external_id": external_id,
                    "card1": card1,
                    "card2": card2,
                })
                print(f"  ✓ Submitted task {i}: {card1} vs {card2} (ID: {external_id})")

            except Exception as e:
                print(f"  ✗ Failed to submit task {i}: {e}")
                results["error"] = str(e)

        results["submitted"] = submitted
        results["available"] = len(submitted) > 0

        if submitted:
            print(f"\n  Submitted {len(submitted)}/{num_tasks} tasks successfully")
            print(f"  Note: Results will be available later (check with retrieve command)")

    except Exception as e:
        print(f"  ✗ Service test failed: {e}")
        results["error"] = str(e)
        import traceback
        traceback.print_exc()

    return results


def compare_services(
    num_tasks: int = 3,
    dry_run: bool = True,
) -> dict:
    """Compare all annotation services.

    Args:
        num_tasks: Number of test tasks per service
        dry_run: If True, don't actually submit

    Returns:
        Comparison results
    """
    print(f"\n{'='*70}")
    print("Annotation Services Comparison")
    print(f"{'='*70}")

    services = ["mturk", "scale", "custom"]
    results = {}

    for service_name in services:
        try:
            result = test_service(service_name, num_tasks=num_tasks, dry_run=dry_run)
            results[service_name] = result
        except Exception as e:
            print(f"\n✗ Failed to test {service_name}: {e}")
            results[service_name] = {"error": str(e), "available": False}

    # Comparison summary
    print(f"\n{'='*70}")
    print("Comparison Summary")
    print(f"{'='*70}\n")

    print(f"{'Service':<15} {'Available':<12} {'Cost/Task':<12} {'Total (100)':<15} {'Quality':<10}")
    print("-" * 70)

    for service_name, result in results.items():
        available = "✓ Yes" if result.get("available") else "✗ No"
        cost_per = result.get("cost_per_task", 0.0)
        total_100 = cost_per * 100
        quality = "High" if service_name == "scale" else "Medium" if service_name == "mturk" else "Variable"
        
        error = result.get("error")
        if error:
            available = f"✗ Error"
        
        print(f"{service_name:<15} {available:<12} ${cost_per:<11.2f} ${total_100:<14.2f} {quality:<10}")

    # Recommendations
    print(f"\n{'='*70}")
    print("Recommendations")
    print(f"{'='*70}\n")

    if results.get("mturk", {}).get("available"):
        print("✓ MTurk: Best for large-scale, cost-effective annotation")
        print("  - Lowest cost (~$0.10/task)")
        print("  - Good quality with proper qualifications")
        print("  - Best for: 100+ annotations, budget-conscious")

    if results.get("scale", {}).get("available"):
        print("✓ Scale AI: Best for high-quality, specialized annotation")
        print("  - Higher cost (~$0.50/task)")
        print("  - Highest quality (specialized annotators)")
        print("  - Best for: Critical annotations, evaluation data")

    if results.get("custom", {}).get("available"):
        print("✓ Custom: Best for internal/expert annotation")
        print("  - Free (internal annotators)")
        print("  - Quality depends on annotators")
        print("  - Best for: Expert review, validation")

    print(f"\n  Hybrid Approach:")
    print(f"    - Use MTurk for large-scale training data")
    print(f"    - Use Scale AI for critical evaluation data")
    print(f"    - Use Custom for expert validation")

    # Save results
    output_file = project_root / "annotations" / "service_comparison.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n✓ Results saved to: {output_file}")

    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test and compare annotation services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--service",
        choices=["mturk", "scale", "custom", "all"],
        default="all",
        help="Service to test",
    )
    parser.add_argument(
        "--num-tasks",
        type=int,
        default=3,
        help="Number of test tasks per service",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Don't actually submit (default: True)",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Actually submit tasks (overrides --dry-run)",
    )

    args = parser.parse_args()

    dry_run = not args.submit

    if args.service == "all":
        results = compare_services(num_tasks=args.num_tasks, dry_run=dry_run)
    else:
        results = test_service(args.service, num_tasks=args.num_tasks, dry_run=dry_run)

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

