#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "boto3",
#   "requests",
# ]
# ///

"""
Review and Test All Annotation Services

1. Reviews task definitions and guidelines
2. Submits test tasks to MTurk and Scale AI
3. Explains custom service
4. Shows where annotations are stored
5. Compares quality/price
"""

import argparse
import json
import os
import sys
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
)
from src.ml.utils.paths import PATHS


def review_task_definition() -> dict:
    """Review and improve task definition."""
    print("="*70)
    print("Task Definition Review")
    print("="*70)
    print()
    
    # Current task definition
    current_instructions = """
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
"""
    
    print("Current Instructions:")
    print("-" * 70)
    print(current_instructions)
    print()
    
    # Improved version with examples and clearer guidelines
    improved_instructions = """
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
    
    print("Improved Instructions (with examples):")
    print("-" * 70)
    print(improved_instructions)
    print()
    
    # Assessment
    issues = []
    improvements = []
    
    issues.append("❌ Missing score examples (annotators may not know what 0.5 means)")
    issues.append("❌ No clear substitution criteria")
    issues.append("❌ Vague similarity type definitions")
    
    improvements.append("✅ Added score range examples (0.0-1.0 with card examples)")
    improvements.append("✅ Added clear substitution criteria")
    improvements.append("✅ Added detailed similarity type definitions")
    improvements.append("✅ Added reasoning requirements")
    improvements.append("✅ Added consistency guidelines")
    
    print("Issues Found:")
    for issue in issues:
        print(f"  {issue}")
    print()
    
    print("Improvements Made:")
    for improvement in improvements:
        print(f"  {improvement}")
    print()
    
    return {
        "current": current_instructions,
        "improved": improved_instructions,
        "issues": issues,
        "improvements": improvements,
    }


def explain_custom_service():
    """Explain what custom service is."""
    print("="*70)
    print("Custom Annotation Service Explanation")
    print("="*70)
    print()
    
    print("What is 'Custom' Service?")
    print("-" * 70)
    print()
    print("❌ NOT our own LLMs (those are separate)")
    print("✅ Internal/expert human annotation interface")
    print()
    print("Purpose:")
    print("  - For internal team members or domain experts to annotate")
    print("  - No external service, no cost")
    print("  - Full control over annotator selection")
    print()
    print("How it works:")
    print("  1. Tasks saved to files: experiments/annotations/human_tasks/")
    print("  2. Human annotator opens file and fills in annotation")
    print("  3. File updated with annotation result")
    print("  4. System retrieves completed annotations")
    print()
    print("Storage:")
    custom_dir = PATHS.experiments / "annotations" / "human_tasks"
    print(f"  Directory: {custom_dir}")
    print(f"  Format: JSON files (one per task)")
    print(f"  Example: {custom_dir}/task_001.json")
    print()
    print("Use cases:")
    print("  - Expert validation (you or team members)")
    print("  - Quality control (spot checks)")
    print("  - When you want full control")
    print("  - No budget for external services")
    print()


def show_annotation_storage():
    """Show where annotations are stored."""
    print("="*70)
    print("Annotation Storage Locations")
    print("="*70)
    print()
    
    # Queue storage
    queue_file = PATHS.experiments / "annotations" / "human_annotation_queue.jsonl"
    print("1. Human Annotation Queue:")
    print(f"   Location: {queue_file}")
    print(f"   Format: JSONL (one task per line)")
    print(f"   Contains: All queued tasks (pending, submitted, completed)")
    print(f"   Status: {'✓ Exists' if queue_file.exists() else '✗ Not created yet'}")
    print()
    
    # Custom task storage
    custom_dir = PATHS.experiments / "annotations" / "human_tasks"
    print("2. Custom Annotation Tasks:")
    print(f"   Location: {custom_dir}")
    print(f"   Format: JSON files (one per task)")
    print(f"   Contains: Tasks for internal annotation")
    print(f"   Status: {'✓ Exists' if custom_dir.exists() else '✗ Not created yet'}")
    if custom_dir.exists():
        task_files = list(custom_dir.glob("*.json"))
        print(f"   Files: {len(task_files)} task files")
    print()
    
    # Final annotations (after retrieval)
    annotations_dir = PATHS.experiments / "annotations"
    print("3. Final Human Annotations:")
    print(f"   Location: {annotations_dir}/human_annotations_*.jsonl")
    print(f"   Format: JSONL (one annotation per line)")
    print(f"   Contains: Completed human annotations from all services")
    print(f"   Status: Created when annotations are retrieved")
    print()
    
    # Integration with main annotation system
    main_annotations = project_root / "annotations"
    print("4. Main Annotation Directory:")
    print(f"   Location: {main_annotations}")
    print(f"   Contains: All annotation sources (LLM, human, etc.)")
    print(f"   Status: {'✓ Exists' if main_annotations.exists() else '✗ Not created yet'}")
    print()


def submit_test_tasks(
    submit_mturk: bool = False,
    submit_scale: bool = False,
    num_tasks: int = 1,
) -> dict:
    """Submit test tasks to services for comparison."""
    print("="*70)
    print("Submitting Test Tasks")
    print("="*70)
    print()
    
    # Create test tasks
    test_pairs = [
        ("Lightning Bolt", "Shock", "magic", "High similarity - both deal 3 damage"),
        ("Counterspell", "Mana Leak", "magic", "High similarity - both counter spells"),
        ("Black Lotus", "Mox Pearl", "magic", "Medium similarity - both fast mana"),
    ][:num_tasks]
    
    results = {
        "mturk": {"submitted": [], "failed": []},
        "scale": {"submitted": [], "failed": []},
    }
    
    improved_instructions = """
CARD SIMILARITY ANNOTATION TASK

Your task: Rate how similar two {game} cards are to each other.

CARDS TO COMPARE:
- Card 1: {card1}
- Card 2: {card2}

SCORING GUIDELINES (0.0 - 1.0):
0.9-1.0: Nearly identical (direct substitutes)
0.7-0.8: Very similar (same role, minor differences)
0.5-0.6: Moderately similar (related function)
0.3-0.4: Somewhat similar (loose connection)
0.1-0.2: Marginally similar (minimal connection)
0.0-0.1: Unrelated (different function)

SIMILARITY TYPES:
- functional: Same function (can replace each other)
- synergy: Work well together
- archetype: Same deck type
- manabase: Both lands/mana
- unrelated: No clear relationship

SUBSTITUTION: Can Card 2 replace Card 1? (yes/no)

REASONING: 2-3 sentences explaining your score
"""
    
    # Submit to MTurk
    if submit_mturk:
        print("Submitting to MTurk...")
        print("-" * 70)
        try:
            mturk_service = get_annotation_service("mturk")
            
            for card1, card2, game, reason in test_pairs:
                try:
                    task = AnnotationTask(
                        task_id=f"test_mturk_{card1}_{card2}",
                        card1=card1,
                        card2=card2,
                        game=game,
                        instructions=improved_instructions.format(
                            game=game, card1=card1, card2=card2
                        ),
                        context={"reason": reason},
                    )
                    
                    external_id = mturk_service.submit_task(task)
                    results["mturk"]["submitted"].append({
                        "card1": card1,
                        "card2": card2,
                        "external_id": external_id,
                    })
                    print(f"  ✓ Submitted: {card1} vs {card2} (HIT: {external_id})")
                    
                except Exception as e:
                    results["mturk"]["failed"].append({
                        "card1": card1,
                        "card2": card2,
                        "error": str(e),
                    })
                    print(f"  ✗ Failed: {card1} vs {card2} - {e}")
        except Exception as e:
            print(f"  ✗ MTurk service error: {e}")
        print()
    
    # Submit to Scale AI
    if submit_scale:
        print("Submitting to Scale AI...")
        print("-" * 70)
        try:
            scale_service = get_annotation_service("scale")
            
            for card1, card2, game, reason in test_pairs:
                try:
                    task = AnnotationTask(
                        task_id=f"test_scale_{card1}_{card2}",
                        card1=card1,
                        card2=card2,
                        game=game,
                        instructions=improved_instructions.format(
                            game=game, card1=card1, card2=card2
                        ),
                        context={"reason": reason},
                    )
                    
                    external_id = scale_service.submit_task(task)
                    results["scale"]["submitted"].append({
                        "card1": card1,
                        "card2": card2,
                        "external_id": external_id,
                    })
                    print(f"  ✓ Submitted: {card1} vs {card2} (Task: {external_id})")
                    
                except Exception as e:
                    results["scale"]["failed"].append({
                        "card1": card1,
                        "card2": card2,
                        "error": str(e),
                    })
                    print(f"  ✗ Failed: {card1} vs {card2} - {e}")
        except Exception as e:
            print(f"  ✗ Scale AI service error: {e}")
        print()
    
    return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Review and test annotation services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Review task definitions",
    )
    parser.add_argument(
        "--explain-custom",
        action="store_true",
        help="Explain custom service",
    )
    parser.add_argument(
        "--show-storage",
        action="store_true",
        help="Show annotation storage locations",
    )
    parser.add_argument(
        "--submit-mturk",
        action="store_true",
        help="Submit test tasks to MTurk",
    )
    parser.add_argument(
        "--submit-scale",
        action="store_true",
        help="Submit test tasks to Scale AI",
    )
    parser.add_argument(
        "--num-tasks",
        type=int,
        default=1,
        help="Number of test tasks to submit",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Do everything (review, explain, show storage)",
    )

    args = parser.parse_args()

    if args.all or args.review:
        review_task_definition()

    if args.all or args.explain_custom:
        explain_custom_service()

    if args.all or args.show_storage:
        show_annotation_storage()

    if args.submit_mturk or args.submit_scale:
        submit_test_tasks(
            submit_mturk=args.submit_mturk,
            submit_scale=args.submit_scale,
            num_tasks=args.num_tasks,
        )

    if not any([args.review, args.explain_custom, args.show_storage, args.submit_mturk, args.submit_scale, args.all]):
        # Default: do everything except submit
        review_task_definition()
        explain_custom_service()
        show_annotation_storage()
        print("\n" + "="*70)
        print("To submit test tasks:")
        print("  python scripts/annotation/review_and_test_services.py \\")
        print("      --submit-mturk --submit-scale --num-tasks 1")
        print("="*70)

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

