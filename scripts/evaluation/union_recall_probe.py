#!/usr/bin/env python3
"""Compare text, graph, tag and union candidate pools on refined positives."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))

from heuristic_scorers import build_tag


PAIRS = ROOT / "data/annotations/refined/magic_pairs.json"
CACHE = ROOT / "data/cache/text_emb_cache_cards_magic_intfloat-e5-base-v2"
EMBEDDING = ROOT / "data/embeddings/magic_v7_spectral_mu35.wv"
TAGS = ROOT / "data-local/label-anchor-20261030/oracle-tags.jsonl.gz"
CARDS = ROOT / "data/raw/scryfall/oracle-cards.json"


def main() -> int:
    pairs = json.loads(PAIRS.read_text())["pairs"]
    positives: dict[str, set[str]] = {}
    for pair in pairs:
        if pair["median_score"] >= 0.5:
            positives.setdefault(pair["query"], set()).add(pair["candidate"])

    names = json.loads(Path(f"{CACHE}.names.json").read_text())
    matrix = np.load(f"{CACHE}.npz")["matrix"].astype(np.float32)
    norms = np.load(f"{CACHE}.npz")["norms"].astype(np.float32)
    position = {n: i for i, n in enumerate(names)}
    wv = KeyedVectors.load(str(EMBEDDING))
    tag = build_tag("magic", TAGS, CARDS)
    tag_pos = tag.positions
    tag_sets = tag.tag_sets
    idf = tag.idf
    inverted: dict[str, set[str]] = {}
    for card, pos in tag_pos.items():
        for label in tag_sets[pos]:
            inverted.setdefault(label, set()).add(card)

    def tag_scores(query: str, limit: int = 50) -> list[str]:
        qpos = tag_pos.get(query)
        if qpos is None or not tag_sets[qpos]:
            return []
        qt = tag_sets[qpos]
        candidates: set[str] = set()
        for label in qt:
            candidates |= inverted.get(label, set())
        scored = []
        for card in candidates:
            cpos = tag_pos[card]
            ct = tag_sets[cpos]
            union = qt | ct
            denom = sum(idf.get(t, 1.0) for t in union)
            common = sum(idf.get(t, 1.0) for t in (qt & ct))
            if denom:
                scored.append((common / denom, card))
        scored.sort(reverse=True)
        return [card for _, card in scored[:limit]]

    def text_rank(query: str, limit: int = 50) -> list[str]:
        idx = position[query]
        v = matrix[idx] / max(float(norms[idx]), 1e-9)
        scores = matrix @ v / np.maximum(norms, 1e-9)
        out = [names[i] for i in np.argsort(scores)[::-1] if names[i] != query]
        return out[:limit]

    def graph_rank(query: str, limit: int = 50) -> list[str]:
        return [n for n, _ in wv.most_similar(query, topn=limit) if n != query]

    rows = []
    for query, expected in positives.items():
        if query not in wv or query not in position:
            continue
        text = text_rank(query)
        graph = graph_rank(query)
        tags = tag_scores(query)
        rrf: dict[str, float] = {}
        for ranked in (text, graph, tags):
            for rank, card in enumerate(ranked, 1):
                rrf[card] = rrf.get(card, 0.0) + 1.0 / (60 + rank)
        fused = sorted(rrf, key=lambda card: (-rrf[card], card))[:50]
        rows.append(
            {
                "query": query,
                "positives": len(expected),
                "text_10": len(expected & set(text[:10])) / len(expected),
                "text_50": len(expected & set(text[:50])) / len(expected),
                "graph_10": len(expected & set(graph[:10])) / len(expected),
                "graph_50": len(expected & set(graph[:50])) / len(expected),
                "tag_10": len(expected & set(tags[:10])) / len(expected),
                "tag_50": len(expected & set(tags[:50])) / len(expected),
                "rrf_10": len(expected & set(fused[:10])) / len(expected),
                "rrf_50": len(expected & set(fused[:50])) / len(expected),
            }
        )

    def mean(key: str) -> float:
        return round(float(np.mean([row[key] for row in rows])), 4) if rows else 0.0

    result = {
        "queries": len(rows),
        "positives": sum(row["positives"] for row in rows),
        "text_at_10": mean("text_10"),
        "text_at_50": mean("text_50"),
        "graph_at_10": mean("graph_10"),
        "graph_at_50": mean("graph_50"),
        "tag_at_10": mean("tag_10"),
        "tag_at_50": mean("tag_50"),
        "rrf_at_10": mean("rrf_10"),
        "rrf_at_50": mean("rrf_50"),
    }
    output = ROOT / "data/results/union_recall.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
