#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2.0",
#     "pydantic-ai>=0.1.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Per-deck LLM annotation: archetype, power level, synergy density, missing roles.

Loads deck JSONL files, samples a configurable number of decks, and asks an LLM
to produce structured annotations. Output is useful for:
- Training: archetype detection signal for deck completion
- Eval: verify deck completion preserves archetype identity and fills role gaps
- Analysis: deck quality distribution across the dataset

Resilience features:
- Incremental save: each deck annotation is flushed to disk immediately.
- Resume: re-running skips decks already in the output file.
- --batch-size: controls how many decks to annotate per invocation.

Usage:
    # Dry run:
    uv run scripts/annotation/annotate_decks.py --game magic --dry-run

    # Annotate 50 decks:
    uv run scripts/annotation/annotate_decks.py --game magic --batch-size 50

    # Resume:
    uv run scripts/annotation/annotate_decks.py --game magic --batch-size 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.utils.paths import PATHS

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from pydantic import BaseModel, Field

    from ml.utils.pydantic_ai_helpers import make_agent

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model for per-deck annotation
# ---------------------------------------------------------------------------


class DeckAnnotation(BaseModel):
    """LLM-generated structured annotation for a full deck."""

    archetype: str = Field(
        description="Deck archetype (e.g., Burn, Control, Midrange, Aggro, Combo, Ramp, Mill, Tempo, Tokens, Stax)"
    )
    power_level: int = Field(
        ge=1,
        le=10,
        description="Deck power level: 1=casual jank, 5=FNM competitive, 7=tournament viable, 10=tier 0",
    )
    curve_quality: float = Field(
        ge=0.0,
        le=1.0,
        description="Mana curve quality 0-1: 0=terrible curve, 0.5=acceptable, 1.0=optimal for archetype",
    )
    synergy_density: float = Field(
        ge=0.0,
        le=1.0,
        description="Synergy density 0-1: 0=pile of random cards, 0.5=some synergy, 1.0=every card supports the plan",
    )
    missing_roles: list[str] = Field(
        default_factory=list,
        description="Roles the deck lacks (removal, draw, threat, ramp, counter, finisher, sideboard_plan)",
    )
    key_cards: list[str] = Field(
        default_factory=list,
        description="The 5 most important cards in the deck (by name)",
    )
    strategy_description: str = Field(
        description="1-2 sentence description of the deck's game plan",
    )
    reasoning: str = Field(
        default="",
        description="Brief justification for power level and archetype classification",
    )


# ---------------------------------------------------------------------------
# Deck loading
# ---------------------------------------------------------------------------

# Per-game deck JSONL file candidates (ordered by preference)
DECK_FILE_CANDIDATES = {
    "magic": [
        "decks/decks_magic_goldfish.jsonl",
        "decks/decks_magic_mtgtop8.jsonl",
    ],
    "yugioh": [
        "decks/decks_yugioh.jsonl",
    ],
    "pokemon": [
        "decks/decks_pokemon.jsonl",
    ],
}


def load_decks(game: str, sample_size: int = 200, seed: int = 42) -> list[dict]:
    """Load and sample decks from JSONL files.

    Returns list of deck dicts, each with at minimum 'cards' and 'deck_id'.
    """
    candidates = DECK_FILE_CANDIDATES.get(game, [])
    all_decks = []

    for rel_path in candidates:
        path = PATHS.data / rel_path
        if not path.exists():
            continue
        logger.info(f"Loading decks from {path.name}")
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Skip metadata lines
                if d.get("_meta"):
                    continue
                # Require cards
                if not d.get("cards"):
                    continue
                all_decks.append(d)
        # Use first available file
        break

    if not all_decks:
        logger.error(f"No deck JSONL files found for {game}")
        return []

    logger.info(f"Total decks loaded: {len(all_decks)}")

    # Sample
    rng = random.Random(seed)
    if len(all_decks) > sample_size:
        all_decks = rng.sample(all_decks, sample_size)
        logger.info(f"Sampled {sample_size} decks")

    return all_decks


def _deck_id(deck: dict) -> str:
    """Extract or generate a stable deck ID."""
    if deck.get("deck_id"):
        return str(deck["deck_id"])
    if deck.get("url"):
        return str(deck["url"])
    # Fallback: hash the card list
    cards = sorted(c.get("name", "") for c in deck.get("cards", []))
    return f"deck_hash_{hash(tuple(cards)) & 0xFFFFFFFF:08x}"


def _deck_prompt_context(deck: dict) -> str:
    """Build prompt context from a deck dict."""
    parts = []
    if deck.get("archetype"):
        parts.append(f"Archetype label: {deck['archetype']}")
    if deck.get("format"):
        parts.append(f"Format: {deck['format']}")
    if deck.get("source"):
        parts.append(f"Source: {deck['source']}")

    # Card list grouped by partition
    cards_by_partition: dict[str, list[str]] = {}
    for card in deck.get("cards", []):
        partition = card.get("partition", "Main")
        name = card.get("name", "?")
        count = card.get("count", 1)
        entry = f"{count}x {name}" if count > 1 else name
        cards_by_partition.setdefault(partition, []).append(entry)

    for partition, card_list in cards_by_partition.items():
        parts.append(f"\n{partition} ({len(card_list)} cards):")
        for entry in card_list:
            parts.append(f"  {entry}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------

DECK_ANNOTATION_PROMPT = """You are an expert TCG deckbuilder annotating full decks with structured labels.

For each deck, produce:
1. **archetype**: the primary archetype/strategy name
   (e.g., Burn, Control, Midrange, Aggro, Combo, Ramp, Mill, Tempo, Tokens, Stax, Toolbox)
2. **power_level**: deck competitive power 1-10
   1=casual jank, 3=kitchen table, 5=FNM/locals competitive, 7=tournament viable,
   9=top-tier meta deck, 10=broken/ban-worthy
3. **curve_quality**: mana curve quality 0-1
   Consider whether the deck has appropriate early plays, smooth progression,
   and a reasonable top end for its strategy.
4. **synergy_density**: how well the cards work together 0-1
   0=random pile, 0.5=some synergies, 1.0=every card supports the game plan
5. **missing_roles**: what the deck lacks
   Choose from: removal, draw, threat, ramp, counter, finisher, sideboard_plan, land
6. **key_cards**: the 5 most important cards (names only)
7. **strategy_description**: 1-2 sentence game plan description
8. **reasoning**: brief justification for power level and archetype

If a source archetype label is provided, use it as a hint but override it if the
card list tells a different story. Judge based on the actual cards present.
"""


async def annotate_deck(
    agent,
    deck: dict,
    game: str,
    semaphore: asyncio.Semaphore,
    model_name: str,
) -> dict:
    """Annotate a single deck via LLM."""
    ctx = _deck_prompt_context(deck)
    prompt = f"Annotate this {game.upper()} deck:\n\n{ctx}"
    deck_id = _deck_id(deck)

    async with semaphore:
        try:
            result = await agent.run(prompt)
            ann = result.output
            return {
                "deck_id": deck_id,
                "archetype": ann.archetype,
                "power_level": ann.power_level,
                "curve_quality": ann.curve_quality,
                "synergy_density": ann.synergy_density,
                "missing_roles": ann.missing_roles,
                "key_cards": ann.key_cards,
                "strategy_description": ann.strategy_description,
                "reasoning": ann.reasoning,
                "source_archetype": deck.get("archetype", ""),
                "source_format": deck.get("format", ""),
                "num_cards": sum(c.get("count", 1) for c in deck.get("cards", [])),
                "llm_model": model_name,
                "game": game,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.warning(f"Annotation failed for {deck_id}: {e}")
            return {
                "deck_id": deck_id,
                "error": str(e),
                "llm_model": model_name,
                "game": game,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }


# ---------------------------------------------------------------------------
# Incremental I/O
# ---------------------------------------------------------------------------


def _load_existing(path: Path) -> dict:
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Corrupt output file {path}, starting fresh: {e}")
    return {"version": "1.0", "decks": {}}


def _flush(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_pipeline(
    game: str = "magic",
    sample_size: int = 200,
    batch_size: int | None = None,
    concurrency: int = 5,
    dry_run: bool = False,
    output_path: Path | None = None,
) -> dict:
    if output_path is None:
        output_path = PATHS.data / "test_sets" / f"deck_annotations_{game}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load decks
    decks = load_decks(game, sample_size=sample_size)
    if not decks:
        return {"error": f"No decks found for {game}"}

    # Load existing for resume
    existing = _load_existing(output_path)
    already_done = set(existing.get("decks", {}).keys())
    logger.info(f"Decks sampled: {len(decks)}, already annotated: {len(already_done)}")

    # Filter to unannotated
    todo = [(d, _deck_id(d)) for d in decks]
    todo = [(d, did) for d, did in todo if did not in already_done]
    if batch_size is not None and batch_size > 0:
        todo = todo[:batch_size]

    if not todo:
        logger.info("All sampled decks already annotated")
        return {"n_existing": len(already_done), "n_new": 0}

    if dry_run:
        print(f"\n--- Dry Run ---")
        print(f"  Total decks sampled: {len(decks)}")
        print(f"  Already annotated: {len(already_done)}")
        print(f"  Decks to annotate: {len(todo)}")
        archetypes = [d.get("archetype", "unknown") for d, _ in todo[:20]]
        print(f"  Sample archetypes: {archetypes}")
        return {"n_existing": len(already_done), "n_new": len(todo), "dry_run": True}

    # Check for API keys
    has_keys = bool(
        os.getenv("OPENAI_API_KEY")
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    )
    if not HAS_PYDANTIC_AI or not has_keys:
        logger.error(
            "pydantic-ai and an API key are required. "
            "Set one of: OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENROUTER_API_KEY"
        )
        return {"error": "No LLM available"}

    model_name = os.getenv("ANNOTATOR_MODEL_DECK", "google/gemini-3-flash-preview")
    agent = make_agent(model_name, DeckAnnotation, DECK_ANNOTATION_PROMPT)
    logger.info(f"Annotating {len(todo)} decks with model={model_name}")

    sem = asyncio.Semaphore(concurrency)
    decks_data = dict(existing.get("decks", {}))
    n_done = 0
    t0 = time.monotonic()

    for deck, deck_id in todo:
        result = await annotate_deck(agent, deck, game, sem, model_name)
        decks_data[deck_id] = result
        n_done += 1

        # Incremental save
        doc = {
            "version": "1.0",
            "game": game,
            "llm_model": model_name,
            "updated": datetime.now(timezone.utc).isoformat(),
            "num_decks": len(decks_data),
            "decks": decks_data,
        }
        _flush(output_path, doc)

        if n_done % 10 == 0 or n_done == len(todo):
            elapsed = time.monotonic() - t0
            rate = n_done / elapsed if elapsed > 0 else 0
            logger.info(
                f"  Progress: {n_done}/{len(todo)} ({rate:.1f} decks/s, {len(decks_data)} total)"
            )

    print(f"\n--- Deck Annotation Summary ---")
    print(f"  New this run: {n_done}")
    print(f"  Total annotated: {len(decks_data)}")
    print(f"  Output: {output_path}")

    return {
        "n_existing": len(already_done),
        "n_new": n_done,
        "n_total": len(decks_data),
        "output_path": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Per-deck LLM annotation (archetype, power level, synergy density).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supports incremental save and resume. Re-run to continue where you left off.

Examples:
  uv run scripts/annotation/annotate_decks.py --game magic --dry-run
  uv run scripts/annotation/annotate_decks.py --game magic --batch-size 50
  uv run scripts/annotation/annotate_decks.py --game magic --sample-size 500 --batch-size 100
""",
    )
    parser.add_argument("--game", type=str, default="magic", help="Game name")
    parser.add_argument(
        "--sample-size", type=int, default=200, help="Number of decks to sample from JSONL"
    )
    parser.add_argument("--batch-size", type=int, default=None, help="Max decks per run")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent LLM calls")
    parser.add_argument("--output", type=Path, default=None, help="Output path")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without API calls")
    args = parser.parse_args()

    result = asyncio.run(
        run_pipeline(
            game=args.game,
            sample_size=args.sample_size,
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
            output_path=args.output,
        )
    )

    if "error" in result:
        logger.error(result["error"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
