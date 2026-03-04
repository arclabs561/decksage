"""
DeckSage Explain API -- LLM-generated similarity explanations.

One Haiku call explains all results for a query in batch.
Results are cached in-memory keyed on (game, query, result_set).

Configuration via .env:
- OPENROUTER_API_KEY: Required
- EXPLAIN_MODEL: Optional override (default: anthropic/claude-haiku-4.5)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional deps
# ---------------------------------------------------------------------------

try:
    from openai import OpenAI

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

explain_router = APIRouter(prefix="/v1", tags=["explain"])

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ExplainRequest(BaseModel):
    game: str = Field(..., description="Game: magic, pokemon, yugioh")
    query: str = Field(..., description="Query card name")
    results: list[str] = Field(..., min_length=1, max_length=20, description="Result card names")
    query_metadata: dict[str, Any] | None = Field(None, description="Query card metadata")
    results_metadata: dict[str, dict[str, Any]] | None = Field(
        None, description="Metadata per result card {card_name: {...}}"
    )


class CardExplanation(BaseModel):
    reason: str = Field(..., description="1-2 sentence explanation of similarity")
    shared_traits: list[str] = Field(default_factory=list, description="Shared traits/mechanics")
    key_difference: str | None = Field(None, description="Main differentiator")


class ExplainResponse(BaseModel):
    query: str
    game: str
    explanations: dict[str, CardExplanation]
    model: str
    cached: bool = False
    latency_ms: int | None = None


# ---------------------------------------------------------------------------
# Cache (in-memory, TTL-based)
# ---------------------------------------------------------------------------

_CACHE_TTL = 3600  # 1 hour
_cache: dict[str, tuple[float, dict[str, CardExplanation]]] = {}


def _cache_key(game: str, query: str, results: list[str]) -> str:
    """Content-addressed cache key."""
    payload = f"{game}:{query}:{','.join(sorted(results))}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _cache_get(key: str) -> dict[str, CardExplanation] | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, data = entry
    if time.time() - ts > _CACHE_TTL:
        del _cache[key]
        return None
    return data


def _cache_set(key: str, data: dict[str, CardExplanation]) -> None:
    # Evict oldest if cache too large
    if len(_cache) > 500:
        oldest_key = min(_cache, key=lambda k: _cache[k][0])
        del _cache[oldest_key]
    _cache[key] = (time.time(), data)


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

_client: OpenAI | None = None

EXPLAIN_MODEL = os.getenv("EXPLAIN_MODEL", "anthropic/claude-haiku-4.5")


def _get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENROUTER_API_KEY not configured")
    _client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    return _client


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_GAME_CONTEXT = {
    "magic": "Magic: The Gathering. Cards have mana cost, power/toughness, creature types, keyword abilities (flying, trample, etc), and oracle text describing effects.",
    "pokemon": "Pokemon TCG. Cards have HP, energy types, attacks with energy costs, weakness/resistance, retreat cost, and abilities. Cards can be Basic, Stage 1/2, or Trainer/Supporter.",
    "yugioh": "Yu-Gi-Oh! Cards have ATK/DEF, level/rank, attribute (DARK, LIGHT, etc), type (Spellcaster, Dragon, etc), and card text. Cards can be Monster, Spell, or Trap.",
}


def _build_prompt(
    game: str,
    query: str,
    results: list[str],
    query_meta: dict[str, Any] | None,
    results_meta: dict[str, dict[str, Any]] | None,
) -> str:
    game_ctx = _GAME_CONTEXT.get(game, f"Card game: {game}")

    # Build metadata context
    meta_lines = []
    if query_meta:
        meta_lines.append(f"QUERY CARD: {query}")
        for k, v in query_meta.items():
            if v and k not in ("image_url",):
                meta_lines.append(f"  {k}: {v}")

    for card in results:
        meta_lines.append(f"\nRESULT: {card}")
        if results_meta and card in results_meta:
            for k, v in results_meta[card].items():
                if v and k not in ("image_url",):
                    meta_lines.append(f"  {k}: {v}")

    meta_block = "\n".join(meta_lines) if meta_lines else "No metadata available."

    return f"""You are a {game} expert. Explain why each result card is similar to the query card.

GAME: {game_ctx}

{meta_block}

For each result card, provide:
1. "reason": 1-2 sentence explanation of WHY this card is similar (shared role, mechanics, strategy, or archetype)
2. "shared_traits": 2-4 shared traits as short strings
3. "key_difference": one sentence on the main difference (optional, omit if obvious)

Be specific about game mechanics. Don't just say "both are creatures" -- explain the functional similarity.

Return ONLY a JSON object mapping card name to explanation:
{{
  "Card Name": {{
    "reason": "...",
    "shared_traits": ["...", "..."],
    "key_difference": "..."
  }}
}}"""


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@explain_router.post("/explain", response_model=ExplainResponse)
async def explain_similarity(request: ExplainRequest):
    """Explain why result cards are similar to the query card using LLM."""
    if not HAS_OPENAI:
        raise HTTPException(status_code=503, detail="openai package not installed")

    key = _cache_key(request.game, request.query, request.results)
    cached = _cache_get(key)
    if cached is not None:
        return ExplainResponse(
            query=request.query,
            game=request.game,
            explanations=cached,
            model=EXPLAIN_MODEL,
            cached=True,
        )

    client = _get_client()
    prompt = _build_prompt(
        request.game,
        request.query,
        request.results,
        request.query_metadata,
        request.results_metadata,
    )

    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model=EXPLAIN_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )
        result_text = response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Explain LLM call failed: {e}")
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}") from e

    latency_ms = int((time.time() - t0) * 1000)

    # Parse JSON from response
    try:
        # Strip markdown code fences if present
        text = result_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        raw = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse explain response: {result_text[:200]}")
        # Return partial result with raw text as fallback
        explanations = {
            card: CardExplanation(reason="Explanation unavailable", shared_traits=[])
            for card in request.results
        }
        return ExplainResponse(
            query=request.query,
            game=request.game,
            explanations=explanations,
            model=EXPLAIN_MODEL,
            latency_ms=latency_ms,
        )

    # Build typed response
    explanations: dict[str, CardExplanation] = {}
    for card in request.results:
        entry = raw.get(card, {})
        if isinstance(entry, str):
            entry = {"reason": entry}
        explanations[card] = CardExplanation(
            reason=entry.get("reason", "No explanation available"),
            shared_traits=entry.get("shared_traits", []),
            key_difference=entry.get("key_difference"),
        )

    _cache_set(key, explanations)

    return ExplainResponse(
        query=request.query,
        game=request.game,
        explanations=explanations,
        model=EXPLAIN_MODEL,
        latency_ms=latency_ms,
    )
