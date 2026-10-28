"""Contract tests: the models must reject the bug classes they exist for."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ml.contracts.annotations import (
    Annotation,
    JudgeScores,
    QueryEntry,
    Task,
    TestSet,
    curate_evaluation_data,
)
from ml.utils.paths import PATHS


def _entry(**overrides):
    base = {
        "annotations": [{"candidate": "Bolt", "similarity_score": 0.9}],
        "highly_relevant": ["Bolt"],
    }
    base.update(overrides)
    return base


def test_bucket_and_score_agree_passes():
    entry = QueryEntry.model_validate(_entry())
    assert entry.highly_relevant == ("Bolt",)


def test_bucket_contradicting_score_is_rejected():
    with pytest.raises(ValidationError, match="highly_relevant"):
        QueryEntry.model_validate(
            {
                "annotations": [{"candidate": "Bolt", "similarity_score": 0.02}],
                "highly_relevant": ["Bolt"],
            }
        )


def test_candidate_in_two_buckets_is_not_silently_accepted():
    # A candidate may appear in one band only; a wrong band is rejected above.
    with pytest.raises(ValidationError):
        QueryEntry.model_validate(
            {
                "annotations": [{"candidate": "Bolt", "similarity_score": 0.55}],
                "relevant": ["Bolt"],
                "marginally_relevant": ["Bolt"],
            }
        )


def test_irrelevant_bucket_must_match_score():
    with pytest.raises(ValidationError, match="irrelevant"):
        QueryEntry.model_validate(
            {
                "annotations": [{"candidate": "Bolt", "similarity_score": 0.8}],
                "irrelevant": ["Bolt"],
            }
        )


def test_duplicate_annotations_are_rejected():
    with pytest.raises(ValidationError, match="duplicate"):
        QueryEntry.model_validate(
            {
                "annotations": [
                    {"candidate": "Bolt", "similarity_score": 0.9},
                    {"candidate": "Bolt", "similarity_score": 0.8},
                ],
                "highly_relevant": ["Bolt"],
            }
        )


def test_score_out_of_range_is_rejected():
    with pytest.raises(ValidationError):
        Annotation.model_validate({"candidate": "Bolt", "similarity_score": 1.4})


def test_judge_response_cannot_fill_missing_or_invalid_scores_with_zero():
    with pytest.raises(ValidationError):
        JudgeScores.model_validate({"similarity_score": 0.8})
    with pytest.raises(ValidationError):
        JudgeScores.model_validate(
            {"similarity_score": 2, "functional_score": 0, "synergy_score": 0, "meta_relevance": 0}
        )


@pytest.mark.parametrize(
    "marker",
    [
        {"synthetic": True},
        {"error": True},
        {"_provenance": {"augmentation": "swap"}},
        {"llm_model": "cosine_fallback"},
    ],
)
def test_evaluation_contract_rejects_ineligible_judgments(marker):
    with pytest.raises(ValidationError):
        QueryEntry.model_validate({"annotations": [{"candidate": "Bolt", **marker}]})


def test_missing_score_stays_none_not_zero():
    ann = Annotation.model_validate({"candidate": "Bolt"})
    assert ann.score_for(Task.SUBSTITUTE) is None


def test_unbucketed_candidate_is_allowed():
    QueryEntry.model_validate({"annotations": [{"candidate": "Bolt", "similarity_score": 0.42}]})


def test_declared_query_count_must_match():
    with pytest.raises(ValidationError, match="num_queries"):
        TestSet.model_validate(
            {
                "game": "magic",
                "num_queries": 5,
                "queries": {"Bolt": _entry()},
            }
        )


def test_real_test_set_loads():
    path = PATHS.data / "test_sets" / "annotated_magic_v2.json"
    if not path.exists():
        pytest.skip("local test set not present")
    data, _removed = curate_evaluation_data(json.loads(path.read_text()))
    test_set = TestSet.model_validate(data)
    assert len(test_set.queries) > 1000
