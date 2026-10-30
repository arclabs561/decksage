"""Search metrics use binary judgments and preserve request failures."""

import importlib.util
from pathlib import Path

import httpx
import pytest


@pytest.fixture(scope="module")
def evaluator():
    path = Path(__file__).resolve().parents[1] / "scripts/evaluation/eval_search_relevance.py"
    spec = importlib.util.spec_from_file_location("search_evaluation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_binary_ndcg_ignores_label_order_and_duplicate_hits(evaluator):
    score = evaluator.ndcg_at_k(["A", "A"], ["A", "B"], 2)
    assert 0 < score < 1
    assert score == evaluator.ndcg_at_k(["A", "A"], ["B", "A"], 2)
    assert evaluator.precision_at_k(["A"], {"A"}, 2) == 0.5


def test_http_failure_does_not_become_zero_relevance(evaluator, monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("unavailable")

    monkeypatch.setattr(evaluator.httpx, "get", fail)
    with pytest.raises(httpx.ConnectError):
        evaluator.eval_game("magic", "http://localhost")
