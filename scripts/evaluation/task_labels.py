"""Task -> annotation field mapping (ADR-0001).

Each evaluation task reads exactly one annotation score field, and a pair is
read only by the task it names. This module is the single source of that
mapping: `eval_per_mode.py`, `eval_fusion.py`, and `sweep_fusion_alpha.py`
import it instead of carrying their own copy.
"""

from __future__ import annotations


# Task -> the one annotation score field that measures it (ADR-0001).
TASK_SCORE_FIELD = {
    "substitute": "functional_score",
    "synergy": "synergy_score",
    "meta": "meta_relevance",
}
TASKS = tuple(TASK_SCORE_FIELD)


def pair_task(ann: dict) -> str | None:
    """The task a pair was annotated for, or None for legacy (pre-ADR-0001) pairs."""
    task = ann.get("task")
    if not isinstance(task, str):
        return None
    return task.strip().lower() or None
