"""Ingestion of external label sources under the registry policy.

``record`` holds the candidate row and its JSONL form, ``writer`` enforces
ADR-0003 (source registry) and ADR-0002 (augmentation is training-only) at the
write path, and ``fetch`` is the byte seam with no network client yet.
"""

from __future__ import annotations

from .fetch import Fetcher, FetchError, StaticFetcher, content_sha256
from .record import (
    NO_PROMPT,
    InvalidCandidateError,
    LabelCandidate,
    read_jsonl,
    write_jsonl,
)
from .writer import LabelPolicyError, LabelWriter


__all__ = [
    "NO_PROMPT",
    "FetchError",
    "Fetcher",
    "InvalidCandidateError",
    "LabelCandidate",
    "LabelPolicyError",
    "LabelWriter",
    "StaticFetcher",
    "content_sha256",
    "read_jsonl",
    "write_jsonl",
]
