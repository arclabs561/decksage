"""Fetcher seam and content hashing for ingestion.

A :class:`Fetcher` returns the raw bytes a source served. This tranche ships
only :class:`StaticFetcher` so tests and fixtures can exercise the write path
without an HTTP client; a real fetcher has to honour the registry's access
method, robots rules and rate limit before it is added.

Snapshots are hashed, not stored. The row keeps ``content_sha256`` so a label
can be re-derived from a later fetch, while the corpus itself stays out of git
and out of redistributed artifacts.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Protocol, runtime_checkable


class FetchError(RuntimeError):
    """Raised when a fetcher cannot produce the body for a URL."""


def content_sha256(payload: bytes) -> str:
    """Return the lowercase hex sha256 of fetched bytes."""
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError(f"payload must be bytes, got {type(payload)!r}")
    return hashlib.sha256(bytes(payload)).hexdigest()


@runtime_checkable
class Fetcher(Protocol):
    """Anything that can turn a URL into the exact bytes served for it."""

    def fetch(self, url: str) -> bytes:
        """Return the body for ``url`` or raise :class:`FetchError`."""
        ...


class StaticFetcher:
    """In-memory fetcher for tests and recorded fixtures.

    ``requests`` keeps every URL in call order, so a test can assert that the
    writer's caller fetched once and only where the registry allows.
    """

    def __init__(self, responses: Mapping[str, bytes]) -> None:
        self._responses = {url: bytes(body) for url, body in responses.items()}
        self.requests: list[str] = []

    def fetch(self, url: str) -> bytes:
        self.requests.append(url)
        try:
            return self._responses[url]
        except KeyError as exc:
            raise FetchError(f"no static body for {url!r}") from exc
