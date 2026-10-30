"""Copy-first repair retains annotations and only removes redundant memberships."""

import copy
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def repair():
    path = Path(__file__).resolve().parents[1] / "scripts/annotation/repair_bucket_duplicates.py"
    spec = importlib.util.spec_from_file_location("repair_bucket_duplicates", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.repair


def test_only_stale_duplicate_membership_is_removed(repair):
    entry = {
        "annotations": [
            {"candidate": "a", "similarity_score": 0.8, "provenance": "judge"},
            {"candidate": "b", "similarity_score": 0.8},
        ],
        "highly_relevant": ["a"],
        "irrelevant": ["a", "b", "bucket only"],
    }
    data = {"queries": {"query": entry}}
    before = copy.deepcopy(data)
    result, count = repair(data)
    assert count == 1
    assert data == before
    assert result["queries"]["query"]["irrelevant"] == ["b", "bucket only"]
    assert result["queries"]["query"]["annotations"] == entry["annotations"]


def test_duplicate_scores_are_not_silently_selected(repair):
    with pytest.raises(ValueError, match="duplicate annotation"):
        repair({"queries": {"q": {"annotations": [{"candidate": "a"}, {"candidate": "a"}]}}})
