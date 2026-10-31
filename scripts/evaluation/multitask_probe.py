#!/usr/bin/env python3
"""Shared-trunk multi-task vs per-facet models on the same features."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))

from heuristic_scorers import build_tag


CACHE = ROOT / "data/cache/text_emb_cache_cards_magic_intfloat-e5-base-v2"
EMBEDDING = ROOT / "data/embeddings/magic_v7_spectral_mu35.wv"
CARDS = ROOT / "data/raw/scryfall/oracle-cards.json"
TEST_SET = ROOT / "data/test_sets/annotated_magic_v2.json"
TAGS = ROOT / "data-local/label-anchor-20261030/oracle-tags.jsonl.gz"
TARGETS = ("functional_score", "synergy_score", "meta_relevance")


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def tokens(text: str) -> set[str]:
    return set(norm(text).split())


def main() -> int:
    names = json.loads(Path(f"{CACHE}.names.json").read_text())
    matrix = np.load(f"{CACHE}.npz")["matrix"].astype(np.float32)
    norms = np.load(f"{CACHE}.npz")["norms"].astype(np.float32)
    position = {name: index for index, name in enumerate(names)}
    wv = KeyedVectors.load(str(EMBEDDING))
    cards = {c["name"]: c for c in json.loads(CARDS.read_text()) if c.get("name")}
    tag = build_tag("magic", TAGS, CARDS)
    test = json.loads(TEST_SET.read_text())["queries"]

    def features(query: str, candidate: str) -> list[float]:
        qi, ci = position.get(query), position.get(candidate)
        e5 = (
            float(matrix[qi] @ matrix[ci] / (norms[qi] * norms[ci] + 1e-9))
            if qi is not None and ci is not None
            else 0.0
        )
        graph = float(wv.similarity(query, candidate)) if query in wv and candidate in wv else 0.0
        tag_score = float(tag.cosines(query, [candidate])[0])
        q, c = cards.get(query, {}), cards.get(candidate, {})
        same_type = float(norm(q.get("type_line")) == norm(c.get("type_line")))
        qc = set(q.get("colors") or [])
        cc = set(c.get("colors") or [])
        color = len(qc & cc) / len(qc | cc) if (qc | cc) else 1.0
        qm = q.get("mana_value") or q.get("cmc") or 0
        cm = c.get("mana_value") or c.get("cmc") or 0
        mana = min(abs(float(qm) - float(cm)) / 10.0, 1.0)
        qt, ct = tokens(q.get("oracle_text") or ""), tokens(c.get("oracle_text") or "")
        text = len(qt & ct) / len(qt | ct) if (qt | ct) else 0.0
        return [e5, graph, tag_score, same_type, color, mana, text]

    X, Y, groups = [], [], []
    for query, entry in test.items():
        for ann in entry.get("annotations", []):
            candidate = ann.get("candidate")
            values = [ann.get(target) for target in TARGETS]
            if not candidate or any(not isinstance(value, (int, float)) for value in values):
                continue
            X.append(features(query, candidate))
            Y.append(values)
            groups.append(query)
    X = np.asarray(X, dtype=np.float64)
    Y = np.asarray(Y, dtype=np.float64)
    groups = np.asarray(groups)
    print(f"rows {len(X)} queries {len(set(groups))}")

    folds = list(GroupKFold(n_splits=5).split(X, Y, groups))
    shared_oof = np.zeros_like(Y)
    for train, valid in folds:
        model = make_pipeline(
            StandardScaler(),
            MLPRegressor(
                hidden_layer_sizes=(64, 32), max_iter=300, early_stopping=True, random_state=13
            ),
        )
        model.fit(X[train], Y[train])
        shared_oof[valid] = model.predict(X[valid])

    separate_oof = np.zeros_like(Y)
    for index, _target in enumerate(TARGETS):
        for train, valid in folds:
            model = make_pipeline(
                StandardScaler(),
                MLPRegressor(
                    hidden_layer_sizes=(64, 32), max_iter=300, early_stopping=True, random_state=13
                ),
            )
            model.fit(X[train], Y[train, index])
            separate_oof[valid, index] = model.predict(X[valid])

    def metrics(pred: np.ndarray) -> dict[str, dict[str, float]]:
        out = {}
        for index, target in enumerate(TARGETS):
            out[target] = {
                "mae": round(float(np.mean(np.abs(pred[:, index] - Y[:, index]))), 4),
                "spearman": round(float(spearmanr(pred[:, index], Y[:, index]).statistic), 4),
            }
        return out

    shared_metrics = metrics(shared_oof)
    separate_metrics = metrics(separate_oof)
    mean_shared = float(np.mean([m["mae"] for m in shared_metrics.values()]))
    mean_separate = float(np.mean([m["mae"] for m in separate_metrics.values()]))
    result = {
        "rows": len(X),
        "queries": len(set(groups)),
        "shared": shared_metrics,
        "separate": separate_metrics,
        "mean_mae_shared": round(mean_shared, 4),
        "mean_mae_separate": round(mean_separate, 4),
        "mean_delta_shared_minus_separate": round(mean_shared - mean_separate, 4),
    }
    output = ROOT / "data/results/multitask_probe.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
