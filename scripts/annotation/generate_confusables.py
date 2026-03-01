#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic-ai", "pydantic", "python-dotenv", "gensim"]
# ///
"""
Generate confusable card pairs using frontier LLMs.

Asks LLMs to identify:
1. Hard negatives: cards that look similar but aren't substitutes
2. Hidden substitutes: cards that look different but serve the same role
3. Near-misses: cards that are almost interchangeable except for one key difference

These "confusable" pairs are high-value training signal -- they teach the embedding
model to distinguish fine-grained differences that co-occurrence alone can't capture.

Output: JSONL with pairs and LLM reasoning, suitable for annotation pipeline.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/annotation/generate_confusables.py \
        --game yugioh \
        --embeddings data/embeddings/yugioh_enriched.wv \
        --output data/annotations/confusables_yugioh.jsonl \
        --num-queries 50
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

try:
    from pydantic import BaseModel
    from pydantic_ai import Agent, ModelSettings
except ImportError:
    print("Error: pydantic-ai required")
    sys.exit(1)

from gensim.models import KeyedVectors


class ConfusablePair(BaseModel):
    """A pair of cards identified as confusable by an LLM."""
    card_a: str
    card_b: str
    confusable_type: str  # "hard_negative", "hidden_substitute", "near_miss"
    reasoning: str
    expected_similarity: float  # 0.0 to 1.0 -- what the true similarity should be


class ConfusableSet(BaseModel):
    """A set of confusable pairs for a focus card."""
    pairs: list[ConfusablePair]


SYSTEM_PROMPT = """You are a {game} trading card game expert. Your task is to identify
"confusable" card pairs -- cards that are tricky to rank by similarity.

Given a focus card and its top similar cards (from an embedding model), identify:

1. **Hard negatives** (type: "hard_negative"):
   Cards in the similar list that LOOK related but are NOT good substitutes.
   Example: two cards share a keyword but serve completely different strategic roles.
   Expected similarity: 0.05-0.25

2. **Hidden substitutes** (type: "hidden_substitute"):
   Cards NOT in the similar list that SHOULD be considered substitutes or strong synergies.
   These are cards the model is missing. Name specific cards from the game.
   Expected similarity: 0.60-0.90

3. **Near-misses** (type: "near_miss"):
   Cards that are ALMOST interchangeable except for one key difference
   (e.g., different element/type, slightly different cost, different era).
   Expected similarity: 0.40-0.65

For each pair, explain WHY it's confusable and give an expected similarity score.

IMPORTANT:
- Use exact card names as they appear in the game
- Be specific about strategic roles and interactions
- Focus on pairs that would genuinely confuse a similarity model
- Give 2-4 pairs total, mixing types
"""


async def generate_confusables_for_card(
    agent: Agent,
    card: str,
    similar_cards: list[tuple[str, float]],
    game: str,
) -> list[dict]:
    """Generate confusable pairs for one focus card."""
    similar_str = "\n".join(
        f"  {i+1}. {name} (model score: {score:.3f})"
        for i, (name, score) in enumerate(similar_cards[:15])
    )

    prompt = f"""Focus card: {card}

Top similar cards from the current model:
{similar_str}

Identify 2-4 confusable pairs involving {card}. For hidden substitutes,
name specific {game} cards that the model should rank higher."""

    try:
        result = await agent.run(prompt)
        output = result.output
        return [p.model_dump() for p in output.pairs]
    except Exception as e:
        print(f"  Error for {card}: {e}")
        return []


async def main_async(args):
    wv = KeyedVectors.load(str(args.embeddings))
    vocab = list(wv.key_to_index.keys())
    print(f"Loaded {len(vocab)} cards from {args.embeddings}")

    # Select focus cards: high-degree nodes (appear in many relationships)
    import random
    rng = random.Random(args.seed)

    # Prefer cards with diverse similarity neighborhoods
    focus_cards = rng.sample(vocab, min(args.num_queries, len(vocab)))

    provider = os.getenv("LLM_PROVIDER", "openrouter")
    model_name = args.model or os.getenv("DEFAULT_LLM_MODEL", "anthropic/claude-sonnet-4-6")
    model_id = f"{provider}:{model_name}"
    print(f"Using model: {model_id}")

    agent = Agent(
        model_id,
        output_type=ConfusableSet,
        instructions=SYSTEM_PROMPT.format(game=args.game),
        model_settings=ModelSettings(temperature=0.6, max_tokens=2000),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    total_pairs = 0
    t0 = time.time()

    # Process in batches
    batch_size = args.concurrency
    with open(args.output, "w") as f:
        for batch_start in range(0, len(focus_cards), batch_size):
            batch = focus_cards[batch_start:batch_start + batch_size]
            tasks = []
            for card in batch:
                similar = wv.most_similar(card, topn=15)
                tasks.append(generate_confusables_for_card(agent, card, similar, args.game))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for card, result in zip(batch, results):
                if isinstance(result, Exception):
                    print(f"  Error for {card}: {result}")
                    continue
                for pair in result:
                    pair["focus_card"] = card
                    pair["game"] = args.game
                    f.write(json.dumps(pair) + "\n")
                    total_pairs += 1

            elapsed = time.time() - t0
            done = batch_start + len(batch)
            print(f"  [{done}/{len(focus_cards)}] {total_pairs} pairs, {elapsed:.1f}s")

    print(f"\nDone: {total_pairs} confusable pairs written to {args.output}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


def main():
    parser = argparse.ArgumentParser(description="Generate confusable card pairs using LLMs")
    parser.add_argument("--game", required=True, choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--num-queries", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not args.embeddings.exists():
        print(f"Error: embeddings not found: {args.embeddings}")
        return 1

    asyncio.run(main_async(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
