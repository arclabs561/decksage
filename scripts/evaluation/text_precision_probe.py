#!/usr/bin/env python3
"""Precision of the text candidate pool from a fresh-judgment batch (0083).

Reads the review/key/judged triple produced by
``scripts/annotation/annotate_pairs_openrouter.py`` and compares the text
top-10 with the graph top-10 on existing labels. Also reports lexical overlap,
because the Lightning Bolt example suggests E5 can rank name-similar cards.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from gensim.models import KeyedVectors


ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "data-local/text-pool-20261031"
EMBEDDING = ROOT / "data/embeddings/magic_v7_spectral_mu35.wv"
TEST_SET = ROOT / "data/test_sets/annotated_magic_v2.json"


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def main() -> int:
    review = json.loads((BATCH / "review.json").read_text())["items"]
    judged = {
        f"{row['query']}\u0000{row['candidate']}": row
        for row in json.loads((BATCH / "judged.json").read_text())["pairs"]
    }
    rows = []
    for item in review:
        fresh = judged.get(f"{item['query']}\u0000{item['candidate']}")
        if not fresh or fresh.get("median_functional") is None:
            continue
        rows.append(
            {
                "query": item["query"],
                "candidate": item["candidate"],
                "score": float(fresh["median_functional"]),
                "n_judges": int(fresh.get("n_judges", 0)),
            }
        )
    by_query: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_query[row["query"]].append(row)

    precision_05 = statistics.mean(
        sum(1 for row in group if row["score"] >= 0.5) / len(group) for group in by_query.values()
    )
    precision_07 = statistics.mean(
        sum(1 for row in group if row["score"] >= 0.7) / len(group) for group in by_query.values()
    )
    overlap = [bool(tokens(row["query"]) & tokens(row["candidate"])) for row in rows]
    with_overlap = [row["score"] for row, hit in zip(rows, overlap) if hit]
    without_overlap = [row["score"] for row, hit in zip(rows, overlap) if not hit]

    wv = KeyedVectors.load(str(EMBEDDING))
    test = json.loads(TEST_SET.read_text())["queries"]
    graph_precision = []
    graph_coverage = []
    for query in by_query:
        if query not in wv:
            continue
        relevance = {
            ann["candidate"]: float(ann["functional_score"])
            for ann in test.get(query, {}).get("annotations", [])
            if isinstance(ann.get("functional_score"), (int, float))
        }
        top = [name for name, _ in wv.most_similar(query, topn=10) if name != query]
        judged_values = [relevance[name] for name in top if name in relevance]
        graph_coverage.append(len(judged_values) / 10)
        if judged_values:
            graph_precision.append(
                sum(1 for value in judged_values if value >= 0.5) / len(judged_values)
            )

    result = {
        "queries": len(by_query),
        "pairs": len(rows),
        "pairs_with_3_judges": sum(1 for row in rows if row["n_judges"] == 3),
        "text_precision_at_10_0p5": round(precision_05, 4),
        "text_precision_at_10_0p7": round(precision_07, 4),
        "graph_precision_judged_subset": round(statistics.mean(graph_precision), 4)
        if graph_precision
        else None,
        "graph_judged_coverage": round(statistics.mean(graph_coverage), 4)
        if graph_coverage
        else None,
        "lexical_overlap_share": round(sum(overlap) / len(overlap), 4),
        "score_with_lexical_overlap": round(statistics.mean(with_overlap), 4)
        if with_overlap
        else None,
        "score_without_lexical_overlap": round(statistics.mean(without_overlap), 4)
        if without_overlap
        else None,
    }
    output = ROOT / "data/results/text_precision.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
