#!/usr/bin/env python3
"""Evaluate embeddings on functional-reprint families.

Families are candidate substitutes based on normalized rules text and selected
card attributes. They require validation; no judge is used to generate them,
which does not by itself rule out leakage or mismatched evaluation populations.

Usage:
    uv run scripts/evaluation/eval_reprints.py --game magic --embedding magic_v7_spectral_mu35
    uv run scripts/evaluation/eval_reprints.py --game magic --embedding magic_text_e5
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.utils.paths import PATHS


KS = (1, 5, 10)


def family_hits(neighbors: list[str], family: set[str], member: str) -> dict[int, int]:
    """Hits at each k, excluding the member itself."""
    others = [name for name in neighbors if name != member]
    return {k: len(set(others[:k]) & family) for k in KS}


def evaluate(vectors, families: list[dict], top_k: int = 10) -> dict:
    if top_k < max(KS):
        raise ValueError(f"top_k must be at least {max(KS)}")
    hits = dict.fromkeys(KS, 0)
    possible = dict.fromkeys(KS, 0)
    queries = 0
    eligible_families = 0
    ranks: list[int] = []
    per_family: list[dict] = []

    for family in families:
        members = [m for m in family["members"] if m in vectors]
        if len(members) < 2:
            continue
        eligible_families += 1
        member_set = set(members)
        family_hits_total = dict.fromkeys(KS, 0)
        for k in KS:
            possible[k] += len(members) * (len(members) - 1)
        for member in members:
            neighbors = [name for name, _ in vectors.most_similar(member, topn=top_k)]
            got = family_hits(neighbors, member_set, member)
            for k in KS:
                hits[k] += got[k]
                family_hits_total[k] += got[k]
            rank = next(
                (
                    i + 1
                    for i, name in enumerate(neighbors)
                    if name in member_set and name != member
                ),
                top_k + 1,
            )
            ranks.append(rank)
            queries += 1
        per_family.append({"size": len(members), "members": members, "hits": family_hits_total})

    return {
        "families_eligible": eligible_families,
        "queries": queries,
        "recall": {k: (hits[k] / possible[k] if possible[k] else None) for k in KS},
        "hits": hits,
        "possible": possible,
        "mean_capped_rank": statistics.fmean(ranks) if ranks else None,
        "median_capped_rank": statistics.median(ranks) if ranks else None,
        "per_family": per_family[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reprint-family recall")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--embedding", default="magic_v7_spectral_mu35")
    parser.add_argument("--families", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from gensim.models import KeyedVectors

    families_path = Path(
        args.families or PATHS.data / "derived" / f"reprint_families_{args.game}.json"
    )
    if not families_path.exists():
        print(
            f"missing {families_path}; run scripts/data/reprint_families.py first", file=sys.stderr
        )
        return 2
    emb_path = PATHS.embeddings / f"{args.embedding}.wv"
    if not emb_path.exists():
        print(f"missing {emb_path}", file=sys.stderr)
        return 2

    with open(families_path) as handle:
        payload = json.load(handle)
    if payload.get("normalization_version") != 2:
        print("stale reprint families; rebuild them before evaluating", file=sys.stderr)
        return 2
    families = payload["records"]
    vectors = KeyedVectors.load(str(emb_path))
    result = evaluate(vectors, families)
    result.update({"embedding": args.embedding, "families_file": str(families_path)})

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(
        f"embedding: {args.embedding}  families: {result['families_eligible']}  queries: {result['queries']}"
    )
    for k in KS:
        recall = result["recall"][k]
        shown = f"{recall:.3f}" if recall is not None else "n/a"
        print(f"  recall@{k:<2d} {shown}  ({result['hits'][k]}/{result['possible'][k]})")
    if result["mean_capped_rank"] is not None:
        print(
            f"  rank capped at 11: mean {result['mean_capped_rank']:.2f}"
            f"  median {result['median_capped_rank']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
