#!/usr/bin/env python3
"""Measure an exact-reprint boost on top of the embedding's own ranking.

Baseline: the embedding's top-10. Boosted: take its top-50, move any exact
functional reprint of the query card to the front, keep the rest in order, and
take the top-10. This is a rule, not a learned arm: it never removes the
embedding's ranking for queries that have no reprint in the pool.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
from pathlib import Path

from gensim.models import KeyedVectors

from ml.utils.paths import PATHS


def normalize_text(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", text or "")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def normalize_type(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def reprint_groups(cards_path: Path) -> dict[str, str]:
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    groups: dict[tuple[str, str], str] = {}
    members: dict[str, str] = {}
    for card in cards:
        name = card.get("name")
        text = normalize_text(card.get("oracle_text") or "")
        if not name or not text or len(text) < 10:
            continue
        key = (text, normalize_type(card.get("type_line") or ""))
        group = groups.setdefault(key, f"g{len(groups)}")
        members[name] = group
    return members


def judged_scores(test_set: dict) -> dict[str, dict[str, float]]:
    judged: dict[str, dict[str, float]] = {}
    for query, entry in test_set.get("queries", {}).items():
        scores: dict[str, float] = {}
        for ann in entry.get("annotations", []):
            if not isinstance(ann, dict):
                continue
            candidate = ann.get("candidate")
            value = ann.get("functional_score")
            if candidate and isinstance(value, (int, float)):
                scores[candidate] = max(scores.get(candidate, 0.0), float(value))
        if scores:
            judged[query] = scores
    return judged


def ndcg(ranked: list[str], rel: dict[str, float], k: int = 10) -> float:
    dcg = sum(rel.get(name, 0.0) / math.log2(i + 2) for i, name in enumerate(ranked[:k]))
    ideal = sorted(rel.values(), reverse=True)[:k]
    idcg = sum(value / math.log2(i + 2) for i, value in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test-set", type=Path, default=PATHS.data / "test_sets" / "annotated_magic_v2.json"
    )
    parser.add_argument(
        "--embedding", type=Path, default=PATHS.embeddings / "magic_v7_spectral_mu35.wv"
    )
    parser.add_argument(
        "--cards", type=Path, default=PATHS.data / "raw" / "scryfall" / "oracle-cards.json"
    )
    parser.add_argument(
        "--judged-only",
        action="store_true",
        help=(
            "rank only candidates that carry a judged score. nDCG counts an "
            "unjudged card as 0, so promoting an unjudged reprint is a loss by "
            "construction; this measures the rule on what the labels can see."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PATHS.project_root / "data-local" / "label-anchor-20261030" / "reprint_boost.json",
    )
    args = parser.parse_args()

    test_set = json.loads(args.test_set.read_text(encoding="utf-8"))
    judged = judged_scores(test_set)
    groups = reprint_groups(args.cards)
    by_group: dict[str, set[str]] = {}
    for name, group in groups.items():
        by_group.setdefault(group, set()).add(name)
    vectors = KeyedVectors.load(str(args.embedding))

    baseline_scores: dict[str, float] = {}
    boosted_scores: dict[str, float] = {}
    covered: dict[str, bool] = {}
    judged_pool_sizes: list[int] = []
    for query, rel in judged.items():
        if query not in vectors:
            continue
        pool = [name for name, _ in vectors.most_similar(query, topn=50) if name != query]
        if args.judged_only:
            pool = [name for name in pool if name in rel]
            if len(pool) < 2:
                continue
            judged_pool_sizes.append(len(pool))
        # A query outside the reprint groups (alternate printing, token) has
        # no reprints; do not let a missing key become group ""
        reprints = by_group.get(groups.get(query), set()) - {query}
        present = [name for name in pool if name in reprints]
        covered[query] = bool(present)
        boosted = present + [name for name in pool if name not in present]
        baseline_scores[query] = ndcg(pool[:10], rel)
        boosted_scores[query] = ndcg(boosted[:10], rel)

    queries = sorted(baseline_scores)
    covered_queries = [query for query in queries if covered[query]]

    def mean(scores: dict[str, float], subset: list[str]) -> float:
        return sum(scores[query] for query in subset) / len(subset) if subset else 0.0

    rng = random.Random(13)
    deltas = []
    for _ in range(1000):
        sample = [rng.choice(queries) for _ in queries]
        deltas.append(sum(boosted_scores[q] - baseline_scores[q] for q in sample) / len(sample))
    deltas.sort()
    result = {
        "queries": len(queries),
        "reprint_covered": len(covered_queries),
        "baseline_ndcg_at_10": round(mean(baseline_scores, queries), 4),
        "boosted_ndcg_at_10": round(mean(boosted_scores, queries), 4),
        "delta": round(mean(boosted_scores, queries) - mean(baseline_scores, queries), 4),
        "delta_ci_95": [round(deltas[25], 4), round(deltas[974], 4)],
        "covered_baseline_ndcg_at_10": round(mean(baseline_scores, covered_queries), 4),
        "covered_boosted_ndcg_at_10": round(mean(boosted_scores, covered_queries), 4),
        "covered_delta": round(
            mean(boosted_scores, covered_queries) - mean(baseline_scores, covered_queries), 4
        ),
        "judged_pool_mean": round(statistics.mean(judged_pool_sizes), 2)
        if judged_pool_sizes
        else None,
        "seed": 13,
        "bootstrap_resamples": 1000,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
