"""Contract tests for the ranking guards.

These pin the errors that were found by hand: a sparse judged pool, a verdict
typo, a pair that is both patched and excluded, and an out-of-range patch.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ml.contracts.evaluation import (
    Coverage,
    LabelPatchEntry,
    LabelPolicy,
    SparseLabelsError,
    Verdict,
)


def test_sparse_pool_is_refused() -> None:
    coverage = Coverage(k=10, depth=50, median_judged=10, min_judged=2)
    with pytest.raises(SparseLabelsError, match="median judged pool 10"):
        coverage.check(judged_only=False, allow_sparse=False)


def test_sparse_pool_passes_when_explicit() -> None:
    coverage = Coverage(k=10, depth=50, median_judged=10, min_judged=2)
    assert coverage.check(judged_only=True, allow_sparse=False) is coverage
    assert coverage.check(judged_only=False, allow_sparse=True) is coverage


def test_dense_pool_passes() -> None:
    coverage = Coverage(k=10, depth=50, median_judged=40, min_judged=30)
    assert coverage.check(judged_only=False, allow_sparse=False) is coverage


def test_verdict_rejects_a_typo() -> None:
    with pytest.raises(ValueError):
        Verdict("candidate_best")
    assert Verdict("candidate_better") is Verdict.CANDIDATE_BETTER


def test_patch_and_exclusion_cannot_overlap() -> None:
    entry = LabelPatchEntry(query="Lightning Bolt", candidate="Shock", functional_score=0.7)
    with pytest.raises(ValidationError, match="both patched and excluded"):
        LabelPolicy(patches=(entry,), excluded=(("Lightning Bolt", "Shock"),))


def test_patch_score_is_bounded() -> None:
    with pytest.raises(ValidationError):
        LabelPatchEntry(query="a", candidate="b", functional_score=1.2)


def test_patch_and_distinct_exclusion_are_allowed() -> None:
    entry = LabelPatchEntry(query="a", candidate="b", functional_score=0.5)
    policy = LabelPolicy(patches=(entry,), excluded=(("c", "d"),))
    assert policy.patches[0].functional_score == 0.5
