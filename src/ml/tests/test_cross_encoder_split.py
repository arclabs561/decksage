"""Validation pairs for the cross-encoder must not leak into training.

scripts/training/train_cross_encoder.py adds reversed (B, A) pairs; if that
happens before the query-level split, a validation pair's reverse lands in
training and validation measures memorization.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "training" / "train_cross_encoder.py"
_spec = importlib.util.spec_from_file_location("train_cross_encoder", _SCRIPT)
train_cross_encoder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(train_cross_encoder)


def _pairs(n_cards: int = 60) -> list[dict]:
    pairs = []
    for i in range(n_cards):
        for j in (i + 1, i + 2):
            a, b = f"card{i}", f"card{j % n_cards}"
            pairs.append(
                {
                    "query": a,
                    "candidate": b,
                    "query_text": f"text {a}",
                    "candidate_text": f"text {b}",
                    "score": 0.5 + 0.01 * (i % 40),
                }
            )
    return pairs


def test_no_validation_pair_or_its_reverse_is_trained_on():
    train, val = train_cross_encoder._prepare_splits(_pairs())
    assert val, "split produced no validation pairs"

    trained = {(p["query"], p["candidate"]) for p in train}
    leaked = [
        (p["query"], p["candidate"])
        for p in val
        if (p["query"], p["candidate"]) in trained or (p["candidate"], p["query"]) in trained
    ]
    assert leaked == []
