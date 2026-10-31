"""Tests for the generic train/eval split-disjointness guard."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.evaluation.split_guard import (
    SplitLeakError,
    check_disjoint,
    refuse_if_leaky,
    split_digest,
)


def _key(record: dict) -> str:
    return record["query"]


def _group(record: dict) -> str:
    return record["card"]


def test_exact_key_overlap_is_reported() -> None:
    train = [{"query": "q1", "card": "bolt"}]
    eval_set = [{"query": "q1", "card": "counterspell"}]
    report = check_disjoint(train, eval_set, key=_key, group=_group)
    assert report.exact_overlap == ("q1",)
    assert report.group_overlap == ()
    assert not report.clean
    assert "shared key" in report.summary()


def test_group_overlap_is_reported_without_exact_overlap() -> None:
    train = [{"query": "q1", "card": "bolt"}]
    eval_set = [{"query": "q9", "card": "bolt"}]
    report = check_disjoint(train, eval_set, key=_key, group=_group)
    assert report.exact_overlap == ()
    assert report.group_overlap == ("bolt",)
    assert not report.clean


def test_clean_split() -> None:
    train = [{"query": "q1", "card": "bolt"}]
    eval_set = [{"query": "q2", "card": "counterspell"}]
    report = check_disjoint(train, eval_set, key=_key, group=_group)
    assert report.clean
    assert "clean:" in report.summary()


def test_generators_are_materialized_once() -> None:
    train = iter([{"query": "q1", "card": "bolt"}])
    eval_set = iter([{"query": "q2", "card": "bolt"}])
    report = check_disjoint(train, eval_set, key=_key, group=_group)
    assert report.train == 1
    assert report.eval == 1
    assert report.group_overlap == ("bolt",)


def test_none_group_is_ignored() -> None:
    train = [{"query": "q1", "card": None}]
    eval_set = [{"query": "q2", "card": None}]
    report = check_disjoint(train, eval_set, key=_key, group=_group)
    assert report.group_overlap == ()
    assert report.clean


def test_refuse_raises_on_a_leak_and_returns_a_clean_report() -> None:
    with pytest.raises(SplitLeakError):
        refuse_if_leaky(
            [{"query": "q1", "card": "bolt"}],
            [{"query": "q1", "card": "bolt"}],
            key=_key,
            group=_group,
        )
    report = refuse_if_leaky(
        [{"query": "q1", "card": "bolt"}],
        [{"query": "q2", "card": "counterspell"}],
        key=_key,
        group=_group,
    )
    assert report.clean


def test_digest_is_order_independent_but_label_sensitive() -> None:
    a = [{"query": "q1", "card": "bolt", "label": 1}]
    b = [{"query": "q2", "card": "counter", "label": 0}]
    digest_a = split_digest([*a, *b], key=_key, group=_group, label=lambda record: record["label"])
    digest_b = split_digest([*b, *a], key=_key, group=_group, label=lambda record: record["label"])
    assert digest_a == digest_b
    changed = split_digest(
        [{"query": "q1", "card": "bolt", "label": 0}, *b],
        key=_key,
        group=_group,
        label=lambda record: record["label"],
    )
    assert changed != digest_a
