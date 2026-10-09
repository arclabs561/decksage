"""Condensed nDCG in scripts/evaluation/eval_per_mode.py (Sakai 2007).

Dropping unjudged results must not also shrink the ideal ranking: one
judged hit out of ten relevant cards is not a perfect score.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


pytest.importorskip("gensim")

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "evaluation" / "eval_per_mode.py"
_spec = importlib.util.spec_from_file_location("eval_per_mode", _SCRIPT)
eval_per_mode = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_per_mode)


def test_single_judged_hit_is_not_a_perfect_score():
    gt = {f"relevant{i}": 1.0 for i in range(10)}
    ranked = ["relevant0"] + [f"unjudged{i}" for i in range(9)]

    score = eval_per_mode.condensed_ndcg(ranked, gt, k=10)

    # DCG of one hit at rank 1 over the ideal DCG@10 of ten hits.
    ideal = sum(1.0 / __import__("math").log2(r + 2) for r in range(10))
    assert score == pytest.approx(1.0 / ideal)


def test_fully_judged_list_matches_standard_ndcg():
    gt = {"a": 3.0, "b": 2.0, "c": 1.0, "d": 0.0}
    ranked = ["b", "a", "d", "c"]
    standard = eval_per_mode.ndcg([gt[c] for c in ranked], list(gt.values()), 4)

    assert eval_per_mode.condensed_ndcg(ranked, gt, k=4) == pytest.approx(standard)


def test_nothing_judged_is_none():
    assert eval_per_mode.condensed_ndcg(["x", "y"], {"a": 1.0}, k=10) is None
