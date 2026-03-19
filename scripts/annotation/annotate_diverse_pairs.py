#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2.0",
#     "pydantic-ai>=0.1.0",
#     "python-dotenv>=1.0.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Annotate diverse pairs and integrate into test sets.

Takes the diverse pairs from generate_diverse_pairs.py (text-similarity,
role-matched, hard-negative, budget pairs) and annotates them via LLM,
then integrates the results into the annotated_*_v2.json test sets.

This breaks the embedding echo chamber by adding pairs the embedding
model MISSES -- functional substitutes across archetypes, cards with
similar text but different co-occurrence, etc.

Usage:
    uv run scripts/annotation/annotate_diverse_pairs.py --game magic
    uv run scripts/annotation/annotate_diverse_pairs.py --all-games
    uv run scripts/annotation/annotate_diverse_pairs.py --game magic --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def load_diverse_pairs(game: str) -> list[dict]:
    """Load diverse pairs JSONL."""
    path = DATA_DIR / "annotations" / f"diverse_pairs_{game}.jsonl"
    if not path.exists():
        return []
    pairs = []
    with open(path) as f:
        for line in f:
            if line.strip():
                pairs.append(json.loads(line))
    return pairs


def load_card_metadata(game: str) -> dict[str, dict]:
    """Load card metadata from enriched CSV."""
    try:
        import pandas as pd
    except ImportError:
        return {}
    path = DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, low_memory=False)
    result = {}
    for _, row in df.iterrows():
        n = str(row.get("name", ""))
        if n:
            result[n] = {
                k: v for k, v in row.to_dict().items() if not (isinstance(v, float) and v != v)
            }
    return result


def _card_context(name: str, card_data: dict[str, dict]) -> str:
    info = card_data.get(name, {})
    if not info:
        return name
    parts = [name]
    if info.get("type"):
        parts.append(f"  Type: {info['type']}")
    if info.get("mana_cost"):
        parts.append(f"  Mana cost: {info['mana_cost']}")
    if info.get("oracle_text"):
        parts.append(f"  Text: {str(info['oracle_text'])[:300]}")
    return "\n".join(parts)


async def annotate_pair(
    agent,
    card1: str,
    card2: str,
    pair_meta: dict,
    game: str,
    card_data: dict,
    sem: asyncio.Semaphore,
) -> dict:
    """Annotate a single diverse pair."""
    c1_ctx = _card_context(card1, card_data)
    c2_ctx = _card_context(card2, card_data)
    source = pair_meta.get("source", "unknown")

    prompt = f"""Judge the similarity between these two {game.upper()} cards.

Card A:
{c1_ctx}

Card B:
{c2_ctx}

Context: This pair was selected via {source} analysis (NOT from embedding neighbors).
The embedding cosine similarity is {pair_meta.get("emb_sim", "unknown")}.

**CALIBRATION ANCHORS**:
- 1.0: Functional reprint
- 0.8: Same role, minor differences
- 0.6: Related function, different power level
- 0.4: Same archetype, different role
- 0.2: Tangential connection
- 0.0: Unrelated

Rate similarity, classify mode, and fill all extended fields."""

    async with sem:
        try:
            result = await agent.run(prompt)
            ann = result.output
            return {
                "query": card1,
                "candidate": card2,
                "cosine_similarity": pair_meta.get("emb_sim", 0),
                "relevance": _score_to_relevance(ann.similarity_score),
                "mode": _classify_mode(ann),
                "similarity_score": ann.similarity_score,
                "functional_score": ann.functional_score,
                "synergy_score": ann.synergy_score,
                "meta_relevance": ann.meta_relevance,
                "reasoning": ann.reasoning,
                "is_substitute": ann.is_substitute,
                "substitutability": getattr(ann, "substitutability", 0.0),
                "combo_potential": getattr(ann, "combo_potential", False),
                "same_archetype": getattr(ann, "same_archetype", False),
                "upgrade_direction": getattr(ann, "upgrade_direction", "neither"),
                "mana_efficiency_comparison": getattr(ann, "mana_efficiency_comparison", "similar"),
                "card_a_role": getattr(ann, "card_a_role", ""),
                "card_b_role": getattr(ann, "card_b_role", ""),
                "card_a_power_level": getattr(ann, "card_a_power_level", 5),
                "card_b_power_level": getattr(ann, "card_b_power_level", 5),
                "relationship_types": getattr(ann, "relationship_types", []),
                "confidence": getattr(ann, "confidence", 0.5),
                "pair_source": source,
                "llm_model": os.getenv(
                    "ANNOTATOR_MODEL_SIMILARITY", "anthropic/claude-haiku-4.5"
                ).split(",")[0],
                "game": game,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.warning(f"Annotation failed for {card1} <-> {card2}: {e}")
            return None


def _score_to_relevance(score: float) -> str:
    if score >= 0.70:
        return "highly_relevant"
    if score >= 0.50:
        return "relevant"
    if score >= 0.30:
        return "somewhat_relevant"
    if score >= 0.15:
        return "marginally_relevant"
    return "irrelevant"


def _classify_mode(ann) -> str:
    func = getattr(ann, "functional_score", None) or 0.0
    syn = getattr(ann, "synergy_score", None) or 0.0
    meta = getattr(ann, "meta_relevance", None) or 0.0
    sim_type = getattr(ann, "similarity_type", "")
    if sim_type == "functional":
        return "substitution"
    if sim_type == "synergy":
        return "synergy"
    scores = {"substitution": func, "synergy": syn, "meta": meta}
    if max(scores.values()) > 0:
        return max(scores, key=scores.get)
    return "synergy"


async def run_annotation(game: str, dry_run: bool = False, concurrency: int = 10) -> dict:
    """Annotate diverse pairs and integrate into test set."""
    pairs = load_diverse_pairs(game)
    if not pairs:
        return {"game": game, "error": "no diverse pairs"}

    logger.info(f"{game}: {len(pairs)} diverse pairs to annotate")

    if dry_run:
        sources = {}
        for p in pairs:
            s = p.get("source", "unknown")
            sources[s] = sources.get(s, 0) + 1
        cost = len(pairs) * 700 * 0.001 / 1000  # ~$0.001/pair for Haiku
        return {
            "game": game,
            "pairs": len(pairs),
            "sources": sources,
            "cost_usd": round(cost, 2),
            "dry_run": True,
        }

    # Load card metadata
    card_data = load_card_metadata(game)
    logger.info(f"Loaded {len(card_data)} card metadata entries")

    # Set up LLM
    model_name = os.getenv("ANNOTATOR_MODEL_SIMILARITY", "anthropic/claude-haiku-4.5").split(",")[0]
    from ml.annotation.llm_annotator import CardSimilarityAnnotation
    from ml.utils.pydantic_ai_helpers import make_agent

    prompt_base = "You are an expert TCG judge. Judge card similarity and fill ALL fields."
    agent = make_agent(model_name, CardSimilarityAnnotation, prompt_base)
    sem = asyncio.Semaphore(concurrency)

    # Annotate all pairs concurrently (semaphore limits parallelism)
    annotations_by_query: dict[str, list[dict]] = {}
    n_done = 0
    n_failed = 0
    t0 = time.monotonic()

    async def _annotate_one(i: int, pair: dict) -> tuple[int, dict | None]:
        card1 = pair["card1"]
        card2 = pair["card2"]
        result = await annotate_pair(agent, card1, card2, pair, game, card_data, sem)
        return i, result

    # Launch all tasks concurrently, semaphore controls actual parallelism
    tasks = [_annotate_one(i, pair) for i, pair in enumerate(pairs)]
    for coro in asyncio.as_completed(tasks):
        i, result = await coro
        if result:
            annotations_by_query.setdefault(result["query"], []).append(result)
            n_done += 1
        else:
            n_failed += 1

        total_processed = n_done + n_failed
        if total_processed % 50 == 0:
            elapsed = time.monotonic() - t0
            rate = total_processed / elapsed if elapsed > 0 else 0
            logger.info(
                f"  Progress: {total_processed}/{len(pairs)} ({rate:.1f} p/s, {n_failed} failed)"
            )

    logger.info(f"Annotated {n_done} pairs ({n_failed} failed)")

    # Integrate into test set
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if test_path.exists():
        with open(test_path) as f:
            test_data = json.load(f)
    else:
        test_data = {"version": "2.0", "game": game, "queries": {}}

    queries = test_data.get("queries", {})
    n_new_queries = 0
    n_augmented = 0

    for query_card, anns in annotations_by_query.items():
        if query_card in queries:
            # Augment existing query with diverse pairs
            existing_anns = queries[query_card].get("annotations", [])
            existing_candidates = {a.get("candidate") for a in existing_anns}
            for ann in anns:
                if ann["candidate"] not in existing_candidates:
                    existing_anns.append(ann)
                    n_augmented += 1
            queries[query_card]["annotations"] = existing_anns
        else:
            # New query from diverse pairs
            queries[query_card] = {
                "highly_relevant": [],
                "relevant": [],
                "somewhat_relevant": [],
                "marginally_relevant": [],
                "irrelevant": [],
                "use_case": "diverse",
                "annotations": anns,
            }
            # Fill relevance buckets
            for ann in anns:
                bucket = ann.get("relevance", "irrelevant")
                queries[query_card][bucket].append(ann["candidate"])
            n_new_queries += 1

    test_data["queries"] = queries
    test_data["num_queries"] = len(queries)
    test_data["updated"] = datetime.now(timezone.utc).isoformat()
    test_data["diverse_pairs_integrated"] = datetime.now(timezone.utc).isoformat()

    with open(test_path, "w") as f:
        json.dump(test_data, f, indent=2)

    logger.info(f"Integrated: {n_new_queries} new queries, {n_augmented} augmented pairs")

    return {
        "game": game,
        "annotated": n_done,
        "failed": n_failed,
        "new_queries": n_new_queries,
        "augmented_pairs": n_augmented,
        "total_queries": len(queries),
    }


async def main_async():
    parser = argparse.ArgumentParser(description="Annotate diverse pairs")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    for game in games:
        result = await run_annotation(game, args.dry_run, args.concurrency)
        print(json.dumps(result, indent=2))


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
