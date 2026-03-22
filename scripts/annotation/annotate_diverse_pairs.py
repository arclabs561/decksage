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


# ---------------------------------------------------------------------------
# Prompt variants for multi-perspective annotation (reduces single-prompt bias)
# ---------------------------------------------------------------------------

GAME_EXPERTISE = {
    "magic": {
        "competitive": "You are a competitive Magic: The Gathering tournament player who has top-8'd multiple GPs. You evaluate cards by their constructed viability and metagame positioning.",
        "commander": "You are a veteran Commander/EDH player who builds decks across all power levels. You evaluate cards by their multiplayer politics, synergy potential, and fun factor.",
        "budget": "You are a budget-conscious deckbuilder who helps players find affordable alternatives. You evaluate cards primarily by their functional similarity and price-to-performance ratio.",
    },
    "pokemon": {
        "competitive": "You are a Pokemon TCG tournament player who follows the Standard and Expanded metagame closely. You evaluate cards by their competitive viability and consistency.",
        "casual": "You are a Pokemon TCG collector and casual player. You evaluate cards by their thematic connections, artwork appeal, and fun gameplay patterns.",
        "budget": "You are a budget Pokemon TCG player who helps newcomers find affordable deck options. You focus on functional substitutes and entry-level alternatives.",
    },
    "yugioh": {
        "competitive": "You are a competitive Yu-Gi-Oh! player who follows the OCG and TCG banlist closely. You evaluate cards by their combo potential, consistency, and meta relevance.",
        "casual": "You are a casual Yu-Gi-Oh! player who enjoys building thematic archetype decks. You evaluate cards by their in-archetype synergy and lore connections.",
        "budget": "You are a budget Yu-Gi-Oh! player who helps others find affordable alternatives to expensive staples. You focus on functional substitutes across price tiers.",
    },
}

# Default variant used when prompt_variants are not enabled
DEFAULT_PROMPT_VARIANT = "default"


def _build_annotation_prompt(
    card1_ctx: str,
    card2_ctx: str,
    game: str,
    variant: str = DEFAULT_PROMPT_VARIANT,
) -> str:
    """Build the annotation prompt, optionally with a persona/expertise variant."""
    persona = ""
    if variant != DEFAULT_PROMPT_VARIANT:
        game_personas = GAME_EXPERTISE.get(game, {})
        persona = game_personas.get(variant, "")

    if persona:
        preamble = f"{persona}\n\n"
    else:
        preamble = ""

    return f"""{preamble}Judge the relationship between these two {game.upper()} cards.
Base your judgment ONLY on the card text below. Do not rely on prior knowledge.

Card A:
{card1_ctx}

Card B:
{card2_ctx}

**SCORING GUIDE** (rate each dimension independently):

similarity_score (overall, 0-1):
  1.0 = Functional reprint (e.g., Lightning Bolt vs Lightning Strike minus the extra mana)
  0.7 = Same role with meaningful differences (e.g., Swords to Plowshares vs Path to Exile)
  0.4 = Related function, different power/context (e.g., Lightning Bolt vs Fireball)
  0.1 = Tangential connection only (e.g., Lightning Bolt vs Furnace of Rath)
  0.0 = Unrelated (e.g., Lightning Bolt vs Island)

functional_score (can one replace the other in a deck? 0-1):
  High = same mana cost, same effect, same deck slot
  Low = different cost, different effect, different role

synergy_score (do they work well together? 0-1):
  High = direct combo or strong synergy
  Low = no interaction

substitutability (how interchangeable are they? 0-1):
  High = swapping A for B barely changes the deck
  Low = completely different cards

**CLASSIFY** the primary relationship mode as one of: substitution, synergy, meta

Fill ALL output fields including card roles, power levels, and relationship types."""


async def annotate_pair(
    agent,
    card1: str,
    card2: str,
    pair_meta: dict,
    game: str,
    card_data: dict,
    sem: asyncio.Semaphore,
    prompt_variant: str = DEFAULT_PROMPT_VARIANT,
) -> dict:
    """Annotate a single diverse pair."""
    c1_ctx = _card_context(card1, card_data)
    c2_ctx = _card_context(card2, card_data)
    source = pair_meta.get("source", "unknown")

    prompt = _build_annotation_prompt(c1_ctx, c2_ctx, game, variant=prompt_variant)

    async with sem:
        try:
            result = await agent.run(prompt)
            ann = result.output

            # Extract token usage from pydantic-ai result
            input_tokens = 0
            output_tokens = 0
            try:
                usage = getattr(result, "usage", None) or getattr(result, "_usage", None)
                if usage:
                    if isinstance(usage, dict):
                        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
                        output_tokens = usage.get(
                            "output_tokens", usage.get("completion_tokens", 0)
                        )
                    elif hasattr(usage, "input_tokens"):
                        input_tokens = usage.input_tokens or 0
                        output_tokens = usage.output_tokens or 0
                    elif hasattr(usage, "request_tokens"):
                        input_tokens = usage.request_tokens or 0
                        output_tokens = usage.response_tokens or 0
            except Exception:
                pass

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
                "prompt_variant": prompt_variant,
                "game": game,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
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


def _checkpoint_path(game: str) -> Path:
    return DATA_DIR / "annotations" / f"diverse_checkpoint_{game}.jsonl"


def _load_checkpoint(game: str) -> set[tuple[str, str, str, str]]:
    """Load already-annotated pairs from checkpoint.

    Keys are (query, candidate, llm_model, prompt_variant) 4-tuples
    to support multi-model x multi-prompt IAA without duplicates.
    """
    path = _checkpoint_path(game)
    if not path.exists():
        return set()
    done = set()
    with open(path) as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                done.add((
                    d.get("query", ""),
                    d.get("candidate", ""),
                    d.get("llm_model", ""),
                    d.get("prompt_variant", DEFAULT_PROMPT_VARIANT),
                ))
    return done


def _save_to_checkpoint(game: str, result: dict) -> None:
    """Append one annotation result to checkpoint file."""
    path = _checkpoint_path(game)
    with open(path, "a") as f:
        f.write(json.dumps(result) + "\n")


async def run_annotation(game: str, dry_run: bool = False, concurrency: int = 10) -> dict:
    """Annotate diverse pairs and integrate into test set.

    Runs all models from ANNOTATOR_MODEL_SIMILARITY (comma-separated) for IAA.
    Each model pass is checkpointed separately so resume skips completed models.
    """
    all_pairs = load_diverse_pairs(game)
    if not all_pairs:
        return {"game": game, "error": "no diverse pairs"}

    # Parse model list for multi-judge IAA
    model_env = os.getenv("ANNOTATOR_MODEL_SIMILARITY", "anthropic/claude-haiku-4.5")
    model_names = [m.strip() for m in model_env.split(",") if m.strip()]

    # Resume support: load checkpoint (keys include model name)
    done_pairs = _load_checkpoint(game)

    # Parse prompt variants (env or default)
    # Set ANNOTATOR_PROMPT_VARIANTS=competitive,commander,budget to enable
    # Default: just "default" (no persona) for backward compat
    variant_env = os.getenv("ANNOTATOR_PROMPT_VARIANTS", DEFAULT_PROMPT_VARIANT)
    prompt_variants = [v.strip() for v in variant_env.split(",") if v.strip()]

    if dry_run:
        sources = {}
        for p in all_pairs:
            s = p.get("source", "unknown")
            sources[s] = sources.get(s, 0) + 1
        per_combo = {}
        for model_name in model_names:
            for variant in prompt_variants:
                remaining = [
                    p for p in all_pairs
                    if (p["card1"], p["card2"], model_name, variant) not in done_pairs
                ]
                per_combo[f"{model_name}+{variant}"] = len(remaining)
        total_calls = sum(per_combo.values())
        cost = total_calls * 700 * 0.001 / 1000
        return {
            "game": game,
            "total_pairs": len(all_pairs),
            "models": model_names,
            "prompt_variants": prompt_variants,
            "per_combo_remaining": per_combo,
            "total_calls": total_calls,
            "sources": sources,
            "cost_usd": round(cost, 2),
            "dry_run": True,
        }

    # Load card metadata
    card_data = load_card_metadata(game)
    logger.info(f"Loaded {len(card_data)} card metadata entries")

    from ml.annotation.llm_annotator import CardSimilarityAnnotation
    from ml.utils.pydantic_ai_helpers import make_agent

    prompt_base = "You are an expert TCG judge. Judge card similarity and fill ALL fields."

    annotations_by_query: dict[str, list[dict]] = {}
    total_done = 0
    total_failed = 0
    total_input_tokens = 0
    total_output_tokens = 0
    t0 = time.monotonic()

    # Build list of (model, variant) combos to iterate
    combos = [(m, v) for m in model_names for v in prompt_variants]
    n_combos = len(combos)

    for combo_idx, (model_name, variant) in enumerate(combos):
        # Filter to pairs not yet done by this (model, variant) combo
        pairs = [
            p for p in all_pairs
            if (p["card1"], p["card2"], model_name, variant) not in done_pairs
        ]
        combo_label = f"{model_name}+{variant}" if variant != DEFAULT_PROMPT_VARIANT else model_name
        if not pairs:
            logger.info(
                f"[{combo_idx + 1}/{n_combos}] {combo_label}: all {len(all_pairs)} pairs done, skipping"
            )
            continue

        logger.info(
            f"[{combo_idx + 1}/{n_combos}] {combo_label}: {len(pairs)} pairs to annotate"
        )

        # Build system prompt with variant persona
        game_personas = GAME_EXPERTISE.get(game, {})
        persona = game_personas.get(variant, "")
        if persona:
            system_prompt = f"{persona} Judge card similarity and fill ALL fields."
        else:
            system_prompt = "You are an expert TCG judge. Judge card similarity and fill ALL fields."

        agent = make_agent(model_name, CardSimilarityAnnotation, system_prompt)
        sem = asyncio.Semaphore(concurrency)
        n_done = 0
        n_failed = 0

        async def _annotate_one(i: int, pair: dict, _variant=variant) -> tuple[int, dict | None]:
            card1 = pair["card1"]
            card2 = pair["card2"]
            result = await annotate_pair(
                agent, card1, card2, pair, game, card_data, sem,
                prompt_variant=_variant,
            )
            return i, result

        tasks = [_annotate_one(i, pair) for i, pair in enumerate(pairs)]
        for coro in asyncio.as_completed(tasks):
            i, result = await coro
            if result:
                result["llm_model"] = model_name
                result["prompt_variant"] = variant
                annotations_by_query.setdefault(result["query"], []).append(result)
                _save_to_checkpoint(game, result)
                n_done += 1
                total_input_tokens += result.get("input_tokens", 0)
                total_output_tokens += result.get("output_tokens", 0)
            else:
                n_failed += 1

            total_processed = n_done + n_failed
            if total_processed % 50 == 0:
                elapsed = time.monotonic() - t0
                rate = total_processed / elapsed if elapsed > 0 else 0
                logger.info(
                    f"  [{combo_label}] {total_processed}/{len(pairs)} ({rate:.1f} p/s, {n_failed} failed)"
                )

        total_done += n_done
        total_failed += n_failed
        logger.info(f"  [{combo_label}] done: {n_done} annotated, {n_failed} failed")

    total_tokens = total_input_tokens + total_output_tokens
    cost_usd = (total_input_tokens * 0.25 + total_output_tokens * 1.25) / 1_000_000
    elapsed = time.monotonic() - t0
    n_done = total_done
    n_failed = total_failed

    # Merge any previously checkpointed results (from interrupted runs)
    checkpoint_path = _checkpoint_path(game)
    if checkpoint_path.exists():
        n_from_checkpoint = 0
        with open(checkpoint_path) as f:
            for line in f:
                if line.strip():
                    ann = json.loads(line)
                    q = ann.get("query", "")
                    if not q:
                        continue
                    existing_keys = {
                        (a.get("candidate"), a.get("llm_model", ""), a.get("prompt_variant", DEFAULT_PROMPT_VARIANT))
                        for a in annotations_by_query.get(q, [])
                    }
                    ann_key = (ann.get("candidate"), ann.get("llm_model", ""), ann.get("prompt_variant", DEFAULT_PROMPT_VARIANT))
                    if ann_key not in existing_keys:
                        annotations_by_query.setdefault(q, []).append(ann)
                        n_from_checkpoint += 1
        if n_from_checkpoint > 0:
            logger.info(f"Loaded {n_from_checkpoint} additional results from checkpoint")

    logger.info(f"Annotated {n_done} pairs ({n_failed} failed) in {elapsed:.0f}s")
    logger.info(
        f"Tokens: {total_input_tokens:,} in + {total_output_tokens:,} out = {total_tokens:,} total"
    )
    logger.info(f"Cost: ~${cost_usd:.4f} ({', '.join(model_names)})")

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
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 4),
        "model": model_name,
        "elapsed_s": round(elapsed, 1),
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
