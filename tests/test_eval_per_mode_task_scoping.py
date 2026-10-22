"""ADR-0001: an evaluation run reads only the labels for the task it evaluates.

Covers `scripts/evaluation/eval_per_mode.py`: task-scoped label selection, the
legacy (no `task` field) pair counter, and absent metrics reported as null with
a reason instead of 0.0.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluation" / "eval_per_mode.py"


@pytest.fixture(scope="module")
def evaluator():
    """Load the evaluator script as a module (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("eval_per_mode", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeKeyedVectors:
    """Minimal KeyedVectors stand-in; neighbors come from an explicit cache."""

    def __init__(self, keys):
        self.index_to_key = list(keys)
        self.key_to_index = {key: i for i, key in enumerate(self.index_to_key)}
        self._normed = np.eye(len(self.index_to_key))

    def __len__(self):
        return len(self.index_to_key)

    def get_normed_vectors(self):
        return self._normed


def test_synergy_task_pair_is_not_consumed_by_substitute_eval(evaluator):
    # Pairs annotated for the synergy task only: they carry synergy_score and no
    # functional_score, so a substitute run must not read them at all.
    queries = {
        "Query Card": {
            "annotations": [
                {"candidate": "Partner A", "task": "synergy", "synergy_score": 0.9},
                {"candidate": "Partner B", "task": "synergy", "synergy_score": 0.4},
            ]
        }
    }
    neighbor_cache = {"Query Card": [("Partner A", 0.9), ("Partner B", 0.4)]}

    substitute = evaluator.eval_mode(
        None, queries, "substitute", k=2, neighbor_cache=neighbor_cache
    )
    assert substitute["status"] == "absent"
    assert substitute["ndcg_at_k"] is None
    assert substitute["n_evaluated"] == 0
    assert substitute["legacy_label_pairs"] == 0
    assert substitute["n_excluded_other_task"] == 2

    synergy = evaluator.eval_mode(None, queries, "synergy", k=2, neighbor_cache=neighbor_cache)
    assert synergy["status"] == "measured"
    assert synergy["score_field"] == "synergy_score"
    assert synergy["n_evaluated"] == 1
    assert synergy["ndcg_at_k"] == pytest.approx(1.0)


def test_legacy_pair_is_read_through_its_field_and_counted(evaluator):
    # No `task` field: a pre-ADR-0001 annotation. It stays usable through the
    # historical task->field mapping and is counted as a legacy label.
    queries = {
        "Query Card": {
            "annotations": [
                {
                    "candidate": "Old A",
                    "functional_score": 0.8,
                    "synergy_score": 0.1,
                }
            ]
        }
    }
    neighbor_cache = {"Query Card": [("Old A", 0.9)]}

    substitute = evaluator.eval_mode(
        None, queries, "substitute", k=1, neighbor_cache=neighbor_cache
    )
    assert substitute["status"] == "measured"
    assert substitute["score_field"] == "functional_score"
    assert substitute["n_evaluated"] == 1
    assert substitute["legacy_label_pairs"] == 1

    synergy = evaluator.eval_mode(None, queries, "synergy", k=1, neighbor_cache=neighbor_cache)
    assert synergy["status"] == "measured"
    assert synergy["score_field"] == "synergy_score"
    assert synergy["legacy_label_pairs"] == 1


def test_unlabeled_metric_reports_absent_not_zero(evaluator):
    # similarity_score is not a task label: no task may fall back to it.
    queries = {
        "Query Card": {"annotations": [{"candidate": "Unlabeled A", "similarity_score": 0.7}]}
    }
    neighbor_cache = {"Query Card": [("Unlabeled A", 0.9)]}

    for mode, field in (
        ("substitute", "functional_score"),
        ("synergy", "synergy_score"),
        ("meta", "meta_relevance"),
    ):
        metric = evaluator.eval_mode(None, queries, mode, k=1, neighbor_cache=neighbor_cache)
        assert metric["status"] == "absent"
        assert metric["ndcg_at_k"] is None
        assert metric["n_evaluated"] == 0
        assert field in metric["reason"]
        assert mode in metric["reason"]


def test_metric_without_any_pairs_reports_absent(evaluator):
    queries = {"Query Card": {"annotations": []}}
    metric = evaluator.eval_mode(None, queries, "meta", k=1, neighbor_cache={})
    assert metric["status"] == "absent"
    assert metric["ndcg_at_k"] is None
    assert metric["reason"]


def test_eval_game_records_task_and_legacy_counter(evaluator, monkeypatch):
    queries = {
        "Query Card": {
            "annotations": [
                {"candidate": "Synergy Partner", "task": "synergy", "synergy_score": 0.9},
                {"candidate": "Legacy Substitute", "functional_score": 0.6},
            ]
        }
    }
    wv = FakeKeyedVectors(["Query Card", "Synergy Partner", "Legacy Substitute"])
    neighbor_cache = {"Query Card": [("Legacy Substitute", 0.5), ("Synergy Partner", 0.4)]}

    monkeypatch.setattr(
        evaluator,
        "load_test_set",
        lambda game: {"version": "unit", "queries": queries},
    )
    monkeypatch.setattr(evaluator, "load_embeddings", lambda game, name=None: wv)
    monkeypatch.setattr(
        evaluator,
        "_precompute_neighbors",
        lambda kvs, names, max_k=30: neighbor_cache,
    )

    substitute_only = evaluator.eval_game("magic", "unit_emb", k=2, quick=True, task="substitute")

    assert substitute_only["task"] == "substitute"
    assert "mode_synergy" not in substitute_only
    assert substitute_only["legacy_labels"] is True
    assert substitute_only["legacy_label_pairs"] == 1
    sub = substitute_only["mode_substitute"]
    assert sub["status"] == "measured"
    assert sub["n_evaluated"] == 1
    # The synergy-only pair was skipped, not read through functional_score.
    assert sub["n_excluded_other_task"] == 1

    all_tasks = evaluator.eval_game("magic", "unit_emb", k=2, quick=True)
    assert all_tasks["task"] == "all"
    assert all_tasks["mode_substitute"]["status"] == "measured"
    assert all_tasks["mode_synergy"]["status"] == "measured"
    # meta has no labels here: absent, and null rather than 0.0.
    assert all_tasks["mode_meta"]["status"] == "absent"
    assert all_tasks["mode_meta"]["ndcg_at_k"] is None
    assert all_tasks["legacy_label_pairs"] == 1
