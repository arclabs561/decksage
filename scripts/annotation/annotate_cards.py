#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "pydantic>=2.0",
#     "pydantic-ai>=0.1.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Per-card LLM annotation: role, power level, archetype fit, synergies.

Loads card metadata (oracle text, type, mana cost) from enriched CSV and asks
an LLM to produce structured annotations for each card. Output is useful for:
- Training: card role as a feature in the fusion cost matrix
- Eval: verify deck completion suggests cards matching needed roles
- UI: show card role badges in search results

Resilience features:
- Incremental save: each card annotation is flushed to disk immediately.
- Resume: re-running skips cards already in the output file.
- --batch-size: controls how many cards to annotate per invocation.

Usage:
    # Dry run:
    uv run scripts/annotation/annotate_cards.py --game magic --dry-run

    # Full run (requires API key):
    uv run scripts/annotation/annotate_cards.py --game magic --batch-size 100

    # Resume after interruption:
    uv run scripts/annotation/annotate_cards.py --game magic --batch-size 100
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
# Pydantic model for per-card annotation
# ---------------------------------------------------------------------------


class CardAnnotation(BaseModel):
    """LLM-generated structured annotation for a single card."""

    name: str = Field(description="Card name")
    role: str = Field(
        description="Primary role: removal, threat, ramp, draw, counter, combo_piece, utility, land, other"
    )
    secondary_roles: list[str] = Field(
        default_factory=list,
        description="Secondary roles (same vocabulary as primary role)",
    )
    power_level: int = Field(
        ge=1,
        le=10,
        description="Competitive power level: 1=unplayable, 5=average, 7=staple, 10=format-defining",
    )
    archetype_fit: list[str] = Field(
        default_factory=list,
        description="Archetypes this card fits (e.g., 'Burn', 'Control', 'Aggro', 'Combo')",
    )
    key_synergies: list[str] = Field(
        default_factory=list,
        description="Cards it synergizes with (by name, up to 5)",
    )
    format_viability: dict[str, float] = Field(
        default_factory=dict,
        description="Format viability scores 0-1 (e.g., {'modern': 0.8, 'standard': 0.0, 'commander': 0.6})",
    )
    is_staple: bool = Field(
        default=False,
        description="True if this card is a format-defining staple in at least one format",
    )
    complexity: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Rules complexity: 1=vanilla/simple, 2=moderate (keywords/triggers), 3=complex (multiple interactions)",
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of role/power assessment",
    )


# ---------------------------------------------------------------------------
# Card metadata loading
# ---------------------------------------------------------------------------


def load_card_metadata(game: str) -> dict[str, dict]:
    """Load card metadata from enriched CSV. Returns {name: {col: val}}."""
    import pandas as pd

    candidates = [
        PATHS.processed / f"card_attributes_{game}_enriched.csv",
        PATHS.processed / f"card_attributes_enriched.csv" if game == "magic" else None,
        PATHS.processed / f"card_attributes_{game}.csv",
    ]
    for p in candidates:
        if p is None or not p.exists():
            continue
        df = pd.read_csv(p, low_memory=False)
        name_col = "name" if "name" in df.columns else df.columns[0]
        metadata = {}
        for _, row in df.iterrows():
            name = str(row.get(name_col, "")).strip()
            if name:
                metadata[name] = {k: v for k, v in row.to_dict().items() if pd.notna(v)}
        logger.info(f"Loaded {len(metadata)} cards from {p.name}")
        return metadata

    logger.error(f"No card attribute CSV found for game={game}")
    return {}


def _card_prompt_context(name: str, info: dict) -> str:
    """Build a context block for a single card."""
    parts = [f"Name: {name}"]
    if info.get("type_line") or info.get("type"):
        parts.append(f"Type: {info.get('type_line') or info.get('type')}")
    if info.get("mana_cost"):
        parts.append(f"Mana cost: {info['mana_cost']}")
    if info.get("cmc") is not None:
        parts.append(f"CMC: {info['cmc']}")
    if info.get("colors"):
        parts.append(f"Colors: {info['colors']}")
    if info.get("oracle_text") or info.get("text"):
        text = str(info.get("oracle_text") or info.get("text"))[:500]
        parts.append(f"Text: {text}")
    if info.get("power") and info.get("toughness"):
        parts.append(f"P/T: {info['power']}/{info['toughness']}")
    if info.get("atk") is not None:
        parts.append(f"ATK/DEF: {info.get('atk')}/{info.get('def_stat', '?')}")
    if info.get("hp"):
        parts.append(f"HP: {info['hp']}")
    if info.get("keywords"):
        parts.append(f"Keywords: {info['keywords']}")
    if info.get("rarity"):
        parts.append(f"Rarity: {info['rarity']}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Annotation
# ---------------------------------------------------------------------------


CARD_ANNOTATION_PROMPT = """You are an expert TCG judge annotating individual cards with structured labels.

For each card, produce:
1. **role**: primary function in a deck. Choose one of:
   removal, threat, ramp, draw, counter, combo_piece, utility, land, other
2. **secondary_roles**: any additional roles (same vocabulary, up to 2)
3. **power_level**: competitive power 1-10
   1=unplayable draft chaff, 3=fringe playable, 5=average constructed,
   7=strong staple, 9=format-defining, 10=banned-level power
4. **archetype_fit**: list of archetypes where this card sees play
   (e.g., Burn, Control, Midrange, Aggro, Combo, Ramp, Mill, Tempo, Tokens)
5. **key_synergies**: up to 5 card names this card synergizes with
6. **format_viability**: dict of format -> viability score 0-1.
   For Magic: standard, pioneer, modern, legacy, vintage, commander, pauper.
   For Yu-Gi-Oh: advanced, traditional, master_duel.
   For Pokemon: standard, expanded.
   Only include formats where viability > 0.
7. **is_staple**: true if format-defining in at least one competitive format
8. **complexity**: rules complexity 1-3
   1=vanilla or single keyword, 2=triggered abilities or moderate text,
   3=multiple interacting abilities or complex state tracking
9. **reasoning**: 1-2 sentence justification

Base your judgment on the card text and attributes provided. Be calibrated:
most cards are power_level 4-6. Reserve 8+ for proven tournament staples.
"""


async def annotate_card(
    agent,
    name: str,
    info: dict,
    game: str,
    semaphore: asyncio.Semaphore,
    model_name: str,
) -> dict:
    """Annotate a single card via LLM."""
    ctx = _card_prompt_context(name, info)
    prompt = f"Annotate this {game.upper()} card:\n\n{ctx}"

    async with semaphore:
        try:
            result = await agent.run(prompt)
            ann = result.output
            return {
                "name": name,
                "role": ann.role,
                "secondary_roles": ann.secondary_roles,
                "power_level": ann.power_level,
                "archetype_fit": ann.archetype_fit,
                "key_synergies": ann.key_synergies,
                "format_viability": ann.format_viability,
                "is_staple": ann.is_staple,
                "complexity": ann.complexity,
                "reasoning": ann.reasoning,
                "llm_model": model_name,
                "game": game,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.warning(f"Annotation failed for {name}: {e}")
            return {
                "name": name,
                "error": str(e),
                "llm_model": model_name,
                "game": game,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }


# ---------------------------------------------------------------------------
# Incremental I/O
# ---------------------------------------------------------------------------


def _load_existing(path: Path) -> dict:
    """Load existing annotations for resume."""
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Corrupt output file {path}, starting fresh: {e}")
    return {"version": "1.0", "cards": {}}


def _flush(path: Path, data: dict) -> None:
    """Atomically write output (write .tmp then rename)."""
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def run_pipeline(
    game: str = "magic",
    batch_size: int | None = None,
    concurrency: int = 5,
    dry_run: bool = False,
    output_path: Path | None = None,
) -> dict:
    """Run card annotation pipeline."""
    if output_path is None:
        output_path = PATHS.data / "test_sets" / f"card_annotations_{game}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load card metadata
    card_metadata = load_card_metadata(game)
    if not card_metadata:
        return {"error": f"No card metadata found for {game}"}

    # Load existing for resume
    existing = _load_existing(output_path)
    already_done = set(existing.get("cards", {}).keys())
    logger.info(f"Cards in metadata: {len(card_metadata)}, already annotated: {len(already_done)}")

    # Select cards to annotate (skip errored cards only if they have valid annotations)
    todo = []
    for name in card_metadata:
        if name not in already_done:
            todo.append(name)
        elif "error" in existing.get("cards", {}).get(name, {}):
            # Retry previously errored cards
            todo.append(name)
    if batch_size is not None and batch_size > 0:
        todo = todo[:batch_size]

    if not todo:
        logger.info("All cards already annotated")
        return {"n_existing": len(already_done), "n_new": 0}

    if dry_run:
        print(f"\n--- Dry Run ---")
        print(f"  Total cards in metadata: {len(card_metadata)}")
        print(f"  Already annotated: {len(already_done)}")
        print(f"  Cards to annotate: {len(todo)}")
        print(f"  Sample cards: {todo[:10]}")
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

    model_name = os.getenv("ANNOTATOR_MODEL_CARD", "google/gemini-3-flash-preview")
    agent = make_agent(model_name, CardAnnotation, CARD_ANNOTATION_PROMPT)
    logger.info(f"Annotating {len(todo)} cards with model={model_name}")

    sem = asyncio.Semaphore(concurrency)
    cards_data = dict(existing.get("cards", {}))
    n_done = 0
    t0 = time.monotonic()

    # Process in concurrent batches for throughput
    batch_chunk = concurrency * 3  # 3x concurrency for good pipelining
    for batch_start in range(0, len(todo), batch_chunk):
        batch = todo[batch_start : batch_start + batch_chunk]
        tasks = [
            annotate_card(agent, name, card_metadata.get(name, {}), game, sem, model_name)
            for name in batch
        ]
        results = await asyncio.gather(*tasks)

        for name, result in zip(batch, results):
            cards_data[name] = result
            n_done += 1

        # Incremental save after each batch
        doc = {
            "version": "1.0",
            "game": game,
            "llm_model": model_name,
            "updated": datetime.now(timezone.utc).isoformat(),
            "num_cards": len(cards_data),
            "cards": cards_data,
        }
        _flush(output_path, doc)

        elapsed = time.monotonic() - t0
        rate = n_done / elapsed if elapsed > 0 else 0
        logger.info(
            f"  Progress: {n_done}/{len(todo)} ({rate:.1f} cards/s, {len(cards_data)} total)"
        )

    remaining = len(card_metadata) - len(cards_data)
    print(f"\n--- Card Annotation Summary ---")
    print(f"  New this run: {n_done}")
    print(f"  Total annotated: {len(cards_data)}")
    print(f"  Remaining: {remaining}")
    print(f"  Output: {output_path}")

    return {
        "n_existing": len(already_done),
        "n_new": n_done,
        "n_total": len(cards_data),
        "output_path": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Per-card LLM annotation (role, power level, archetype fit).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supports incremental save and resume. Re-run to continue where you left off.

Examples:
  uv run scripts/annotation/annotate_cards.py --game magic --dry-run
  uv run scripts/annotation/annotate_cards.py --game magic --batch-size 100
  uv run scripts/annotation/annotate_cards.py --game yugioh --batch-size 50
""",
    )
    parser.add_argument("--game", type=str, default="magic", help="Game name")
    parser.add_argument("--batch-size", type=int, default=None, help="Max cards per run")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent LLM calls")
    parser.add_argument("--output", type=Path, default=None, help="Output path")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without API calls")
    args = parser.parse_args()

    result = asyncio.run(
        run_pipeline(
            game=args.game,
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
