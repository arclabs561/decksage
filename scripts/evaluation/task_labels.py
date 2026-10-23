"""Task -> annotation field mapping (ADR-0001).

Each evaluation task reads exactly one annotation score field, and a pair is
read only by the task it names. This module is the single source of that
mapping: `eval_per_mode.py`, `eval_fusion.py`, and `sweep_fusion_alpha.py`
import it instead of carrying their own copy.

The types are the contract. `Task` and `ScoreField` are string enums, so a
misspelt task is a type error rather than a silent miss, while still comparing
and hashing equal to the plain strings stored in the annotation files.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class Task(StrEnum):
    """The question a pair was annotated for."""

    SUBSTITUTE = "substitute"
    SYNERGY = "synergy"
    META = "meta"


class ScoreField(StrEnum):
    """The one annotation field that measures a task (ADR-0001)."""

    FUNCTIONAL = "functional_score"
    SYNERGY = "synergy_score"
    META = "meta_relevance"


# Task -> the one annotation score field that measures it.
TASK_SCORE_FIELD: Final[Mapping[Task, ScoreField]] = MappingProxyType(
    {
        Task.SUBSTITUTE: ScoreField.FUNCTIONAL,
        Task.SYNERGY: ScoreField.SYNERGY,
        Task.META: ScoreField.META,
    }
)
TASKS: Final[tuple[Task, ...]] = tuple(TASK_SCORE_FIELD)


def pair_task(ann: Mapping[str, object]) -> Task | None:
    """The task a pair was annotated for, or None for legacy (pre-ADR-0001) pairs.

    Unknown task names return None rather than inventing a category, so a typo
    is treated as legacy data instead of silently selecting the wrong field.
    """
    raw = ann.get("task")
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().lower()
    if not candidate:
        return None
    try:
        return Task(candidate)
    except ValueError:
        return None
