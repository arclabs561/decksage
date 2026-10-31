#!/usr/bin/env python3
"""Materialize a multi-relation card graph (cooccurrence, text, tag, attribute).

The serving graph was co-occurrence only. This writes SQLite edges with a
relation column so an agent can ask for all evidence about a card, and so the
union retriever has a persisted edge store instead of recomputing lists.

Usage:
    scripts/graph/build_unified_graph.py --game magic --out data/graphs/unified_magic.db
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data/cache/text_emb_cache_cards_magic_intfloat-e5-base-v2"
PAIRS = ROOT / "data/graphs/pairs_large.edg"
TAGS = ROOT / "data/processed/magic_tags.json"
CARDS = ROOT / "data/processed/card_attributes_magic_enriched.csv"


def tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", default="magic", choices=("magic",))
    parser.add_argument("--out", type=Path, default=ROOT / "data/graphs/unified_magic.db")
    parser.add_argument("--max-cards", type=int, default=0, help="Smoke test limit")
    parser.add_argument("--top-k", type=int, default=20)
    args = parser.parse_args()

    all_names = json.loads(Path(f"{CACHE}.names.json").read_text())
    matrix = np.load(f"{CACHE}.npz")["matrix"].astype(np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    matrix = matrix / np.maximum(norms[:, None], 1e-9)
    index = {name: i for i, name in enumerate(all_names)}
    names = all_names[: args.max_cards] if args.max_cards else all_names

    edges: dict[tuple[str, str, str], float] = {}

    def add(src: str, dst: str, relation: str, weight: float) -> None:
        if src == dst or dst not in index:
            return
        key = (src, dst, relation)
        if weight > edges.get(key, 0.0):
            edges[key] = float(weight)

    # co-occurrence
    raw: dict[str, list[tuple[str, float]]] = defaultdict(list)
    with PAIRS.open() as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            a, b, weight = parts[0], parts[1], float(parts[2])
            if a in index and b in index:
                raw[a].append((b, weight))
                raw[b].append((a, weight))
    for card, neighbours in raw.items():
        ceiling = max(weight for _, weight in neighbours) or 1.0
        for other, weight in sorted(neighbours, key=lambda p: -p[1])[: args.top_k]:
            add(card, other, "cooccurrence", weight / ceiling)

    # text kNN
    for start in range(0, len(names), 256):
        chunk = names[start : start + 256]
        rows = [index[name] for name in chunk]
        scores = matrix[rows] @ matrix.T
        for row, name in enumerate(chunk):
            order = np.argsort(scores[row])[::-1]
            kept = 0
            for i in order:
                other = all_names[int(i)]
                if other == name:
                    continue
                add(name, other, "text", float(scores[row, int(i)]))
                kept += 1
                if kept >= args.top_k:
                    break
        print(f"text {min(start + 256, len(names))}/{len(names)}", flush=True)

    # tag neighbours
    tag_map = json.loads(TAGS.read_text())
    tag_sets = {name: set(tags) for name, tags in tag_map.items() if name in index}
    inverted: dict[str, set[str]] = defaultdict(set)
    for name, tags in tag_sets.items():
        for label in tags:
            inverted[label].add(name)
    for name, tags in tag_sets.items():
        candidates: set[str] = set()
        for label in tags:
            candidates |= inverted[label]
        scored = []
        for other in candidates:
            if other == name:
                continue
            union = tags | tag_sets[other]
            scored.append((len(tags & tag_sets[other]) / len(union), other))
        for score, other in sorted(scored, reverse=True)[: args.top_k]:
            add(name, other, "tag", score)
    print(f"tag neighbours for {len(tag_sets)} cards", flush=True)

    # attribute neighbours: shared creature types
    with CARDS.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    type_map: dict[str, set[str]] = {}
    type_index: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        name = row.get("name", "")
        if name not in index:
            continue
        kinds = set(tokens(row.get("creature_types", "")))
        if kinds:
            type_map[name] = kinds
            for kind in kinds:
                type_index[kind].add(name)
    for name, kinds in type_map.items():
        candidates: set[str] = set()
        for kind in kinds:
            candidates |= type_index[kind]
        scored = []
        for other in candidates:
            if other == name:
                continue
            other_kinds = type_map.get(other, set())
            union = kinds | other_kinds
            if union:
                scored.append((len(kinds & other_kinds) / len(union), other))
        for score, other in sorted(scored, reverse=True)[: args.top_k]:
            add(name, other, "attribute", score)
    print(f"attribute neighbours for {len(type_map)} creatures", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()
    connection = sqlite3.connect(args.out)
    connection.execute(
        "CREATE TABLE edges (src TEXT, dst TEXT, relation TEXT, weight REAL, "
        "PRIMARY KEY (src, dst, relation))"
    )
    connection.executemany(
        "INSERT OR REPLACE INTO edges VALUES (?, ?, ?, ?)",
        [(src, dst, relation, weight) for (src, dst, relation), weight in edges.items()],
    )
    connection.execute("CREATE INDEX idx_edges_src ON edges(src, relation, weight DESC)")
    connection.commit()
    counts = connection.execute("SELECT relation, COUNT(*) FROM edges GROUP BY relation").fetchall()
    connection.close()
    print(f"wrote {args.out}: {len(edges)} edges {dict(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
