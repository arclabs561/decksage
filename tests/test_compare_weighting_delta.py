"""A delta across arms scored on different query sets must be refused.

Both arms draw from the same candidate pool, but each one ranks it with its own
weights and scores whatever subset of queries that ranking judges. Subtracting
the two means hides that difference inside "the weighting got better".
`compare_outcomes` publishes the raw delta only when both arms scored exactly the
same queries, and always prints each arm's coverage and the intersection size.
"""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def comparison():
    path = Path(__file__).resolve().parent.parent / "scripts/evaluation/compare_weighting.py"
    spec = importlib.util.spec_from_file_location("compare_weighting", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _arm(values: dict[str, float], coverage: float) -> dict:
    return {
        "ndcg_at_10": sum(values.values()) / len(values),
        "queries_eligible": 100,
        "queries_scored": len(values),
        "coverage": coverage,
        "per_query": values,
    }


def test_delta_is_withheld_when_arms_scored_different_query_sets(comparison):
    calibrated = _arm({"a": 0.9, "b": 0.8, "c": 0.7}, coverage=0.6)
    uniform = _arm({"b": 0.4, "c": 0.3, "d": 0.2}, coverage=0.5)

    result = comparison.compare_outcomes(calibrated, uniform, k=10)

    assert result["same_subset"] is False
    assert result["delta"] is None
    assert "different query sets" in result["delta_withheld"]
    # The paired intersection is still reported, on the shared queries only.
    assert result["paired_intersection"]["queries"] == 2
    assert result["paired_intersection"]["calibrated_mean"] == pytest.approx(0.75)
    assert result["paired_intersection"]["uniform_mean"] == pytest.approx(0.35)

    report = comparison.format_report(result)
    assert "delta withheld" in report
    assert "coverage 0.6" in report and "coverage 0.5" in report
    assert "2 shared queries" in report


def test_delta_is_published_when_both_arms_scored_the_same_queries(comparison):
    calibrated = _arm({"a": 0.9, "b": 0.8}, coverage=0.6)
    uniform = _arm({"a": 0.4, "b": 0.3}, coverage=0.6)

    result = comparison.compare_outcomes(calibrated, uniform, k=10)

    assert result["same_subset"] is True
    assert result["delta_withheld"] is None
    assert result["delta"] == pytest.approx(0.5)
    assert result["paired_intersection"]["queries"] == 2
    assert "delta withheld" not in comparison.format_report(result)


def test_strict_scalars_are_a_like_for_like_comparison(comparison):
    # The strict scorer returns a number only when every eligible query had a
    # judged result, so two scalars already describe the same query set.
    result = comparison.compare_outcomes(0.6, 0.4, k=10)

    assert result["same_subset"] is True
    assert result["delta_withheld"] is None
    assert result["delta"] == pytest.approx(0.2)
    assert "coverage 1.0, strict" in comparison.format_report(result)


def test_no_shared_query_means_nothing_is_published(comparison):
    result = comparison.compare_outcomes(
        _arm({"a": 0.9}, coverage=0.5),
        _arm({"b": 0.2}, coverage=0.5),
        k=10,
    )

    assert result["delta"] is None
    assert result["paired_intersection"] is None
    assert "none" in comparison.format_report(result)
