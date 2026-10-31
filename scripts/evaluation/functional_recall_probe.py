#!/usr/bin/env python3
"""Known-item recall of judged functional positives: E5 vs the graph.

Positives come from the refined pair corpus (median judge score >= 0.5), which
was sampled from several sources, not only the graph neighbourhood. That makes
it a less biased test than the test-set annotations, whose candidates were
chosen from the embedding's own neighbours.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors


ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = {
    "magic": (
        "data/annotations/refined/magic_pairs.json",
        "data/cache/text_emb_cache_cards_magic_intfloat-e5-base-v2",
        "data/embeddings/magic_v7_spectral_mu35.wv",
    ),
    "pokemon": (
        "data/annotations/refined/pokemon_pairs.json",
        "data/cache/text_emb_cache_cards_pokemon_intfloat-e5-base-v2",
        "data/embeddings/pokemon_v7_fused.wv",
    ),
    "yugioh": (
        "data/annotations/refined/yugioh_pairs.json",
        "data/cache/text_emb_cache_cards_yugioh_intfloat-e5-base-v2",
        "data/embeddings/yugioh_v7_spectral_mu3.wv",
    ),
}


def bootstrap(values: list[float], seed: int = 13, resamples: int = 1000) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    sample = np.asarray(values)
    means = [
        float(rng.choice(sample, size=len(sample), replace=True).mean()) for _ in range(resamples)
    ]
    means.sort()
    return means[25], means[974]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", choices=sorted(DEFAULTS), default="magic")
    args = parser.parse_args()
    pairs_path, cache_path, embedding_path = (ROOT / part for part in DEFAULTS[args.game])
    pairs = json.loads(pairs_path.read_text(encoding="utf-8"))["pairs"]
    positives: dict[str, set[str]] = {}
    for pair in pairs:
        if pair["median_score"] >= 0.5:
            positives.setdefault(pair["query"], set()).add(pair["candidate"])

    names = json.loads(Path(f"{cache_path}.names.json").read_text(encoding="utf-8"))
    matrix = np.load(f"{cache_path}.npz")["matrix"].astype(np.float32)
    norms = np.load(f"{cache_path}.npz")["norms"].astype(np.float32)
    position = {name: index for index, name in enumerate(names)}
    wv = KeyedVectors.load(str(embedding_path))

    rows = []
    for query, expected in positives.items():
        if query not in wv or query not in position:
            continue
        graph = [name for name, _ in wv.most_similar(query, topn=50) if name != query]
        vector = matrix[position[query]] / max(float(norms[position[query]]), 1e-9)
        scores = matrix @ vector / np.maximum(norms, 1e-9)
        text = [names[i] for i in np.argsort(scores)[::-1] if names[i] != query][:50]
        rows.append(
            {
                "query": query,
                "positives": len(expected),
                "graph_at_10": len(expected & set(graph[:10])) / len(expected),
                "graph_at_50": len(expected & set(graph[:50])) / len(expected),
                "text_at_10": len(expected & set(text[:10])) / len(expected),
                "text_at_50": len(expected & set(text[:50])) / len(expected),
            }
        )

    def mean(key: str) -> float:
        return round(float(np.mean([row[key] for row in rows])), 4) if rows else 0.0

    delta = [row["text_at_50"] - row["graph_at_50"] for row in rows]
    low, high = bootstrap(delta)
    result = {
        "game": args.game,
        "queries": len(rows),
        "positives": sum(row["positives"] for row in rows),
        "graph_recall_at_10": mean("graph_at_10"),
        "graph_recall_at_50": mean("graph_at_50"),
        "text_recall_at_10": mean("text_at_10"),
        "text_recall_at_50": mean("text_at_50"),
        "recall50_delta_text_minus_graph": round(float(np.mean(delta)), 4),
        "delta_ci_95": [round(low, 4), round(high, 4)],
        "text_cache_names": len(names),
    }
    output = ROOT / f"data/results/functional_recall_{args.game}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
