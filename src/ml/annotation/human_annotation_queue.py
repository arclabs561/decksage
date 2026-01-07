"""
Human Annotation Queue System

Queues card pairs for human annotation when:
1. LLM annotations have low confidence/IAA
2. Multi-annotator systems disagree significantly
3. Uncertainty-based selection identifies ambiguous cases
4. User explicitly requests human review

Supports integration with:
- Amazon Mechanical Turk (MTurk)
- Scale AI
- Labelbox
- Appen/Figure Eight
- Custom annotation interfaces
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from ..utils.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


class AnnotationPriority(Enum):
    """Priority levels for human annotation."""

    CRITICAL = "critical"  # High disagreement, needs immediate review
    HIGH = "high"  # Low IAA, uncertain predictions
    MEDIUM = "medium"  # Ambiguous cases, edge cases
    LOW = "low"  # Quality check, validation


class AnnotationStatus(Enum):
    """Status of human annotation task."""

    PENDING = "pending"  # Queued, not yet submitted
    SUBMITTED = "submitted"  # Submitted to annotation service
    IN_PROGRESS = "in_progress"  # Being annotated
    COMPLETED = "completed"  # Annotation received
    REJECTED = "rejected"  # Annotation rejected (quality issues)
    FAILED = "failed"  # Submission/retrieval failed


@dataclass
class HumanAnnotationTask:
    """A task queued for human annotation."""

    task_id: str
    card1: str
    card2: str
    game: str
    priority: AnnotationPriority
    status: AnnotationStatus
    reason: str  # Why this needs human annotation
    llm_annotations: list[dict[str, Any]] | None = None  # LLM predictions for context
    iaa_metrics: dict[str, Any] | None = None  # IAA metrics if available
    uncertainty_score: float | None = None  # Uncertainty if available
    created_at: str | None = None
    submitted_at: str | None = None
    completed_at: str | None = None
    human_annotation: dict[str, Any] | None = None  # Final human annotation
    annotation_service: str | None = None  # Which service (mturk, scale, etc.)
    external_task_id: str | None = None  # Task ID in external service
    cost: float | None = None  # Cost in USD
    annotator_id: str | None = None  # Human annotator ID


class HumanAnnotationQueue:
    """Manages queue of tasks for human annotation."""

    def __init__(self, queue_file: Path | None = None):
        """Initialize human annotation queue.

        Args:
            queue_file: Path to JSON file storing queue (default: annotations/human_annotation_queue.jsonl)
        """
        if queue_file is None:
            from ..utils.paths import PATHS

            queue_file = PATHS.experiments / "annotations" / "human_annotation_queue.jsonl"
            queue_file.parent.mkdir(parents=True, exist_ok=True)

        self.queue_file = queue_file
        self.tasks: dict[str, HumanAnnotationTask] = {}
        self._load_queue()

    def _load_queue(self) -> None:
        """Load existing queue from file."""
        if not self.queue_file.exists():
            return

        try:
            with open(self.queue_file) as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    task = HumanAnnotationTask(**data)
                    # Convert string enums back
                    task.priority = AnnotationPriority(task.priority)
                    task.status = AnnotationStatus(task.status)
                    self.tasks[task.task_id] = task
            logger.info(f"Loaded {len(self.tasks)} tasks from queue")
        except Exception as e:
            logger.warning(f"Failed to load queue: {e}")

    def _save_queue(self) -> None:
        """Save queue to file (atomic write)."""
        temp_file = self.queue_file.with_suffix(self.queue_file.suffix + ".tmp")
        try:
            with open(temp_file, "w") as f:
                for task in self.tasks.values():
                    # Convert to dict, handling enums
                    data = asdict(task)
                    data["priority"] = task.priority.value
                    data["status"] = task.status.value
                    f.write(json.dumps(data) + "\n")
            temp_file.replace(self.queue_file)
            logger.debug(f"Saved {len(self.tasks)} tasks to queue")
        except Exception as e:
            logger.error(f"Failed to save queue: {e}")
            if temp_file.exists():
                temp_file.unlink()

    def queue_for_human_annotation(
        self,
        card1: str,
        card2: str,
        game: str,
        priority: AnnotationPriority,
        reason: str,
        llm_annotations: list[dict[str, Any]] | None = None,
        iaa_metrics: dict[str, Any] | None = None,
        uncertainty_score: float | None = None,
    ) -> str:
        """Queue a pair for human annotation.

        Args:
            card1: First card name
            card2: Second card name
            game: Game name
            priority: Priority level
            reason: Why this needs human annotation
            llm_annotations: Optional LLM predictions for context
            iaa_metrics: Optional IAA metrics
            uncertainty_score: Optional uncertainty score

        Returns:
            Task ID
        """
        task_id = f"{game}_{card1}_{card2}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        task_id = task_id.replace(" ", "_").replace("/", "_")[:100]  # Sanitize

        task = HumanAnnotationTask(
            task_id=task_id,
            card1=card1,
            card2=card2,
            game=game,
            priority=priority,
            status=AnnotationStatus.PENDING,
            reason=reason,
            llm_annotations=llm_annotations,
            iaa_metrics=iaa_metrics,
            uncertainty_score=uncertainty_score,
            created_at=datetime.now().isoformat(),
        )

        self.tasks[task_id] = task
        self._save_queue()

        logger.info(
            f"Queued human annotation: {card1} vs {card2} "
            f"(priority={priority.value}, reason={reason})"
        )

        return task_id

    def get_pending_tasks(
        self,
        priority: AnnotationPriority | None = None,
        limit: int | None = None,
    ) -> list[HumanAnnotationTask]:
        """Get pending tasks, optionally filtered by priority.

        Args:
            priority: Optional priority filter
            limit: Optional limit on number of tasks

        Returns:
            List of pending tasks
        """
        pending = [
            task
            for task in self.tasks.values()
            if task.status == AnnotationStatus.PENDING
            and (priority is None or task.priority == priority)
        ]

        # Sort by priority (critical first)
        priority_order = {
            AnnotationPriority.CRITICAL: 0,
            AnnotationPriority.HIGH: 1,
            AnnotationPriority.MEDIUM: 2,
            AnnotationPriority.LOW: 3,
        }
        pending.sort(key=lambda t: priority_order.get(t.priority, 99))

        if limit:
            pending = pending[:limit]

        return pending

    def update_task_status(
        self,
        task_id: str,
        status: AnnotationStatus,
        human_annotation: dict[str, Any] | None = None,
        external_task_id: str | None = None,
        cost: float | None = None,
        annotator_id: str | None = None,
    ) -> None:
        """Update task status and annotation.

        Args:
            task_id: Task ID
            status: New status
            human_annotation: Optional human annotation result
            external_task_id: Optional external service task ID
            cost: Optional cost in USD
            annotator_id: Optional annotator ID
        """
        if task_id not in self.tasks:
            logger.warning(f"Task {task_id} not found in queue")
            return

        task = self.tasks[task_id]
        task.status = status

        if status == AnnotationStatus.SUBMITTED:
            task.submitted_at = datetime.now().isoformat()
            if external_task_id:
                task.external_task_id = external_task_id

        if status == AnnotationStatus.COMPLETED:
            task.completed_at = datetime.now().isoformat()
            if human_annotation:
                task.human_annotation = human_annotation
            if annotator_id:
                task.annotator_id = annotator_id

        if cost is not None:
            task.cost = cost

        self._save_queue()
        logger.info(f"Updated task {task_id} status to {status.value}")

    def get_statistics(self) -> dict[str, Any]:
        """Get queue statistics.

        Returns:
            Dict with counts by status, priority, etc.
        """
        stats = {
            "total": len(self.tasks),
            "by_status": {},
            "by_priority": {},
            "by_game": {},
            "total_cost": 0.0,
        }

        for task in self.tasks.values():
            # Status counts
            status_key = task.status.value
            stats["by_status"][status_key] = stats["by_status"].get(status_key, 0) + 1

            # Priority counts
            priority_key = task.priority.value
            stats["by_priority"][priority_key] = (
                stats["by_priority"].get(priority_key, 0) + 1
            )

            # Game counts
            game_key = task.game
            stats["by_game"][game_key] = stats["by_game"].get(game_key, 0) + 1

            # Cost
            if task.cost:
                stats["total_cost"] += task.cost

        return stats


def queue_low_iaa_annotations(
    queue: HumanAnnotationQueue,
    multi_annotator_results: list[Any],  # MultiAnnotatorResult
    min_iaa_threshold: float = 0.4,
) -> int:
    """Queue annotations with low IAA for human review.

    Args:
        queue: Human annotation queue
        multi_annotator_results: List of MultiAnnotatorResult
        min_iaa_threshold: Minimum IAA threshold (below this = queue for human)

    Returns:
        Number of tasks queued
    """
    queued = 0

    for result in multi_annotator_results:
        alpha = result.iaa_metrics.get("krippendorff_alpha", 1.0)
        if alpha < min_iaa_threshold:
            priority = (
                AnnotationPriority.CRITICAL
                if alpha < 0.2
                else AnnotationPriority.HIGH
                if alpha < 0.3
                else AnnotationPriority.MEDIUM
            )

            # Convert annotations to dicts
            llm_anns = []
            for name, ann in result.annotations.items():
                if hasattr(ann, "model_dump"):
                    llm_anns.append(ann.model_dump())
                else:
                    llm_anns.append(dict(ann))

            queue.queue_for_human_annotation(
                card1=result.card1,
                card2=result.card2,
                game="unknown",  # Should be extracted from result
                priority=priority,
                reason=f"Low IAA (α={alpha:.3f} < {min_iaa_threshold})",
                llm_annotations=llm_anns,
                iaa_metrics=result.iaa_metrics,
            )
            queued += 1

    logger.info(f"Queued {queued} annotations with low IAA for human review")
    return queued


def queue_uncertain_pairs(
    queue: HumanAnnotationQueue,
    uncertain_pairs: list[Any],  # PairUncertainty
    min_uncertainty: float = 0.7,
    game: str = "unknown",
) -> int:
    """Queue highly uncertain pairs for human annotation.

    Args:
        queue: Human annotation queue
        uncertain_pairs: List of PairUncertainty
        min_uncertainty: Minimum uncertainty to queue
        game: Game name

    Returns:
        Number of tasks queued
    """
    queued = 0

    for pair in uncertain_pairs:
        if pair.combined_score >= min_uncertainty:
            priority = (
                AnnotationPriority.CRITICAL
                if pair.combined_score >= 0.9
                else AnnotationPriority.HIGH
            )

            queue.queue_for_human_annotation(
                card1=pair.card1,
                card2=pair.card2,
                game=game,
                priority=priority,
                reason=f"High uncertainty (score={pair.combined_score:.3f})",
                uncertainty_score=pair.combined_score,
            )
            queued += 1

    logger.info(f"Queued {queued} uncertain pairs for human review")
    return queued

