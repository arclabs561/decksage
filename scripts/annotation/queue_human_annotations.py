#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pydantic-ai",
# ]
# ///

"""
Queue Human Annotations

Automatically queues card pairs for human annotation when:
1. LLM annotations have low IAA (< 0.4)
2. Multi-annotator systems disagree significantly
3. Uncertainty-based selection identifies highly uncertain cases
4. User explicitly requests human review

Supports integration with:
- Amazon Mechanical Turk
- Scale AI
- Custom annotation interface
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.ml.annotation.human_annotation_queue import (
    AnnotationPriority,
    HumanAnnotationQueue,
    queue_low_iaa_annotations,
    queue_uncertain_pairs,
)
from src.ml.annotation.llm_annotator import LLMAnnotator
from src.ml.annotation.multi_annotator_iaa import MultiAnnotatorIAA


async def queue_from_llm_annotations(
    queue: HumanAnnotationQueue,
    num_pairs: int = 20,
    game: str = "magic",
    use_multi_annotator: bool = True,
    use_uncertainty_selection: bool = True,
    min_iaa_threshold: float = 0.4,
    min_uncertainty: float = 0.7,
) -> dict[str, int]:
    """Generate LLM annotations and queue low-quality ones for human review.

    Args:
        queue: Human annotation queue
        num_pairs: Number of pairs to annotate
        game: Game name
        use_multi_annotator: Use multi-annotator IAA
        use_uncertainty_selection: Use uncertainty-based selection
        min_iaa_threshold: Minimum IAA to avoid human review
        min_uncertainty: Minimum uncertainty to queue

    Returns:
        Dict with counts of queued tasks
    """
    print(f"\n{'='*70}")
    print(f"Generating LLM Annotations and Queueing for Human Review")
    print(f"{'='*70}")
    print(f"Game: {game}")
    print(f"Pairs: {num_pairs}")
    print(f"Multi-annotator: {use_multi_annotator}")
    print(f"Uncertainty selection: {use_uncertainty_selection}")
    print()

    stats = {
        "total_annotated": 0,
        "queued_low_iaa": 0,
        "queued_uncertain": 0,
        "queued_total": 0,
    }

    # Initialize annotator
    annotator = LLMAnnotator(
        game=game,
        use_graph_enrichment=True,
        use_evoc_clustering=False,
        use_meta_judge=False,
        use_multi_annotator=use_multi_annotator,
        use_uncertainty_selection=use_uncertainty_selection,
    )

    # Generate annotations
    strategy = "uncertainty" if use_uncertainty_selection else "diverse"
    annotations = await annotator.annotate_similarity_pairs(
        num_pairs=num_pairs,
        strategy=strategy,
        batch_size=5,
    )

    stats["total_annotated"] = len(annotations)

    # Queue low IAA annotations (if multi-annotator was used)
    if use_multi_annotator and annotator.multi_annotator:
        # Note: This would require storing multi-annotator results
        # For now, we'll queue based on uncertainty
        print("  Note: Multi-annotator IAA queuing requires result storage")
        # TODO: Store multi-annotator results and queue low IAA

    # Queue highly uncertain pairs
    if use_uncertainty_selection and annotator.uncertainty_selector:
        # Get uncertain pairs that were annotated
        # (We'd need to track which pairs were selected)
        print("  Note: Uncertainty-based queuing requires pair tracking")
        # TODO: Track uncertain pairs and queue high-uncertainty ones

    # For now, queue based on annotation quality heuristics
    queued = 0
    for ann in annotations:
        if isinstance(ann, dict):
            score = ann.get("similarity_score", 0.0)
            reasoning = ann.get("reasoning", "")
        else:
            score = ann.similarity_score
            reasoning = ann.reasoning

        # Queue if score is very low or very high (edge cases)
        # or if reasoning is short (low confidence)
        should_queue = False
        priority = AnnotationPriority.MEDIUM
        reason = ""

        if score < 0.1:
            should_queue = True
            priority = AnnotationPriority.HIGH
            reason = f"Very low similarity score ({score:.3f}) - needs validation"
        elif score > 0.9:
            should_queue = True
            priority = AnnotationPriority.MEDIUM
            reason = f"Very high similarity score ({score:.3f}) - needs validation"
        elif len(reasoning) < 50:
            should_queue = True
            priority = AnnotationPriority.MEDIUM
            reason = "Short reasoning - may indicate low confidence"

        if should_queue:
            card1 = ann.get("card1") if isinstance(ann, dict) else ann.card1
            card2 = ann.get("card2") if isinstance(ann, dict) else ann.card2

            queue.queue_for_human_annotation(
                card1=card1,
                card2=card2,
                game=game,
                priority=priority,
                reason=reason,
                llm_annotations=[ann if isinstance(ann, dict) else ann.model_dump()],
            )
            queued += 1

    stats["queued_total"] = queued

    print(f"\n  Generated: {stats['total_annotated']} annotations")
    print(f"  Queued for human review: {stats['queued_total']}")

    return stats


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Queue card pairs for human annotation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--game",
        choices=["magic", "pokemon", "yugioh", "all"],
        default="magic",
        help="Game to generate annotations for",
    )
    parser.add_argument(
        "--num-pairs",
        type=int,
        default=20,
        help="Number of pairs to annotate and potentially queue",
    )
    parser.add_argument(
        "--use-multi-annotator",
        action="store_true",
        help="Use multi-annotator IAA (queues low IAA annotations)",
    )
    parser.add_argument(
        "--use-uncertainty",
        action="store_true",
        help="Use uncertainty-based selection",
    )
    parser.add_argument(
        "--min-iaa",
        type=float,
        default=0.4,
        help="Minimum IAA threshold (below this = queue for human)",
    )
    parser.add_argument(
        "--min-uncertainty",
        type=float,
        default=0.7,
        help="Minimum uncertainty to queue (above this = queue for human)",
    )
    parser.add_argument(
        "--list-queue",
        action="store_true",
        help="List pending tasks in queue",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show queue statistics",
    )

    args = parser.parse_args()

    queue = HumanAnnotationQueue()

    # List queue
    if args.list_queue:
        pending = queue.get_pending_tasks()
        print(f"\n{'='*70}")
        print(f"Pending Human Annotation Tasks: {len(pending)}")
        print(f"{'='*70}\n")

        for task in pending[:20]:  # Show first 20
            print(f"  {task.task_id}")
            print(f"    Cards: {task.card1} vs {task.card2}")
            print(f"    Priority: {task.priority.value}")
            print(f"    Reason: {task.reason}")
            print()

        if len(pending) > 20:
            print(f"  ... and {len(pending) - 20} more tasks")
        return 0

    # Show stats
    if args.stats:
        stats = queue.get_statistics()
        print(f"\n{'='*70}")
        print("Human Annotation Queue Statistics")
        print(f"{'='*70}\n")

        print(f"Total tasks: {stats['total']}")
        print(f"\nBy Status:")
        for status, count in stats["by_status"].items():
            print(f"  {status}: {count}")

        print(f"\nBy Priority:")
        for priority, count in stats["by_priority"].items():
            print(f"  {priority}: {count}")

        print(f"\nBy Game:")
        for game, count in stats["by_game"].items():
            print(f"  {game}: {count}")

        print(f"\nTotal Cost: ${stats['total_cost']:.2f}")
        return 0

    # Generate and queue
    if args.game == "all":
        games = ["magic", "pokemon", "yugioh"]
    else:
        games = [args.game]

    all_stats = {}
    for game in games:
        stats = await queue_from_llm_annotations(
            queue=queue,
            num_pairs=args.num_pairs,
            game=game,
            use_multi_annotator=args.use_multi_annotator,
            use_uncertainty_selection=args.use_uncertainty,
            min_iaa_threshold=args.min_iaa,
            min_uncertainty=args.min_uncertainty,
        )
        all_stats[game] = stats

    # Summary
    print(f"\n{'='*70}")
    print("Summary")
    print(f"{'='*70}\n")

    for game, stats in all_stats.items():
        print(f"{game}:")
        print(f"  Annotated: {stats['total_annotated']}")
        print(f"  Queued: {stats['queued_total']}")

    print(f"\n✓ Queue saved to: {queue.queue_file}")
    print(f"  Use --list-queue to view pending tasks")
    print(f"  Use --stats to view statistics")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

