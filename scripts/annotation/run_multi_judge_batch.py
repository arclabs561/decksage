#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic-ai", "pydantic", "python-dotenv"]
# ///
"""
Run multi-judge annotation batch using the existing LLMAnnotator/MultiAnnotatorIAA.

Thin wrapper that:
1. Selects diverse pairs from an edgelist
2. Runs MultiAnnotatorIAA.annotate_pair_multi() on each pair
3. Saves results with per-judge annotations, consensus, and Krippendorff's alpha

Usage:
  PYTHONPATH=src uv run scripts/annotation/run_multi_judge_batch.py \
    --game magic --edgelist data/graphs/pairs_large.edg \
    --output data/annotations/magic_multi_judge.json \
    --num-pairs 100
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load API keys
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

# Import existing infrastructure
from ml.annotation.llm_annotator import get_similarity_prompt  # noqa: E402
from ml.annotation.multi_annotator_iaa import MultiAnnotatorIAA  # noqa: E402


def load_edgelist(path: Path) -> list[tuple[str, str, float]]:
    """Load tab-separated edgelist."""
    edges = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            edges.append((parts[0], parts[1], float(parts[2]) if len(parts) > 2 else 1.0))
    return edges


def select_diverse_pairs(
    edges: list[tuple[str, str, float]],
    num_pairs: int,
    seed: int = 42,
) -> list[tuple[str, str]]:
    """Select pairs stratified across weight buckets for diversity."""
    rng = random.Random(seed)
    sorted_edges = sorted(edges, key=lambda e: e[2], reverse=True)
    n = len(sorted_edges)

    # 30% high weight, 30% medium, 20% low, 20% tail
    buckets = [
        (sorted_edges[: n // 4], 0.30),
        (sorted_edges[n // 4 : n // 2], 0.30),
        (sorted_edges[n // 2 : 3 * n // 4], 0.20),
        (sorted_edges[3 * n // 4 :], 0.20),
    ]

    selected = []
    seen = set()
    for bucket, frac in buckets:
        count = int(num_pairs * frac)
        sample = rng.sample(bucket, min(count, len(bucket)))
        for c1, c2, _ in sample:
            key = tuple(sorted([c1, c2]))
            if key not in seen:
                seen.add(key)
                selected.append((c1, c2))

    # Pad if needed
    if len(selected) < num_pairs:
        remaining = [(c1, c2) for c1, c2, _ in edges if tuple(sorted([c1, c2])) not in seen]
        extra = rng.sample(remaining, min(num_pairs - len(selected), len(remaining)))
        selected.extend(extra)

    return selected[:num_pairs]


async def annotate_one_pair(
    iaa: MultiAnnotatorIAA,
    card1: str,
    card2: str,
    game: str,
    idx: int,
    total: int,
    sem: asyncio.Semaphore,
) -> dict | None:
    """Annotate a single pair under a concurrency semaphore."""
    async with sem:
        print(f"  [{idx}/{total}] {card1} <-> {card2}", flush=True)
        try:
            result = await iaa.annotate_pair_multi(card1, card2)
            entry = {
                "card1": result.card1,
                "card2": result.card2,
                "game": game,
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
            print(f"    [{idx}] -> {result.agreement_level} ({result.iaa_metrics.get('krippendorff_alpha', 0):.2f})")
            return entry
        except Exception as e:
            print(f"    [{idx}] -> FAILED: {e}")
            return None


async def run_batch(
    game: str,
    edgelist_path: Path,
    output_path: Path,
    num_pairs: int,
    seed: int,
    concurrency: int = 5,
) -> dict:
    """Run multi-judge annotation batch with parallel pair processing."""
    # Load edges and select pairs
    print(f"Loading edgelist: {edgelist_path}")
    edges = load_edgelist(edgelist_path)
    pairs = select_diverse_pairs(edges, num_pairs, seed=seed)
    print(f"  {len(edges):,} edges, selected {len(pairs)} diverse pairs")

    # Initialize multi-annotator system (uses DEFAULT_ANNOTATORS from multi_annotator_iaa.py)
    print("Initializing multi-annotator IAA system...")
    iaa = MultiAnnotatorIAA(
        annotator_configs=None,  # uses defaults (4 diverse models)
        min_iaa_threshold=0.6,
        use_consensus=True,
    )
    print(f"  Judges: {list(iaa.agents.keys())}")
    print(f"  Concurrency: {concurrency} pairs in parallel")

    # Run annotations in parallel with semaphore-controlled concurrency
    sem = asyncio.Semaphore(concurrency)
    t0 = time.monotonic()

    tasks = [
        annotate_one_pair(iaa, c1, c2, game, i, len(pairs), sem)
        for i, (c1, c2) in enumerate(pairs, 1)
    ]
    raw_results = await asyncio.gather(*tasks)
    results = [r for r in raw_results if r is not None]

    elapsed = time.monotonic() - t0
    print(f"\nCompleted {len(results)}/{len(pairs)} pairs in {elapsed:.0f}s ({elapsed/max(len(results),1):.1f}s/pair)")

    _save(results, game, output_path)
    print(f"Saved: {output_path}")

    return {"total": len(results), "elapsed_s": round(elapsed, 1)}


def _save(results: list[dict], game: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({
            "version": "multi_judge_v1",
            "game": game,
            "generated_at": datetime.now().isoformat(),
            "num_pairs": len(results),
            "labels": results,
        }, f, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run multi-judge annotation batch")
    parser.add_argument("--game", required=True, choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--edgelist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--num-pairs", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=5, help="Max pairs to annotate in parallel")
    args = parser.parse_args()

    if not args.edgelist.exists():
        print(f"Error: edgelist not found: {args.edgelist}", file=sys.stderr)
        return 1

    asyncio.run(run_batch(
        game=args.game,
        edgelist_path=args.edgelist,
        output_path=args.output,
        num_pairs=args.num_pairs,
        seed=args.seed,
        concurrency=args.concurrency,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
