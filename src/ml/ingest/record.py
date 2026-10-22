"""Candidate label records shared by every ingestion path.

One :class:`LabelCandidate` is one (query, candidate) judgment produced by an
external source. It carries the provenance ``docs/LABEL-SOURCES.md`` requires --
source URL, fetch time, extractor, prompt version, confidence -- plus the hash
of the fetched payload, so a later licensing or contamination audit can trace a
row back to a snapshot without keeping the corpus in git.

The writer owns three fields. ``synthetic`` marks an augmented row (ADR-0002);
``allow_trial_training`` records that a ``trial`` source was admitted to the
training path as an explicit exception; ``duplicate_count`` counts rows dropped
by the writer's dedup rule. They default to the values a fresh, unaugmented row
has, so an extractor never has to set them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import MISSING, asdict, dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any


SHA256_HEX = re.compile(r"[0-9a-f]{64}")
NO_PROMPT = "none"
"""Marker for a deterministic extractor. Blank is refused so "no prompt" and
"forgot to record the prompt" cannot be confused in an audit."""

_CANDIDATE_FIELDS = {
    "source_id",
    "label_type",
    "query",
    "candidate",
    "score",
    "source_url",
    "fetched_at",
    "content_sha256",
    "extractor",
    "prompt_version",
    "confidence",
    "synthetic",
    "allow_trial_training",
    "duplicate_count",
}

_IDENTIFIER_FIELDS = ("source_id", "label_type", "query", "candidate")


class InvalidCandidateError(ValueError):
    """Raised when a label candidate is malformed or fails validation."""


@dataclass(frozen=True, slots=True)
class LabelCandidate:
    """A single external label judgment with its provenance.

    ``score`` is the graded label the source implies (0.0-1.0); ``confidence``
    is how sure the extractor is of that reading. They are separate because a
    source can state a relation firmly while measuring it coarsely.
    """

    source_id: str
    label_type: str
    query: str
    candidate: str
    score: float
    source_url: str
    fetched_at: str
    content_sha256: str
    extractor: str
    prompt_version: str
    confidence: float
    synthetic: bool = False
    allow_trial_training: bool = False
    duplicate_count: int = 0

    def __post_init__(self) -> None:
        for name in _IDENTIFIER_FIELDS:
            _require_text(name, getattr(self, name))
        # Provenance: the source URL may be empty (a local or offline extractor
        # has none); the extractor and prompt version may not, because a row
        # whose producer is unknown cannot be audited.
        if not isinstance(self.source_url, str):
            raise InvalidCandidateError(f"source_url must be a string, got {self.source_url!r}")
        _require_text("extractor", self.extractor)
        _require_text("prompt_version", self.prompt_version)

        object.__setattr__(self, "score", _require_unit_interval("score", self.score))
        object.__setattr__(
            self, "confidence", _require_unit_interval("confidence", self.confidence)
        )
        _validate_timestamp("fetched_at", self.fetched_at)
        _validate_sha256("content_sha256", self.content_sha256)

        _require_bool("synthetic", self.synthetic)
        _require_bool("allow_trial_training", self.allow_trial_training)
        if isinstance(self.duplicate_count, bool) or not isinstance(self.duplicate_count, int):
            raise InvalidCandidateError(
                f"duplicate_count must be an integer, got {self.duplicate_count!r}"
            )
        if self.duplicate_count < 0:
            raise InvalidCandidateError("duplicate_count must be >= 0")

    @property
    def dedup_key(self) -> tuple[str, str, str, str]:
        """Identity of a judgment: the same quartet is the same label."""
        return (self.source_id, self.label_type, self.query, self.candidate)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible mapping of every field, in declaration order."""
        return asdict(self)

    def to_json(self) -> str:
        """Return one JSONL line (no trailing newline)."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, row: Mapping[str, Any]) -> LabelCandidate:
        """Rebuild a candidate from a mapping, validating it.

        Unknown keys are refused: a misspelled provenance field would otherwise
        be dropped silently. Keys with defaults may be absent.
        """
        if not isinstance(row, Mapping):
            raise InvalidCandidateError(f"label candidate must be a mapping, got {type(row)!r}")
        unknown = sorted(set(row) - _CANDIDATE_FIELDS)
        if unknown:
            raise InvalidCandidateError(f"unknown label candidate field(s): {', '.join(unknown)}")
        required = [
            item.name
            for item in fields(cls)
            if item.default is MISSING and item.default_factory is MISSING
        ]
        missing = sorted(name for name in required if name not in row)
        if missing:
            raise InvalidCandidateError(f"missing label candidate field(s): {', '.join(missing)}")
        try:
            return cls(**row)
        except TypeError as exc:
            raise InvalidCandidateError(f"invalid label candidate: {exc}") from exc

    @classmethod
    def from_json(cls, line: str) -> LabelCandidate:
        """Parse one JSONL line."""
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InvalidCandidateError(f"label candidate is not valid JSON: {exc}") from exc
        return cls.from_dict(payload)


def read_jsonl(path: Path) -> list[LabelCandidate]:
    """Read every non-blank line of a JSONL file.

    A malformed line is reported with its file and line number so the offending
    row can be found without guessing.
    """
    candidates: list[LabelCandidate] = []
    with open(path, encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                candidates.append(LabelCandidate.from_json(line))
            except InvalidCandidateError as exc:
                raise InvalidCandidateError(f"{path}:{lineno}: {exc}") from exc
    return candidates


def write_jsonl(path: Path, candidates: Iterable[LabelCandidate]) -> int:
    """Replace ``path`` with one JSON line per candidate; return the row count."""
    rows = list(candidates)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for candidate in rows:
            handle.write(candidate.to_json())
            handle.write("\n")
    return len(rows)


def _require_text(name: str, value: Any) -> None:
    if not isinstance(value, str):
        raise InvalidCandidateError(f"{name} must be a string, got {value!r}")
    if not value.strip():
        raise InvalidCandidateError(f"{name} must not be empty")


def _require_bool(name: str, value: Any) -> None:
    if not isinstance(value, bool):
        raise InvalidCandidateError(f"{name} must be a boolean, got {value!r}")


def _require_unit_interval(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidCandidateError(f"{name} must be a number, got {value!r}")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise InvalidCandidateError(f"{name} must be within [0, 1], got {value!r}")
    return number


def _validate_timestamp(name: str, value: str) -> None:
    """Require an ISO 8601 timestamp with an offset.

    A bare date or a naive datetime is refused: ``fetched_at`` exists to order
    snapshots and to date the terms that applied, and neither is meaningful
    without a time zone.
    """
    if not isinstance(value, str):
        raise InvalidCandidateError(f"{name} must be a string, got {value!r}")
    if "T" not in value:
        raise InvalidCandidateError(
            f"{name} must be an ISO 8601 timestamp with a UTC offset, got {value!r}"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidCandidateError(f"{name} must be an ISO 8601 timestamp, got {value!r}") from exc
    if parsed.tzinfo is None:
        raise InvalidCandidateError(f"{name} must include a UTC offset, got {value!r}")


def _validate_sha256(name: str, value: str) -> None:
    if not isinstance(value, str):
        raise InvalidCandidateError(f"{name} must be a string, got {value!r}")
    if not SHA256_HEX.fullmatch(value):
        raise InvalidCandidateError(f"{name} must be 64 lowercase hex characters, got {value!r}")
