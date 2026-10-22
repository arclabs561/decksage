"""ADR-0001: an evaluation run reads only the labels for the task it evaluates.

Covers `scripts/evaluation/eval_per_mode.py`: task-scoped label selection, the
legacy (no `task` field) pair counter, and absent metrics reported as null with
a reason instead of 0.0. Also covers the composite similarity_score metrics
(absent when a task is requested, marked legacy for the default `all` run) and
the pipeline formatter that prints null scores as `absent`.
"""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluation" / "eval_per_mode.py"
PIPELINE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pipeline" / "run_pipeline.py"


@pytest.fixture(scope="module")
def evaluator():
    """Load the evaluator script as a module (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("eval_per_mode", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pipeline():
    """Load the pipeline script as a module (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("run_pipeline", PIPELINE_SCRIPT)
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


def fake_universe(keys: list[str], size: int = 60) -> FakeKeyedVectors:
    """A fake vocabulary large enough for the Hit@50 pass in eval_game."""
    vocab = list(keys)
    vocab += [f"Filler {i}" for i in range(size - len(vocab))]
    return FakeKeyedVectors(vocab)


def patch_eval_game(monkeypatch, evaluator, queries, wv, neighbor_cache):
    """Point eval_game at in-memory data and a fixed neighbor cache."""
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


def test_composite_metrics_absent_when_task_requested(evaluator, monkeypatch):
    # similarity_score is a composite across every pair, not a task label, so a
    # task-scoped run reports the composite metrics as absent while keeping the
    # JSON keys present (no KeyError for consumers).
    queries = {
        "Query Card": {
            "annotations": [
                {"candidate": "Card A", "functional_score": 0.6, "similarity_score": 0.7},
                {"candidate": "Card B", "task": "synergy", "synergy_score": 0.9},
            ]
        }
    }
    wv = fake_universe(["Query Card", "Card A", "Card B"])
    neighbor_cache = {"Query Card": [("Card A", 0.5), ("Card B", 0.4)]}
    patch_eval_game(monkeypatch, evaluator, queries, wv, neighbor_cache)

    scoped = evaluator.eval_game("unit", "unit_emb", k=2, quick=True, task="substitute")

    # The task's own metric is unaffected.
    assert scoped["mode_substitute"]["status"] == "measured"

    overall = scoped["overall_ndcg"]
    assert overall["status"] == "absent"
    assert overall["ndcg_at_k"] is None
    assert "substitute" in overall["reason"]
    assert overall["k"] == 2

    hit = scoped["hit_at_k"]
    assert hit["status"] == "absent"
    for k_val in ("10", "20", "50"):
        assert hit[k_val]["rate"] is None
        assert hit[k_val]["hits"] == 0

    mrr = scoped["mrr_relevant"]
    assert mrr["status"] == "absent"
    assert mrr["mrr"] is None
    assert mrr["mean_rank"] is None


def test_composite_metrics_are_marked_legacy_in_all_run(evaluator, monkeypatch):
    # The default `all` run keeps the composite values for continuity, but marks
    # them as legacy composites that are not scoped to any task.
    queries = {
        "Query Card": {
            "annotations": [
                {"candidate": "Card A", "task": "substitute", "functional_score": 0.9},
                {"candidate": "Card B", "similarity_score": 0.2},
                {"candidate": "Card C", "similarity_score": 0.7},
            ]
        }
    }
    wv = fake_universe(["Query Card", "Card A", "Card B", "Card C"])
    neighbor_cache = {"Query Card": [("Card A", 0.9), ("Card C", 0.7), ("Card B", 0.2)]}
    patch_eval_game(monkeypatch, evaluator, queries, wv, neighbor_cache)

    result = evaluator.eval_game("unit", "unit_emb", k=2, quick=True)

    for key in ("overall_ndcg", "hit_at_k", "mrr_relevant"):
        metric = result[key]
        assert metric["legacy_composite"] is True
        assert metric["task_scoped"] is False
        assert "not task-scoped" in metric["note"]
        assert metric.get("status") is None

    # Values are unchanged by the marking.
    assert result["overall_ndcg"]["ndcg_at_k"] is not None
    assert result["hit_at_k"]["10"]["rate"] is not None
    assert result["mrr_relevant"]["mrr"] is not None


def test_stratified_ndcg_follows_composite_task_scope(evaluator, monkeypatch):
    # stratified_ndcg is also built from similarity_score, so it is absent for a
    # task-scoped run and legacy-marked for `all`. Non-quick mode is needed: the
    # stratified block only runs when secondary metrics are computed.
    wv = fake_universe(["Card 0", "Card 1", "Card 2"])
    queries = {
        "Card 0": {
            "annotations": [
                {
                    "candidate": "Card 1",
                    "functional_score": 0.8,
                    "similarity_score": 0.6,
                },
                {"candidate": "Card 2", "functional_score": 0.3, "similarity_score": 0.1},
            ]
        }
    }
    neighbor_cache = {"Card 0": [("Card 1", 0.9), ("Card 2", 0.3)]}
    patch_eval_game(monkeypatch, evaluator, queries, wv, neighbor_cache)

    scoped = evaluator.eval_game("unit", "unit_emb", k=2, task="substitute")
    strat = scoped["stratified_ndcg"]
    assert strat["status"] == "absent"
    assert strat["popular_ndcg"] is None
    assert strat["niche_ndcg"] is None
    assert strat["bias_ratio"] is None
    assert "substitute" in strat["reason"]

    unscoped = evaluator.eval_game("unit", "unit_emb", k=2)
    strat = unscoped["stratified_ndcg"]
    assert strat["legacy_composite"] is True
    assert strat["task_scoped"] is False
    assert strat["popular_ndcg"] is not None
    assert strat["niche_ndcg"] is not None


def test_pipeline_formats_null_scores_as_absent(pipeline):
    # eval_per_mode reports an absent metric as null (ADR-0001); the pipeline
    # prints `absent` instead of raising on the None.
    assert pipeline.format_score(None) == "absent"
    assert pipeline.format_score(0.51234) == "0.5123"
    assert pipeline.format_score(0.0) == "0.0000"
    assert pipeline.format_optional(None) == "absent"
    assert pipeline.format_optional("?") == "?"
    assert pipeline.format_optional(0.8) == "0.8"
