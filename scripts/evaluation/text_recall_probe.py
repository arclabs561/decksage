#!/usr/bin/env python3
"""Known-item recall of functional reprints: full-catalog E5 vs the graph.

Both retrievers run over the same queries, so the comparison is paired. The
E5 cache must cover the catalog (scripts/training/extend_text_cache.py).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors


ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data/cache/text_emb_cache_cards_magic_intfloat-e5-base-v2"
EMBEDDING = ROOT / "data/embeddings/magic_v7_spectral_mu35.wv"
CARDS = ROOT / "data/raw/scryfall/oracle-cards.json"
TEST_SET = ROOT / "data/test_sets/annotated_magic_v2.json"


def norm(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", text or "")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def groups() -> dict[str, str]:
    members: dict[str, str] = {}
    by_key: dict[tuple[str, str], str] = {}
    for card in json.loads(CARDS.read_text(encoding="utf-8")):
        name = card.get("name")
        text = norm(card.get("oracle_text") or "")
        if not name or not text or len(text) < 10:
            continue
        key = (text, norm(card.get("type_line") or ""))
        by_key.setdefault(key, f"g{len(by_key)}")
        members[name] = by_key[key]
    return members


def main() -> int:
    names = json.loads(Path(f"{CACHE}.names.json").read_text(encoding="utf-8"))
    matrix = np.load(f"{CACHE}.npz")["matrix"].astype(np.float32)
    norms = np.load(f"{CACHE}.npz")["norms"].astype(np.float32)
    position = {name: i for i, name in enumerate(names)}
    wv = KeyedVectors.load(str(EMBEDDING))
    members = groups()
    by_group: dict[str, set[str]] = {}
    for name, group in members.items():
        by_group.setdefault(group, set()).add(name)
    queries = json.loads(TEST_SET.read_text(encoding="utf-8"))["queries"]

    rows = []
    for query in queries:
        if query not in wv or query not in position:
            continue
        reprints = by_group.get(members.get(query), set()) - {query}
        if not reprints:
            continue
        graph = [name for name, _ in wv.most_similar(query, topn=50) if name != query]
        vector = matrix[position[query]] / max(float(norms[position[query]]), 1e-9)
        scores = matrix @ vector / np.maximum(norms, 1e-9)
        order = np.argsort(scores)[::-1]
        text = [names[i] for i in order if names[i] != query][:50]
        rows.append(
            {
                "query": query,
                "reprints": sorted(reprints),
                "graph_at_10": any(name in reprints for name in graph[:10]),
                "graph_at_50": any(name in reprints for name in graph[:50]),
                "text_at_10": any(name in reprints for name in text[:10]),
                "text_at_50": any(name in reprints for name in text[:50]),
            }
        )

    def mean(key: str) -> float:
        return round(float(np.mean([row[key] for row in rows])), 4) if rows else 0.0

    result = {
        "queries": len(rows),
        "graph_recall_at_10": mean("graph_at_10"),
        "graph_recall_at_50": mean("graph_at_50"),
        "text_recall_at_10": mean("text_at_10"),
        "text_recall_at_50": mean("text_at_50"),
        "text_cache_names": len(names),
    }
    output = ROOT / "data/results/text_reprint_recall.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
