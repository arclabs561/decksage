#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///

"""
Submit Human Annotation Tasks to Services

Submits queued tasks to annotation services:
- Amazon Mechanical Turk
- Scale AI
- Custom annotation interface

Retrieves results and updates queue.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.ml.annotation.human_annotation_queue import (
    AnnotationStatus,
    HumanAnnotationQueue,
)
from src.ml.annotation.human_annotation_services import (
    AnnotationTask,
    get_annotation_service,
)


def submit_tasks(
    service_name: str = "custom",
    priority: str | None = None,
    limit: int = 10,
    dry_run: bool = False,
) -> dict[str, int]:
    """Submit pending tasks to annotation service.

    Args:
        service_name: Service name ("mturk", "scale", "custom")
        priority: Optional priority filter ("critical", "high", "medium", "low")
        limit: Maximum number of tasks to submit
        dry_run: If True, don't actually submit

    Returns:
        Dict with submission statistics
    """
    queue = HumanAnnotationQueue()
    service = get_annotation_service(service_name)

    # Get pending tasks
    from src.ml.annotation.human_annotation_queue import AnnotationPriority

    priority_enum = None
    if priority:
        priority_enum = AnnotationPriority(priority)

    pending = queue.get_pending_tasks(priority=priority_enum, limit=limit)

    if not pending:
        print(f"No pending tasks to submit")
        return {"submitted": 0, "failed": 0}

    print(f"\n{'='*70}")
    print(f"Submitting {len(pending)} tasks to {service_name}")
    print(f"{'='*70}\n")

    if dry_run:
        print("  [DRY RUN - Not actually submitting]\n")

    submitted = 0
    failed = 0

    for task in pending:
        if dry_run:
            print(f"  Would submit: {task.card1} vs {task.card2} (priority: {task.priority.value})")
            submitted += 1
            continue

        try:
            # Create annotation task
            annotation_task = AnnotationTask(
                task_id=task.task_id,
                card1=task.card1,
                card2=task.card2,
                game=task.game,
                instructions=f"""
Rate the similarity between these two {task.game} cards:

Card 1: {task.card1}
Card 2: {task.card2}

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

Context: {task.reason}
""",
                context={
                    "llm_annotations": task.llm_annotations,
                    "iaa_metrics": task.iaa_metrics,
                    "uncertainty_score": task.uncertainty_score,
                },
            )

            # Submit to service
            external_id = service.submit_task(annotation_task)

            # Update queue
            queue.update_task_status(
                task.task_id,
                AnnotationStatus.SUBMITTED,
                external_task_id=external_id,
                annotation_service=service_name,
            )

            print(f"  ✓ Submitted: {task.card1} vs {task.card2} (ID: {external_id})")
            submitted += 1

        except Exception as e:
            print(f"  ✗ Failed: {task.card1} vs {task.card2} - {e}")
            failed += 1

    print(f"\n  Submitted: {submitted}, Failed: {failed}")

    return {"submitted": submitted, "failed": failed}


def retrieve_results(
    service_name: str = "custom",
    limit: int = 50,
) -> dict[str, int]:
    """Retrieve completed annotations from service.

    Args:
        service_name: Service name
        limit: Maximum number of tasks to check

    Returns:
        Dict with retrieval statistics
    """
    queue = HumanAnnotationQueue()
    service = get_annotation_service(service_name)

    # Get submitted tasks
    submitted_tasks = [
        task
        for task in queue.tasks.values()
        if task.status == AnnotationStatus.SUBMITTED
        and task.annotation_service == service_name
    ][:limit]

    if not submitted_tasks:
        print(f"No submitted tasks to retrieve")
        return {"retrieved": 0, "pending": 0, "failed": 0}

    print(f"\n{'='*70}")
    print(f"Retrieving results from {service_name}")
    print(f"{'='*70}\n")

    retrieved = 0
    pending = 0
    failed = 0

    for task in submitted_tasks:
        if not task.external_task_id:
            continue

        try:
            result = service.get_result(task.external_task_id)

            if result is None:
                pending += 1
                continue

            # Update queue with result
            queue.update_task_status(
                task.task_id,
                AnnotationStatus.COMPLETED,
                human_annotation={
                    "similarity_score": result.similarity_score,
                    "similarity_type": result.similarity_type,
                    "reasoning": result.reasoning,
                    "is_substitute": result.is_substitute,
                },
                cost=result.cost,
                annotator_id=result.annotator_id,
            )

            print(
                f"  ✓ Retrieved: {task.card1} vs {task.card2} "
                f"(score: {result.similarity_score:.3f}, cost: ${result.cost:.2f})"
            )
            retrieved += 1

        except Exception as e:
            print(f"  ✗ Failed: {task.card1} vs {task.card2} - {e}")
            failed += 1

    print(f"\n  Retrieved: {retrieved}, Pending: {pending}, Failed: {failed}")

    return {"retrieved": retrieved, "pending": pending, "failed": failed}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Submit and retrieve human annotations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "action",
        choices=["submit", "retrieve", "both"],
        help="Action to perform",
    )
    parser.add_argument(
        "--service",
        choices=["mturk", "scale", "custom"],
        default="custom",
        help="Annotation service to use",
    )
    parser.add_argument(
        "--priority",
        choices=["critical", "high", "medium", "low"],
        help="Only submit/retrieve tasks with this priority",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of tasks",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually submit (dry run)",
    )

    args = parser.parse_args()

    if args.action in ["submit", "both"]:
        submit_tasks(
            service_name=args.service,
            priority=args.priority,
            limit=args.limit,
            dry_run=args.dry_run,
        )

    if args.action in ["retrieve", "both"]:
        retrieve_results(
            service_name=args.service,
            limit=args.limit,
        )

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

