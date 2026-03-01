#!/usr/bin/env python3
"""Convert pairwise v3/v5 annotations to graded-relevance test set format.

Transforms:
  {"labels": [{"card1": "A", "card2": "B", "consensus": {"z_score": 0.8, ...}, ...}]}
Into:
  {"queries": {"A": {"use_case": "...", "highly_relevant": ["B"], ...}}}

Usage:
  PYTHONPATH=src .venv/bin/python scripts/annotation/convert_to_test_set.py \
    --input data/annotations/yugioh_500_v3.json \
    --output data/test_set_from_annotations_yugioh.json \
    --min-pairs 3
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


# Z-score thresholds for graded relevance.
# These are calibrated to the z-normalized consensus from _recompute_agreement.
# Z-scores are per-batch relative, so thresholds are percentile-based.
GRADE_THRESHOLDS = {
    "highly_relevant": 0.70,     # top ~10%
    "relevant": 0.50,            # 50-70%
    "somewhat_relevant": 0.35,   # 35-50%
    "marginally_relevant": 0.20, # 20-35%
    # below 0.20 = irrelevant
}

# Map similarity_type to use_case
TYPE_TO_USE_CASE = {
    "functional": "functional",
    "synergy": "synergy",
    "archetype": "archetype",
    "manabase": "functional",
    "unrelated": "functional",  # default
}


def convert(input_path: Path, min_pairs: int = 3) -> dict:
    """Convert pairwise annotations to graded relevance format."""
    with open(input_path) as f:
        data = json.load(f)

    game = data.get("game", "unknown")
    labels = data.get("labels", [])

    # Group by query card (both directions: card1->card2 and card2->card1)
    query_pairs: dict[str, list[dict]] = defaultdict(list)
    for label in labels:
        c1, c2 = label["card1"], label["card2"]
        consensus = label.get("consensus", {})
        per_judge = label.get("per_judge", {})

        # Use z_score if available, fall back to raw consensus score, then raw median
        score = consensus.get("z_score")
        if score is None:
            score = consensus.get("similarity_score")
        if score is None:
            # Compute median from per_judge
            raw = [a.get("similarity_score") for a in per_judge.values()
                   if a.get("similarity_score") is not None]
            score = sorted(raw)[len(raw) // 2] if raw else 0

        sim_type = consensus.get("similarity_type", "functional")
        agreement = label.get("agreement_level", "unknown")

        entry = {
            "card": None,  # filled per direction
            "score": score,
            "sim_type": sim_type,
            "agreement": agreement,
        }

        e1 = dict(entry, card=c2)
        e2 = dict(entry, card=c1)
        query_pairs[c1].append(e1)
        query_pairs[c2].append(e2)

    # Build test set: only include queries with enough pairs
    queries = {}
    for query_card, pairs in sorted(query_pairs.items()):
        if len(pairs) < min_pairs:
            continue

        # Determine use_case from most common sim_type
        type_counts = defaultdict(int)
        for p in pairs:
            type_counts[p["sim_type"]] += 1
        dominant_type = max(type_counts, key=type_counts.get)
        use_case = TYPE_TO_USE_CASE.get(dominant_type, "functional")

        # Grade each pair by z-score
        grades: dict[str, list[str]] = {
            "highly_relevant": [],
            "relevant": [],
            "somewhat_relevant": [],
            "marginally_relevant": [],
            "irrelevant": [],
        }

        for p in sorted(pairs, key=lambda x: x["score"], reverse=True):
            s = p["score"]
            if s >= GRADE_THRESHOLDS["highly_relevant"]:
                grades["highly_relevant"].append(p["card"])
            elif s >= GRADE_THRESHOLDS["relevant"]:
                grades["relevant"].append(p["card"])
            elif s >= GRADE_THRESHOLDS["somewhat_relevant"]:
                grades["somewhat_relevant"].append(p["card"])
            elif s >= GRADE_THRESHOLDS["marginally_relevant"]:
                grades["marginally_relevant"].append(p["card"])
            else:
                grades["irrelevant"].append(p["card"])

        # IAA: fraction of pairs with high/medium agreement
        n_agree = sum(1 for p in pairs if p["agreement"] in ("high", "medium"))
        iaa = round(n_agree / len(pairs), 3) if pairs else 0

        queries[query_card] = {
            "use_case": use_case,
            **grades,
            "iaa": iaa,
        }

    return {
        "version": "annotations_v5",
        "game": game,
        "source": str(input_path),
        "num_queries": len(queries),
        "queries": queries,
    }


def main():
    parser = argparse.ArgumentParser(description="Convert pairwise annotations to test set format")
    parser.add_argument("--input", type=Path, required=True, help="v3/v5 annotation JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output test set JSON")
    parser.add_argument("--min-pairs", type=int, default=3,
                        help="Minimum pairs per query card to include (default: 3)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found")
        return 1

    result = convert(args.input, min_pairs=args.min_pairs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Converted {args.input.name} -> {args.output.name}")
    print(f"  {result['num_queries']} queries from {len(result.get('queries', {}))} unique cards")
    # Grade distribution
    total_by_grade = defaultdict(int)
    for q in result["queries"].values():
        for grade in ("highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant", "irrelevant"):
            total_by_grade[grade] += len(q.get(grade, []))
    for grade, count in total_by_grade.items():
        print(f"  {grade}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
