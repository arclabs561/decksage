"""Loader and policy checks for the label-source registry.

The registry says which external sources may produce which labels and under
what terms. Code that ingests a source should call :func:`assert_source_allowed`
first, so a prohibited source cannot be wired in by accident.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


VERDICTS = {"adopt", "trial", "reject"}
TERMS = {"permissive", "attribution", "licence-required", "prohibited", "unknown"}
REGISTRY_PATH = Path(__file__).resolve().parents[3] / "config" / "label_sources.toml"


@dataclass(frozen=True)
class LabelSource:
    id: str
    labels: tuple[str, ...]
    access: str
    terms: str
    verdict: str
    note: str = ""


class SourcePolicyError(ValueError):
    """Raised when a source is missing, malformed, or not allowed for use."""


def load_sources(path: Path | None = None) -> dict[str, LabelSource]:
    """Load and validate the registry.

    Raises SourcePolicyError on duplicate ids, unknown verdict or terms, or an
    usable entry whose terms forbid use.
    """
    registry = path or REGISTRY_PATH
    with open(registry, "rb") as handle:
        data = tomllib.load(handle)

    sources: dict[str, LabelSource] = {}
    for entry in data.get("source", []):
        source = LabelSource(
            id=str(entry.get("id", "")).strip(),
            labels=tuple(entry.get("labels", [])),
            access=str(entry.get("access", "")).strip(),
            terms=str(entry.get("terms", "")).strip(),
            verdict=str(entry.get("verdict", "")).strip(),
            note=str(entry.get("note", "")).strip(),
        )
        if not source.id:
            raise SourcePolicyError("source entry without an id")
        if source.id in sources:
            raise SourcePolicyError(f"duplicate source id: {source.id}")
        if source.verdict not in VERDICTS:
            raise SourcePolicyError(f"{source.id}: unknown verdict {source.verdict!r}")
        if source.terms not in TERMS:
            raise SourcePolicyError(f"{source.id}: unknown terms {source.terms!r}")
        if source.verdict != "reject" and source.terms == "prohibited":
            raise SourcePolicyError(f"{source.id}: cannot use a prohibited source")
        if source.verdict != "reject" and not source.labels:
            raise SourcePolicyError(f"{source.id}: usable source lists no labels")
        sources[source.id] = source
    return sources


def assert_source_allowed(
    source_id: str, label: str, registry: dict[str, LabelSource] | None = None
) -> LabelSource:
    """Check that a source may be used for a label under the current policy.

    ``trial`` sources are allowed for evaluation samples but not for training;
    callers that train must check :attr:`LabelSource.verdict` themselves.
    """
    sources = registry if registry is not None else load_sources()
    source = sources.get(source_id)
    if source is None:
        raise SourcePolicyError(f"unknown source: {source_id}")
    if source.verdict == "reject":
        raise SourcePolicyError(f"{source_id} is rejected for this project")
    if source.terms == "prohibited":
        raise SourcePolicyError(f"{source_id} is prohibited for this project")
    if label not in source.labels:
        raise SourcePolicyError(f"{source_id} is not registered for label {label!r}")
    return source
