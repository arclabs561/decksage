"""The single policy-enforcing write path for external label candidates.

ADR-0003 makes ``config/label_sources.toml`` the gate: a source may only
produce the labels registered for it, and only at or below its verdict.
ADR-0002 makes augmentation training-only. Both are enforced here, once, so no
extractor decides them again:

- every write calls :func:`assert_source_allowed`, so an unknown, ``reject``ed
  or unregistered-label source is refused;
- a ``trial`` source is refused on the training path unless the writer was
  constructed with ``allow_trial_training=True``, and the exception is recorded
  on the row;
- a ``synthetic`` candidate is refused on the evaluation path;
- duplicates on ``(source_id, label_type, query, candidate)`` collapse to one
  row: the highest confidence wins, and the dropped count is recorded.

A writer owns one file and rewrites it atomically after each accepted row. Two
writers on the same path are not supported; the ingestion tranche is sized for
evaluation slices, and compaction belongs to storage, not policy.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from dataclasses import replace
from pathlib import Path

from ..data.label_sources import (
    LabelSource,
    SourcePolicyError,
    assert_source_allowed,
    load_sources,
)
from .record import LabelCandidate, read_jsonl, write_jsonl


class LabelPolicyError(SourcePolicyError):
    """Raised when a candidate is refused by a write-path policy.

    Subclasses :class:`SourcePolicyError` so a caller can catch one exception
    for every policy refusal, whatever the reason.
    """


class LabelWriter:
    """Append label candidates to a JSONL file under the ingestion policies.

    ``evaluation=True`` (the default) is the evaluation path: trial sources are
    allowed, synthetic rows are not. ``evaluation=False`` is the training path:
    synthetic rows are allowed, trial sources need ``allow_trial_training=True``.
    Existing rows are re-checked when the file is opened, so an evaluation
    writer cannot silently extend a file that already holds synthetic labels.
    """

    def __init__(
        self,
        path: str | Path,
        evaluation: bool = True,
        allow_trial_training: bool = False,
        registry_path: str | Path | None = None,
    ) -> None:
        self.path = Path(path)
        self.evaluation = bool(evaluation)
        self.allow_trial_training = bool(allow_trial_training)
        self.registry = load_sources(Path(registry_path) if registry_path else None)
        self._rows: dict[tuple[str, str, str, str], LabelCandidate] = {}
        self._load_existing()

    @property
    def rows(self) -> tuple[LabelCandidate, ...]:
        """Stored rows in write order, deduplicated."""
        return tuple(self._rows.values())

    def __len__(self) -> int:
        return len(self._rows)

    def __iter__(self) -> Iterator[LabelCandidate]:
        return iter(self._rows.values())

    def write(self, candidate: LabelCandidate) -> LabelCandidate:
        """Check, deduplicate and persist one candidate; return the stored row.

        Raises :class:`~ml.data.label_sources.SourcePolicyError` for a registry
        refusal and :class:`LabelPolicyError` for a trial-training or synthetic
        refusal. Nothing is written when a candidate is refused.
        """
        source = self.check_policy(candidate)
        incoming = replace(
            candidate,
            allow_trial_training=not self.evaluation and source.verdict == "trial",
            duplicate_count=0,
        )
        key = incoming.dedup_key
        existing = self._rows.get(key)
        stored = incoming if existing is None else _merge(existing, incoming)
        self._rows[key] = stored
        self._persist()
        return stored

    def write_many(self, candidates: Iterable[LabelCandidate]) -> list[LabelCandidate]:
        """Write each candidate in order; stop at the first refusal."""
        return [self.write(candidate) for candidate in candidates]

    def check_policy(self, candidate: LabelCandidate) -> LabelSource:
        """Apply the registry and ADR-0002 refusals without writing anything."""
        source = assert_source_allowed(candidate.source_id, candidate.label_type, self.registry)
        if self.evaluation and candidate.synthetic:
            raise LabelPolicyError(
                f"{source.id}: synthetic labels are training-only (ADR-0002), "
                f"refusing {candidate.dedup_key}"
            )
        if not self.evaluation and source.verdict == "trial" and not self.allow_trial_training:
            raise LabelPolicyError(
                f"{source.id} is a trial source: leave it on the evaluation path, "
                "or construct LabelWriter(allow_trial_training=True) and record why"
            )
        return source

    def _load_existing(self) -> None:
        if not self.path.exists():
            return
        for row in read_jsonl(self.path):
            source = assert_source_allowed(row.source_id, row.label_type, self.registry)
            if self.evaluation and row.synthetic:
                raise LabelPolicyError(
                    f"{self.path} holds a synthetic row for {row.dedup_key}; "
                    "an evaluation writer cannot extend it (ADR-0002)"
                )
            if (
                not self.evaluation
                and source.verdict == "trial"
                and not (row.allow_trial_training or self.allow_trial_training)
            ):
                raise LabelPolicyError(
                    f"{self.path} holds a trial-source row for {row.dedup_key} "
                    "without the recorded training exception"
                )
            key = row.dedup_key
            existing = self._rows.get(key)
            self._rows[key] = row if existing is None else _merge(existing, row)

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        write_jsonl(temporary, self._rows.values())
        os.replace(temporary, self.path)


def _merge(existing: LabelCandidate, incoming: LabelCandidate) -> LabelCandidate:
    """Collapse two judgments of the same key, keeping the higher confidence.

    An exact confidence tie keeps the first row, so replaying a file is a no-op
    beyond the duplicate count.
    """
    merged = replace(existing, duplicate_count=existing.duplicate_count + 1)
    if incoming.confidence > existing.confidence:
        merged = replace(incoming, duplicate_count=merged.duplicate_count)
    return merged
