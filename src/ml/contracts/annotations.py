"""Typed contracts for annotation test sets.

The v2 files are dictionaries with no schema, so every consumer re-implements
its own reading rules and the mistakes are silent: a pair can sit in the
`highly_relevant` bucket while its own annotation says 0.02, and both readers
stay happy. These models make that impossible to load.

Pydantic is used rather than dataclasses because the checks are cross-field
(bucket membership against score bands, task against score field) and because
the error message should name the query and candidate that broke it.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


# Bucket -> inclusive lower bound, exclusive upper bound, matching
# eval_per_mode and fill_eval_holes.
BUCKET_BANDS: dict[str, tuple[float, float]] = {
    "highly_relevant": (0.70, 1.01),
    "relevant": (0.50, 0.70),
    "somewhat_relevant": (0.30, 0.50),
    "marginally_relevant": (0.15, 0.30),
}


class Task(StrEnum):
    """The question a pair was annotated for (ADR-0001)."""

    SUBSTITUTE = "substitute"
    SYNERGY = "synergy"
    META = "meta"


class ScoreField(StrEnum):
    FUNCTIONAL = "functional_score"
    SYNERGY = "synergy_score"
    META = "meta_relevance"


TASK_SCORE_FIELD: dict[Task, ScoreField] = {
    Task.SUBSTITUTE: ScoreField.FUNCTIONAL,
    Task.SYNERGY: ScoreField.SYNERGY,
    Task.META: ScoreField.META,
}


class Annotation(BaseModel):
    """One judged pair.

    Scores are optional because older writers omit fields; a missing score is
    `None`, never zero. That distinction is the whole point of ADR-0001.
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    candidate: str = Field(min_length=1)
    similarity_score: float | None = Field(default=None, ge=0.0, le=1.0)
    functional_score: float | None = Field(default=None, ge=0.0, le=1.0)
    synergy_score: float | None = Field(default=None, ge=0.0, le=1.0)
    meta_relevance: float | None = Field(default=None, ge=0.0, le=1.0)
    substitutability: float | None = Field(default=None, ge=0.0, le=1.0)
    task: Task | None = None
    synthetic: bool = False
    llm_model: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    def score_for(self, task: Task) -> float | None:
        """The score that measures this task, or None when it was not judged."""
        return getattr(self, TASK_SCORE_FIELD[task].value, None)


class QueryEntry(BaseModel):
    """One query card with its judged candidates and relevance buckets."""

    model_config = ConfigDict(extra="allow", frozen=True)

    annotations: tuple[Annotation, ...] = ()
    highly_relevant: tuple[str, ...] = ()
    relevant: tuple[str, ...] = ()
    somewhat_relevant: tuple[str, ...] = ()
    marginally_relevant: tuple[str, ...] = ()
    irrelevant: tuple[str, ...] = ()

    @model_validator(mode="after")
    def buckets_agree_with_scores(self) -> QueryEntry:
        """A bucketed candidate must sit in the band its own score implies.

        Buckets feed the fusion evaluators; scores feed eval_per_mode. When the
        two disagree the same pair is highly relevant to one and irrelevant to
        the other, and their numbers stop being comparable.
        """
        by_candidate = {ann.candidate: ann for ann in self.annotations}
        for bucket, (low, high) in BUCKET_BANDS.items():
            for candidate in getattr(self, bucket):
                ann = by_candidate.get(candidate)
                if ann is None or ann.similarity_score is None:
                    continue
                score = ann.similarity_score
                if not low <= score < high:
                    raise ValueError(
                        f"candidate {candidate!r} is in {bucket} but its "
                        f"similarity_score is {score}; expected [{low}, {high})"
                    )
        return self

    @model_validator(mode="after")
    def no_duplicate_annotations(self) -> QueryEntry:
        seen: set[str] = set()
        duplicates: list[str] = []
        for ann in self.annotations:
            if ann.candidate in seen:
                duplicates.append(ann.candidate)
            seen.add(ann.candidate)
        if duplicates:
            raise ValueError(f"duplicate annotations for candidates: {sorted(set(duplicates))[:5]}")
        return self


class TestSet(BaseModel):
    """A whole annotated test set, validated on load."""

    model_config = ConfigDict(extra="allow", frozen=True)

    version: str | None = None
    game: str = Field(min_length=1)
    queries: dict[str, QueryEntry]
    num_queries: int | None = None

    @model_validator(mode="after")
    def declared_count_matches(self) -> TestSet:
        if self.num_queries is not None and self.num_queries != len(self.queries):
            raise ValueError(
                f"num_queries says {self.num_queries} but {len(self.queries)} queries are present"
            )
        return self


def load_test_set(path: Path | str) -> TestSet:
    """Load and validate a v2 annotated test set."""
    return TestSet.model_validate_json(Path(path).read_text())
