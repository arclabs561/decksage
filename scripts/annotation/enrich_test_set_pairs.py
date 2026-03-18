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
Enrich existing v2 test set annotations with extended fields.

Reads annotated_*_v2.json, finds pairs that have per-pair annotations
but lack extended fields (substitutability, upgrade_direction, card roles,
power levels, relationship types), and re-annotates them via LLM.

Incremental: saves after each query. Resume by re-running.

This is cheaper than full re-annotation because:
- Only annotates pairs that already exist (no new query selection)
- Uses a focused prompt (extended fields only, not full similarity judgment)
- Skips pairs that already have extended fields

Usage:
    # Dry run
    uv run scripts/annotation/enrich_test_set_pairs.py --game magic --dry-run

    # Enrich all pairs lacking extended fields
    uv run scripts/annotation/enrich_test_set_pairs.py --game magic

    # Batch of 50 queries
    uv run scripts/annotation/enrich_test_set_pairs.py --game magic --batch-size 50

    # All games
    uv run scripts/annotation/enrich_test_set_pairs.py --all-games
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class ExtendedPairAnnotation(BaseModel):
    """Extended annotation fields for a card pair."""

    substitutability: float = Field(
        ge=0.0,
        le=1.0,
        description="Continuous substitutability 0-1. 0=not interchangeable, 1=drop-in replacement",
    )
    upgrade_direction: str = Field(
        description="Power relationship: a_upgrades_b, b_upgrades_a, sidegrade, neither",
    )
    mana_efficiency_comparison: str = Field(
        description="Resource efficiency: a_more_efficient, b_more_efficient, similar",
    )
    combo_potential: bool = Field(
        description="Do these cards form a known combo or rules interaction?",
    )
    same_archetype: bool = Field(
        description="Would both cards typically appear in the same deck archetype?",
    )
    card_a_role: str = Field(
        description="Primary role of card A: removal, threat, ramp, draw, counter, combo_piece, utility, land, other",
    )
    card_b_role: str = Field(
        description="Primary role of card B: removal, threat, ramp, draw, counter, combo_piece, utility, land, other",
    )
    card_a_power_level: int = Field(
        ge=1,
        le=10,
        description="Power level 1-10: 1=unplayable, 5=average, 7=staple, 10=format-defining",
    )
    card_b_power_level: int = Field(
        ge=1,
        le=10,
        description="Power level 1-10: 1=unplayable, 5=average, 7=staple, 10=format-defining",
    )
    relationship_types: list[str] = Field(
        description="All that apply: functional_substitute, synergy_partner, meta_companion, curve_filler, archetype_staple, budget_alternative",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in this judgment: 0=guessing, 1=certain",
    )


ENRICH_PROMPT = """You are an expert TCG card game analyst. Given two cards and their existing similarity judgment, provide EXTENDED ANNOTATIONS.

You will receive card A, card B, the game, and context about each card.

Fill in ALL fields:
- substitutability (0-1): how interchangeable are these cards? 0=completely different, 0.5=partial overlap, 1.0=functional reprint
- upgrade_direction: is one card strictly better? One of: a_upgrades_b, b_upgrades_a, sidegrade, neither
- mana_efficiency_comparison: resource efficiency. One of: a_more_efficient, b_more_efficient, similar
- combo_potential: do these cards form a known combo? true/false
- same_archetype: would both appear in the same deck archetype? true/false
- card_a_role / card_b_role: primary role. One of: removal, threat, ramp, draw, counter, combo_piece, utility, land, other
- card_a_power_level / card_b_power_level: competitive power 1-10 (1=unplayable draft chaff, 3=fringe, 5=average constructed, 7=strong staple, 9=format-defining, 10=banned-level)
- relationship_types: ALL that apply from: functional_substitute, synergy_partner, meta_companion, curve_filler, archetype_staple, budget_alternative
- confidence: 0-1 how confident you are
"""


def _load_card_metadata(game: str) -> dict[str, dict]:
    """Load card metadata from enriched CSV."""
    try:
        import pandas as pd
    except ImportError:
        return {}

    for name in [
        f"card_attributes_{game}_enriched.csv",
        f"card_attributes_{game}.csv",
    ]:
        path = DATA_DIR / "processed" / name
        if path.exists():
            try:
                df = pd.read_csv(path, low_memory=False)
                name_col = "name" if "name" in df.columns else df.columns[0]
                result = {}
                for _, row in df.iterrows():
                    n = str(row.get(name_col, ""))
                    if n:
                        result[n] = {
                            k: v
                            for k, v in row.to_dict().items()
                            if not (isinstance(v, float) and v != v)
                        }
                return result
            except Exception as e:
                logger.debug(f"Failed to load {path}: {e}")
    return {}


def _card_context(name: str, card_data: dict[str, dict]) -> str:
    """Build card context string."""
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
    if info.get("power") and info.get("toughness"):
        parts.append(f"  P/T: {info['power']}/{info['toughness']}")
    if info.get("atk") is not None:
        parts.append(f"  ATK/DEF: {info.get('atk')}/{info.get('def_stat', '?')}")
    if info.get("hp"):
        parts.append(f"  HP: {info['hp']}")
    return "\n".join(parts)


def _needs_enrichment(ann: dict) -> bool:
    """Check if an annotation lacks extended fields."""
    # If it has a non-default substitutability or upgrade_direction, it's already enriched
    if ann.get("substitutability") and ann["substitutability"] > 0:
        return False
    if ann.get("upgrade_direction") and ann["upgrade_direction"] not in ("", "neither"):
        return False
    if ann.get("card_a_role") and ann["card_a_role"] not in ("", "other"):
        return False
    return True


async def enrich_pair(
    agent: Any,
    card_a: str,
    card_b: str,
    game: str,
    card_data: dict[str, dict],
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    """Enrich a single pair with extended fields."""
    a_ctx = _card_context(card_a, card_data)
    b_ctx = _card_context(card_b, card_data)

    prompt = f"""Game: {game.upper()}

Card A:
{a_ctx}

Card B:
{b_ctx}

Provide the extended annotation fields for this pair."""

    async with sem:
        try:
            result = await agent.run(prompt)
            ann = result.output
            return {
                "substitutability": ann.substitutability,
                "upgrade_direction": ann.upgrade_direction,
                "mana_efficiency_comparison": ann.mana_efficiency_comparison,
                "combo_potential": ann.combo_potential,
                "same_archetype": ann.same_archetype,
                "card_a_role": ann.card_a_role,
                "card_b_role": ann.card_b_role,
                "card_a_power_level": ann.card_a_power_level,
                "card_b_power_level": ann.card_b_power_level,
                "relationship_types": ann.relationship_types,
                "confidence": ann.confidence,
            }
        except Exception as e:
            logger.warning(f"Enrichment failed for {card_a} <-> {card_b}: {e}")
            return {}


async def run_enrichment(
    game: str,
    batch_size: int | None = None,
    dry_run: bool = False,
    concurrency: int = 5,
) -> dict[str, Any]:
    """Enrich all unenriched pairs in a game's test set."""
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not path.exists():
        return {"error": f"Test set not found: {path}"}

    with open(path) as f:
        data = json.load(f)

    queries = data.get("queries", {})
    card_data = _load_card_metadata(game)
    logger.info(f"Loaded card metadata: {len(card_data)} cards")

    # Find pairs needing enrichment
    to_enrich = []
    already_enriched = 0
    for qname, qdata in queries.items():
        annotations = qdata.get("annotations", [])
        for i, ann in enumerate(annotations):
            if _needs_enrichment(ann):
                to_enrich.append((qname, i, ann))
            else:
                already_enriched += 1

    logger.info(f"{game}: {len(to_enrich)} pairs need enrichment, {already_enriched} already done")

    if batch_size:
        to_enrich = to_enrich[:batch_size]
        logger.info(f"Batch limited to {len(to_enrich)} pairs")

    # Cost estimate (~400 tokens/pair at $0.002/1K for gpt-4o-mini)
    cost_est = len(to_enrich) * 400 * 0.002 / 1000
    logger.info(f"Estimated cost: ${cost_est:.2f}")

    if dry_run:
        return {
            "game": game,
            "pairs_to_enrich": len(to_enrich),
            "already_enriched": already_enriched,
            "cost_estimate_usd": round(cost_est, 2),
            "dry_run": True,
        }

    # Set up LLM agent
    model_name = os.getenv("ANNOTATOR_MODEL_SIMILARITY", "anthropic/claude-haiku-4.5").split(",")[0]
    has_keys = bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    )

    if not has_keys:
        logger.error(
            "No API keys found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, or OPENROUTER_API_KEY"
        )
        return {"error": "no API keys"}

    from ml.utils.pydantic_ai_helpers import make_agent

    agent = make_agent(model_name, ExtendedPairAnnotation, ENRICH_PROMPT)
    sem = asyncio.Semaphore(concurrency)

    n_done = 0
    n_total = len(to_enrich)
    t0 = time.monotonic()

    for qname, ann_idx, ann in to_enrich:
        card_a = ann.get("query", qname)
        card_b = ann.get("candidate", "")
        if not card_b:
            continue

        extended = await enrich_pair(agent, card_a, card_b, game, card_data, sem)
        if extended:
            # Merge extended fields into the annotation
            data["queries"][qname]["annotations"][ann_idx].update(extended)

        n_done += 1

        # Incremental save every 10 pairs
        if n_done % 10 == 0 or n_done == n_total:
            tmp = path.with_suffix(".json.tmp")
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)
            tmp.rename(path)

            elapsed = time.monotonic() - t0
            rate = n_done / elapsed if elapsed > 0 else 0
            logger.info(f"  Progress: {n_done}/{n_total} pairs ({rate:.1f} p/s)")

    # Final save
    data["enrichment_updated"] = datetime.now(timezone.utc).isoformat()
    data["enrichment_model"] = model_name
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    return {
        "game": game,
        "pairs_enriched": n_done,
        "already_enriched": already_enriched,
        "model": model_name,
    }


async def main_async():
    parser = argparse.ArgumentParser(description="Enrich v2 test set pairs with extended fields")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]

    for game in games:
        result = await run_enrichment(
            game,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            concurrency=args.concurrency,
        )
        print(json.dumps(result, indent=2))


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
