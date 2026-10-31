#!/usr/bin/env python3
"""0087: does one shared trunk serve three facets from raw E5 vectors?

0086 compared trunks on seven scalar features. This compares them on the pair
representation itself: [q_e5, c_e5] at 1536 dims, with a scalar-feature arm
reproduced on the same rows so the comparison is apples to apples.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))
sys.path.insert(0, str(ROOT / "src"))

from heuristic_scorers import build_tag

from ml.utils.paths import PATHS


CACHE = PATHS.data / "cache" / "text_emb_cache_cards_magic_intfloat-e5-base-v2"
CARDS = PATHS.data / "raw" / "scryfall" / "oracle-cards.json"
TEST_SET = PATHS.data / "test_sets" / "annotated_magic_v2.json"
TAGS = ROOT / "data-local" / "label-anchor-20261030" / "oracle-tags.jsonl.gz"
TARGETS = ("functional_score", "synergy_score", "meta_relevance")
OUT = PATHS.data / "results" / "encoder_trunk_0087.json"


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def tokens(text: str) -> set[str]:
    return set(norm(text).split())


def main() -> int:
    names = json.loads(Path(f"{CACHE}.names.json").read_text())
    matrix = np.load(f"{CACHE}.npz")["matrix"].astype(np.float32)
    position = {name: index for index, name in enumerate(names)}
    cards = {card["name"]: card for card in json.loads(CARDS.read_text()) if card.get("name")}
    tag = build_tag("magic", TAGS, CARDS)
    test = json.loads(TEST_SET.read_text())["queries"]

    def scalar_features(query: str, candidate: str) -> list[float]:
        qi, ci = position.get(query), position.get(candidate)
        e5 = float(matrix[qi] @ matrix[ci]) if qi is not None and ci is not None else 0.0
        tag_score = float(tag.cosines(query, [candidate])[0])
        q, c = cards.get(query, {}), cards.get(candidate, {})
        same_type = float(norm(q.get("type_line")) == norm(c.get("type_line")))
        qc, cc = set(q.get("colors") or []), set(c.get("colors") or [])
        color = len(qc & cc) / len(qc | cc) if (qc | cc) else 1.0
        mana = min(
            abs(float(q.get("mana_value") or 0) - float(c.get("mana_value") or 0)) / 10.0, 1.0
        )
        qt, ct = tokens(q.get("oracle_text") or ""), tokens(c.get("oracle_text") or "")
        text = len(qt & ct) / len(qt | ct) if (qt | ct) else 0.0
        return [e5, tag_score, same_type, color, mana, text]

    pair_vectors = []
    scalar_rows = []
    target_rows = []
    groups = []
    for query, entry in test.items():
        qi = position.get(query)
        for annotation in entry.get("annotations", []):
            candidate = annotation.get("candidate")
            ci = position.get(candidate)
            values = [annotation.get(target) for target in TARGETS]
            if qi is None or ci is None or not candidate:
                continue
            if any(not isinstance(value, (int, float)) for value in values):
                continue
            pair_vectors.append(np.concatenate([matrix[qi], matrix[ci]]))
            scalar_rows.append(scalar_features(query, candidate))
            target_rows.append(values)
            groups.append(query)

    X_vector = np.asarray(pair_vectors, dtype=np.float64)
    X_scalar = np.asarray(scalar_rows, dtype=np.float64)
    Y = np.asarray(target_rows, dtype=np.float64)
    groups = np.asarray(groups)
    print(f"rows {len(Y)} queries {len(set(groups))}", flush=True)

    folds = list(GroupKFold(n_splits=5).split(X_vector, Y, groups))

    def fit_arm(X: np.ndarray, hidden: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
        shared = np.zeros_like(Y)
        for train, valid in folds:
            model = make_pipeline(
                StandardScaler(),
                MLPRegressor(
                    hidden_layer_sizes=hidden, max_iter=300, early_stopping=True, random_state=13
                ),
            )
            model.fit(X[train], Y[train])
            shared[valid] = model.predict(X[valid])
        separate = np.zeros_like(Y)
        for index in range(Y.shape[1]):
            for train, valid in folds:
                model = make_pipeline(
                    StandardScaler(),
                    MLPRegressor(
                        hidden_layer_sizes=hidden,
                        max_iter=300,
                        early_stopping=True,
                        random_state=13,
                    ),
                )
                model.fit(X[train], Y[train, index])
                separate[valid, index] = model.predict(X[valid])
        return shared, separate

    scalar_shared, scalar_separate = fit_arm(X_scalar, (64, 32))
    vector_shared, vector_separate = fit_arm(X_vector, (128, 64))

    def metrics(prediction: np.ndarray) -> dict[str, dict[str, float]]:
        return {
            target: {
                "mae": round(float(np.mean(np.abs(prediction[:, index] - Y[:, index]))), 4),
                "spearman": round(float(spearmanr(prediction[:, index], Y[:, index]).statistic), 4),
            }
            for index, target in enumerate(TARGETS)
        }

    arms = {
        "scalar_shared": metrics(scalar_shared),
        "scalar_separate": metrics(scalar_separate),
        "vector_shared": metrics(vector_shared),
        "vector_separate": metrics(vector_separate),
    }
    mean_mae = {
        name: round(float(np.mean([values["mae"] for values in arm.values()])), 4)
        for name, arm in arms.items()
    }
    candidate_delta = round(mean_mae["vector_shared"] - mean_mae["vector_separate"], 4)
    per_target_delta = {
        target: round(
            arms["vector_shared"][target]["mae"] - arms["vector_separate"][target]["mae"], 4
        )
        for target in TARGETS
    }
    worst_target = max(per_target_delta, key=lambda name: per_target_delta[name])

    verdict = (
        "shared_matches_separate"
        if candidate_delta <= 0.01 and per_target_delta[worst_target] <= 0.02
        else "negative_transfer"
    )
    beats_scalar = mean_mae["vector_shared"] < mean_mae["scalar_shared"]
    payload = {
        "rows": len(Y),
        "queries": len(set(groups)),
        "arms": arms,
        "mean_mae": mean_mae,
        "delta_shared_minus_separate": candidate_delta,
        "per_target_delta": per_target_delta,
        "vector_beats_scalar_shared": bool(beats_scalar),
        "verdict": verdict,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
