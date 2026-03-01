#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic-ai", "pydantic", "python-dotenv", "gensim", "anyio"]
# ///
"""
Annotate model outputs to get complete relevance judgments.

Instead of annotating random pairs, this script:
1. Runs the embedding model to get top-K similar cards for each query
2. Sends each (query, result) pair through the multi-judge annotation pipeline
3. Produces a test set where every recommended card has a ground-truth score

This is pool-based evaluation: annotate what the system actually retrieves.
Much more efficient than random sampling -- every annotation is useful.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/annotation/annotate_model_output.py \
        --game yugioh \
        --embeddings data/embeddings/yugioh_enriched.wv \
        --output data/annotations/model_output_yugioh.json \
        --num-queries 50 --top-k 20 --concurrency 10
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from gensim.models import KeyedVectors  # noqa: E402

# Reuse existing annotation infrastructure
from ml.annotation.multi_annotator_iaa import MultiAnnotatorIAA  # noqa: E402


async def annotate_model_output(args):
    """Run model, annotate its outputs, save as test set."""
    # Load embeddings
    print(f"Loading embeddings from {args.embeddings}...")
    wv = KeyedVectors.load(str(args.embeddings))
    vocab = list(wv.key_to_index.keys())
    print(f"  {len(vocab)} cards")

    # Select query cards
    rng = random.Random(args.seed)
    query_cards = rng.sample(vocab, min(args.num_queries, len(vocab)))
    print(f"  Selected {len(query_cards)} query cards")

    # Get model outputs
    pairs = []
    for query in query_cards:
        try:
            similar = wv.most_similar(query, topn=args.top_k)
            for card, score in similar:
                pairs.append((query, card, float(score)))
        except KeyError:
            continue

    print(f"  Generated {len(pairs)} (query, result) pairs to annotate")

    # Load game knowledge
    game_knowledge_path = Path(f"data/game_knowledge/{args.game}.json")
    game_knowledge = None
    if game_knowledge_path.exists():
        with open(game_knowledge_path) as f:
            game_knowledge = json.load(f)

    # Initialize annotator
    print(f"Initializing multi-annotator IAA system...")
    annotator = MultiAnnotatorIAA(
        game=args.game,
        game_knowledge=game_knowledge,
    )
    judges = [c.name for c in annotator.annotator_configs]
    print(f"  Judges: {judges}")

    # Checkpoint setup
    checkpoint_path = args.output.with_suffix(".checkpoint.jsonl")
    completed_pairs: set[tuple[str, str]] = set()

    if args.resume and checkpoint_path.exists():
        with open(checkpoint_path) as f:
            for line in f:
                d = json.loads(line)
                completed_pairs.add((d["card1"], d["card2"]))
        print(f"  Resumed: {len(completed_pairs)} pairs already completed")

    # Filter out completed pairs
    pairs_to_do = [(q, c, s) for q, c, s in pairs if (q, c) not in completed_pairs]
    print(f"  Pairs to annotate: {len(pairs_to_do)}")

    if not pairs_to_do:
        print("  All pairs already annotated!")
        return

    # Annotate
    t0 = time.time()
    sem = asyncio.Semaphore(args.concurrency)
    completed = 0
    total = len(pairs_to_do)

    def _serialize_result(result, query: str, card: str, model_score: float) -> dict:
        """Convert MultiAnnotatorResult to serializable dict."""
        entry = {
            "card1": result.card1,
            "card2": result.card2,
            "query_card": query,
            "model_score": model_score,
            "game": args.game,
            "timestamp": datetime.now().isoformat(),
            "agreement_level": result.agreement_level,
            "iaa_metrics": result.iaa_metrics,
            "consensus": {
                "similarity_score": result.consensus_annotation.similarity_score,
                "similarity_type": result.consensus_annotation.similarity_type,
                "is_substitute": result.consensus_annotation.is_substitute,
                "reasoning": result.consensus_annotation.reasoning,
            } if result.consensus_annotation else None,
            "per_judge": {
                name: {
                    "similarity_score": ann.similarity_score,
                    "similarity_type": ann.similarity_type,
                    "is_substitute": ann.is_substitute,
                    "reasoning": ann.reasoning,
                }
                for name, ann in result.annotations.items()
            },
        }
        if result.usage_by_judge:
            entry["usage"] = result.usage_by_judge
        return entry

    async def annotate_one(query: str, card: str, model_score: float):
        nonlocal completed
        async with sem:
            try:
                result = await annotator.annotate_pair_multi(query, card)
                entry = _serialize_result(result, query, card, model_score)

                # Write checkpoint
                with open(checkpoint_path, "a") as f:
                    f.write(json.dumps(entry) + "\n")

                completed += 1
                if completed % 10 == 0 or completed == total:
                    elapsed = time.time() - t0
                    rate = elapsed / completed if completed else 0
                    eta = rate * (total - completed)
                    print(f"  [{completed}/{total}] {rate:.1f}s/pair | ETA {eta/60:.0f}m")

            except Exception as e:
                print(f"  Error: {query} <-> {card}: {e}")

    tasks = [annotate_one(q, c, s) for q, c, s in pairs_to_do]
    await asyncio.gather(*tasks)

    # Finalize: convert checkpoint to structured test set
    print(f"\nFinalizing...")
    labels = []
    with open(checkpoint_path) as f:
        for line in f:
            labels.append(json.loads(line))

    # Build test set grouped by query
    from collections import defaultdict
    queries: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

    for label in labels:
        query = label.get("query_card", label["card1"])
        score = label["consensus"]["similarity_score"]

        # Grade based on raw score (not z-score, since we're building from model output)
        if score >= 0.65:
            grade = "highly_relevant"
        elif score >= 0.45:
            grade = "relevant"
        elif score >= 0.30:
            grade = "somewhat_relevant"
        elif score >= 0.15:
            grade = "marginally_relevant"
        else:
            grade = "irrelevant"

        # The other card in the pair
        other = label["card2"] if label["card1"] == query else label["card1"]
        queries[query][grade].append(other)

    test_set = {
        "version": "model_output_annotated_v1",
        "game": args.game,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "num_queries": len(queries),
        "num_pairs": len(labels),
        "model_source": str(args.embeddings),
        "top_k": args.top_k,
        "queries": {q: dict(grades) for q, grades in queries.items()},
    }

    with open(args.output, "w") as f:
        json.dump(test_set, f, indent=2)

    # Summary
    grade_counts = defaultdict(int)
    for q_grades in queries.values():
        for grade, cards in q_grades.items():
            grade_counts[grade] += len(cards)

    print(f"\nTest set written to {args.output}")
    print(f"  {len(queries)} queries, {len(labels)} annotated pairs")
    for grade in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant", "irrelevant"]:
        print(f"  {grade}: {grade_counts[grade]}")


def main():
    parser = argparse.ArgumentParser(description="Annotate model output for pool-based evaluation")
    parser.add_argument("--game", required=True, choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--num-queries", type=int, default=50,
                        help="Number of query cards to sample (default: 50)")
    parser.add_argument("--top-k", type=int, default=20,
                        help="Number of top results to annotate per query (default: 20)")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if not args.embeddings.exists():
        print(f"Error: embeddings not found: {args.embeddings}")
        return 1

    asyncio.run(annotate_model_output(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
