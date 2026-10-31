#!/usr/bin/env python3
"""Train a functional-pair ranker from text, tags and co-occurrence.

The benchmark says the co-occurrence embedding orders substitutes poorly and
tag Jaccard orders them better. This trains a small supervised model on the
11.9k refined pair labels and asks whether it beats the tag prior on the same
judged pools.

Features per pair, all available at query time:
  e5_cosine      document-embedding cosine from the cached E5 matrix
  emb_cosine     production co-occurrence embedding cosine
  tag_jaccard    Scryfall Oracle Tag IDF-weighted Jaccard
  same_type      normalized type_line equality
  color_jaccard  color-identity overlap
  mana_delta     absolute mana-value difference (normalized)
  text_jaccard   oracle-text token Jaccard

Training uses GroupKFold by query; pairs whose query appears in the Magic test
set are dropped so the evaluation queries are unseen. The model is a
HistGradientBoostingRegressor on the median judge score.

Usage:
    scripts/training/train_functional_ranker.py
"""

from __future__ import annotations

import os


# HistGradientBoosting predict and BLAS both spawn threads per call; on a
# per-query loop that overhead dominated the run (63 min at 588% CPU).
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))

from heuristic_scorers import build_tag


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def tokens(text: str) -> set[str]:
    return set(norm(text).split())


class Features:
    def __init__(self, cards_path: Path, cache_prefix: Path, embedding_path: Path, tags_path: Path):
        cards = json.loads(cards_path.read_text(encoding="utf-8"))
        self.cards = {card["name"]: card for card in cards if card.get("name")}
        self.names = json.loads(Path(f"{cache_prefix}.names.json").read_text(encoding="utf-8"))
        matrix = np.load(f"{cache_prefix}.npz")["matrix"].astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1)
        self.text = matrix / np.maximum(norms[:, None], 1e-9)
        self.text_pos = {name: i for i, name in enumerate(self.names)}
        self.wv = KeyedVectors.load(str(embedding_path))
        self.tags = build_tag("magic", tags_path, cards_path)

    def pair(self, query: str, candidate: str) -> dict[str, float]:
        q, c = self.cards.get(query, {}), self.cards.get(candidate, {})
        qi, ci = self.text_pos.get(query), self.text_pos.get(candidate)
        e5 = float(self.text[qi] @ self.text[ci]) if qi is not None and ci is not None else 0.0
        emb = (
            float(self.wv.similarity(query, candidate))
            if query in self.wv and candidate in self.wv
            else 0.0
        )
        tag = float(self.tags.cosines(query, [candidate])[0])
        same_type = float(norm(q.get("type_line")) == norm(c.get("type_line")))
        qc = set(q.get("colors") or [])
        cc = set(c.get("colors") or [])
        color = len(qc & cc) / len(qc | cc) if (qc | cc) else 1.0
        qm = q.get("mana_value") or q.get("cmc") or 0
        cm = c.get("mana_value") or c.get("cmc") or 0
        mana = min(abs(float(qm) - float(cm)) / 10.0, 1.0)
        qt, ct = tokens(q.get("oracle_text") or ""), tokens(c.get("oracle_text") or "")
        text = len(qt & ct) / len(qt | ct) if (qt | ct) else 0.0
        return {
            "e5_cosine": e5,
            "emb_cosine": emb,
            "tag_jaccard": tag,
            "same_type": same_type,
            "color_jaccard": color,
            "mana_delta": mana,
            "text_jaccard": text,
        }


FIELDS = [
    "e5_cosine",
    "emb_cosine",
    "tag_jaccard",
    "same_type",
    "color_jaccard",
    "mana_delta",
    "text_jaccard",
]


def ndcg(ranked: list[str], rel: dict[str, float], k: int = 10) -> float:
    dcg = sum(rel.get(name, 0.0) / np.log2(i + 2) for i, name in enumerate(ranked[:k]))
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = sum(value / np.log2(i + 2) for i, value in enumerate(ideal))
    return float(dcg / idcg) if idcg else 0.0


def bootstrap(deltas: list[float], seed: int = 13, resamples: int = 1000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    values = np.asarray(deltas)
    means = [
        float(rng.choice(values, size=len(values), replace=True).mean()) for _ in range(resamples)
    ]
    means.sort()
    return means[25], means[974]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", default="magic")
    parser.add_argument(
        "--pairs", type=Path, default=ROOT / "data/annotations/refined/magic_pairs.json"
    )
    parser.add_argument(
        "--test-set", type=Path, default=ROOT / "data/test_sets/annotated_magic_v2.json"
    )
    parser.add_argument("--cards", type=Path, default=ROOT / "data/raw/scryfall/oracle-cards.json")
    parser.add_argument(
        "--cache-prefix",
        type=Path,
        default=ROOT / "data/cache/text_emb_cache_cards_magic_intfloat-e5-base-v2",
    )
    parser.add_argument(
        "--embedding", type=Path, default=ROOT / "data/embeddings/magic_v7_spectral_mu35.wv"
    )
    parser.add_argument(
        "--tags", type=Path, default=ROOT / "data-local/label-anchor-20261030/oracle-tags.jsonl.gz"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "data/results/functional_ranker.json")
    parser.add_argument(
        "--model", type=Path, default=ROOT / "data-local/functional_ranker_magic.pkl"
    )
    args = parser.parse_args()

    feats = Features(args.cards, args.cache_prefix, args.embedding, args.tags)
    test = json.loads(args.test_set.read_text(encoding="utf-8"))
    queries = test["queries"]
    test_queries = set(queries)

    pairs = json.loads(args.pairs.read_text(encoding="utf-8"))["pairs"]
    train_pairs = [
        p for p in pairs if p["query"] not in test_queries and p["candidate"] in feats.cards
    ]
    print(f"training pairs {len(train_pairs)} of {len(pairs)} (test queries excluded)")

    X = np.asarray(
        [[feats.pair(p["query"], p["candidate"])[f] for f in FIELDS] for p in train_pairs]
    )
    y = np.asarray([p["median_score"] for p in train_pairs])
    groups = np.asarray([p["query"] for p in train_pairs])
    model = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.05, max_depth=6, random_state=13
    )
    oof = np.zeros(len(y))
    for train_idx, valid_idx in GroupKFold(n_splits=5).split(X, y, groups):
        fold = HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.05, max_depth=6, random_state=13
        )
        fold.fit(X[train_idx], y[train_idx])
        oof[valid_idx] = fold.predict(X[valid_idx])
    from scipy.stats import spearmanr

    oof_rho = float(spearmanr(oof, y).statistic)
    oof_mae = float(np.mean(np.abs(oof - y)))
    model.fit(X, y)
    print(f"OOF spearman {oof_rho:.3f}, MAE {oof_mae:.3f}", flush=True)

    # Evaluate on the test set's judged candidates that are in the embedding pool.
    rows = []
    for query_index, (query, entry) in enumerate(queries.items()):
        if query_index % 500 == 0:
            print(f"eval {query_index}/{len(queries)}", flush=True)
        rel = {
            ann["candidate"]: float(ann["functional_score"])
            for ann in entry.get("annotations", [])
            if ann.get("candidate") and isinstance(ann.get("functional_score"), (int, float))
        }
        if len(rel) < 2 or query not in feats.wv:
            continue
        pool = [name for name, _ in feats.wv.most_similar(query, topn=50) if name in rel]
        if len(pool) < 2:
            continue
        candidates = [name for name in pool if name in feats.cards]
        if len(candidates) < 2:
            continue
        matrix = np.asarray([[feats.pair(query, c)[f] for f in FIELDS] for c in candidates])
        scores = {
            "model": model.predict(matrix),
            "tag": matrix[:, FIELDS.index("tag_jaccard")],
            "emb": matrix[:, FIELDS.index("emb_cosine")],
            "e5": matrix[:, FIELDS.index("e5_cosine")],
        }
        row = {"query": query}
        for name, values in scores.items():
            ranked = [c for _, c in sorted(zip(values, candidates), reverse=True)]
            row[name] = ndcg(ranked, rel)
        rows.append(row)

    summary = {
        name: round(statistics.mean(row[name] for row in rows), 4)
        for name in ("model", "tag", "emb", "e5")
    }
    deltas = [row["model"] - row["tag"] for row in rows]
    low, high = bootstrap(deltas)
    result = {
        "game": args.game,
        "train_pairs": len(train_pairs),
        "oof_spearman": round(oof_rho, 4),
        "oof_mae": round(oof_mae, 4),
        "eval_queries": len(rows),
        "mean_ndcg_at_10": summary,
        "model_minus_tag": round(statistics.mean(deltas), 4),
        "delta_ci_95": [round(low, 4), round(high, 4)],
        "seed": 13,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    import joblib

    args.model.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "fields": FIELDS}, args.model)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
