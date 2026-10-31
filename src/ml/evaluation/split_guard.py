"""Refuse to train or compare across splits that share identity.

The label gate screens contradictions *within* one evaluation set. This guard
answers the other question: do the training records and the evaluation records
describe the same thing? Exact key overlap is the cheap check; entity/group
overlap is the one that catches the realistic leak, where a card (or a deck, a
workspace, a user) appears on both sides under different query keys.

The module is deliberately generic. Callers supply the key and group extractors;
nothing here knows about cards, decks, or any label policy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, TypeVar


T = TypeVar("T")
KeyFn = Callable[[T], str]
GroupFn = Callable[[T], str | None]


class SplitLeakError(RuntimeError):
    """Raised when a split check finds shared identity."""


@dataclass(frozen=True)
class SplitReport:
    """The result of comparing the identity of two splits."""

    train: int
    eval: int
    exact_overlap: tuple[str, ...]
    group_overlap: tuple[str, ...]

    @property
    def clean(self) -> bool:
        """True only when neither the keys nor the groups overlap."""
        return not self.exact_overlap and not self.group_overlap

    def summary(self) -> str:
        """One line naming the counts and the first few offending ids."""
        if self.clean:
            return f"clean: {self.train} train / {self.eval} eval records share no key or group"
        parts = [
            f"{self.train} train / {self.eval} eval records",
            f"{len(self.exact_overlap)} shared key(s)",
            f"{len(self.group_overlap)} shared group(s)",
        ]
        examples = (self.exact_overlap + self.group_overlap)[:5]
        if examples:
            parts.append("e.g. " + ", ".join(repr(value) for value in examples))
        return "; ".join(parts)


def _materialize(records: Iterable[T]) -> list[T]:
    # Callers pass generators often enough that consuming twice would silently
    # produce an empty group set. Materialize once and check it in memory.
    return list(records)


def check_disjoint(
    train: Iterable[T],
    eval: Iterable[T],
    *,
    key: KeyFn[T],
    group: GroupFn[T] | None = None,
) -> SplitReport:
    """Compare the identity of a training split and an evaluation split.

    ``key`` is the exact record identity (query id, pair id, row id). ``group``
    is the coarser unit that must not span the split (card, deck, user,
    workspace). A group extractor that returns ``None`` is ignored, which lets a
    caller mark records with no meaningful group without inventing one.

    The check is set-based: order and duplicates inside one split do not affect
    the verdict.
    """
    train_records = _materialize(train)
    eval_records = _materialize(eval)
    train_keys = {key(record) for record in train_records}
    eval_keys = {key(record) for record in eval_records}
    exact_overlap = tuple(sorted(train_keys & eval_keys))

    group_overlap: tuple[str, ...] = ()
    if group is not None:
        train_groups = {value for record in train_records if (value := group(record)) is not None}
        eval_groups = {value for record in eval_records if (value := group(record)) is not None}
        group_overlap = tuple(sorted(train_groups & eval_groups))

    return SplitReport(
        train=len(train_records),
        eval=len(eval_records),
        exact_overlap=exact_overlap,
        group_overlap=group_overlap,
    )


def refuse_if_leaky(
    train: Iterable[T],
    eval: Iterable[T],
    *,
    key: KeyFn[T],
    group: GroupFn[T] | None = None,
) -> SplitReport:
    """Return the report, or raise :class:`SplitLeakError` when it is not clean."""
    report = check_disjoint(train, eval, key=key, group=group)
    if not report.clean:
        raise SplitLeakError(report.summary())
    return report


def split_digest(
    records: Iterable[T],
    *,
    key: KeyFn[T],
    group: GroupFn[T] | None = None,
    label: Callable[[T], Any] | None = None,
) -> str:
    """A stable digest of a split's identity, independent of input order.

    Two splits with the same records in a different order have the same digest;
    a different key, group or label changes it. This is the value to put in a
    training ledger or an experiment record.
    """
    rows: list[tuple[str, str | None, str]] = []
    for record in records:
        group_value = group(record) if group is not None else None
        label_value = "" if label is None else json.dumps(label(record), sort_keys=True)
        rows.append((key(record), group_value, label_value))
    rows.sort()
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()
