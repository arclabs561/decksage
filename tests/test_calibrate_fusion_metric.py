"""The calibration objective must retain the full judged ideal ranking."""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def calibrator():
    path = Path(__file__).resolve().parent.parent / "scripts/training/calibrate_fusion_weights.py"
    spec = importlib.util.spec_from_file_location("calibrate_fusion", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_missing_relevant_candidates_reduce_ndcg(calibrator):
    assert calibrator.compute_ndcg([0.5], [1.0, 0.5], 10) == pytest.approx(
        0.5 / (1 + 0.5 / 1.584962500721156)
    )


def test_weight_evaluation_ignores_unjudged_and_keeps_full_ideal(calibrator, monkeypatch):
    from ml.similarity import fusion

    class FakeFusion:
        def __init__(self, **kwargs):
            pass

        def similar(self, query, k):
            return [("unjudged", 1), ("weaker", 0.9)]

    monkeypatch.setattr(fusion, "WeightedLateFusion", FakeFusion)
    test_data = {
        "queries": {
            "query": {
                "annotations": [
                    {"candidate": "stronger", "functional_score": 1.0},
                    {"candidate": "weaker", "functional_score": 0.5},
                ]
            }
        }
    }
    score = calibrator.evaluate_weights(
        "magic", 1, 0, 0, 0, 0, test_data, {}, {"query"}, None, None, None, None
    )
    assert score == pytest.approx(0.5 / (1 + 0.5 / 1.584962500721156))


def test_ground_truth_excludes_other_tasks_and_missing_functional_scores(calibrator):
    labels = {
        "annotations": [
            {"candidate": "valid", "functional_score": 0.8, "task": "substitute"},
            {"candidate": "other", "functional_score": 1.0, "task": "synergy"},
            {"candidate": "composite", "similarity_score": 0.9},
        ],
        "highly_relevant": ["bucket_only"],
    }
    assert calibrator._ground_truth(labels) == {"valid": 0.8}


def test_unjudged_only_result_cannot_be_compared(calibrator, monkeypatch):
    from ml.similarity import fusion

    class FakeFusion:
        def __init__(self, **kwargs):
            pass

        def similar(self, query, k):
            return [("unjudged", 1.0)]

    monkeypatch.setattr(fusion, "WeightedLateFusion", FakeFusion)
    test_data = {
        "queries": {"query": {"annotations": [{"candidate": "A", "functional_score": 1.0}]}}
    }
    score = calibrator.evaluate_weights(
        "magic", 1, 0, 0, 0, 0, test_data, {}, {"query"}, None, None, None, None
    )
    assert score is None


def test_calibration_refuses_to_overwrite_existing_weights(calibrator, tmp_path, monkeypatch):
    monkeypatch.setattr(calibrator, "DATA_DIR", tmp_path)
    (tmp_path / "embeddings").mkdir()
    path = tmp_path / "embeddings/fusion_weights_magic.json"
    path.write_text("original")
    with pytest.raises(FileExistsError):
        calibrator.calibrate("magic")
    assert path.read_text() == "original"


def test_main_reports_failed_calibration(calibrator, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["calibrate_fusion_weights.py", "--game", "magic"])
    monkeypatch.setattr(calibrator, "calibrate", lambda game, quick=False: None)
    assert calibrator.main() == 1
