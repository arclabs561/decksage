"""
DeckSage Chat API — LLM assistant with tool calling over SSE.

Provides a streaming chat endpoint that uses pydantic-ai agents with
DeckSage's similarity search, deck building, and contextual tools.

The agent reuses the same ApiState / embeddings / graph data that powers
the REST endpoints, calling internal functions directly (no HTTP self-calls).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional deps
# ---------------------------------------------------------------------------

try:
    from pydantic_ai import Agent, ModelSettings, RunContext, Tool
    from pydantic_ai.messages import (
        ModelMessage,
        ModelMessagesTypeAdapter,
    )

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

chat_router = APIRouter(prefix="/v1", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    game: str = Field(..., description="Game: magic, pokemon, yugioh")
    session_id: str | None = Field(None, description="Session ID for multi-turn")
    deck: dict[str, Any] | None = Field(None, description="Optional deck context")


# ---------------------------------------------------------------------------
# Session store (in-memory, TTL 1 hour)
# ---------------------------------------------------------------------------

SESSION_TTL = 3600  # seconds


@dataclass
class ChatSession:
    session_id: str
    game: str
    messages_json: list[bytes] = field(default_factory=list)
    deck_state: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)


_sessions: dict[str, ChatSession] = {}


def _cleanup_sessions() -> None:
    now = time.time()
    expired = [sid for sid, s in _sessions.items() if now - s.last_used > SESSION_TTL]
    for sid in expired:
        del _sessions[sid]


def _get_or_create_session(
    session_id: str | None, game: str, deck: dict[str, Any] | None
) -> ChatSession:
    _cleanup_sessions()
    if session_id and session_id in _sessions:
        sess = _sessions[session_id]
        sess.last_used = time.time()
        sess.game = game
        if deck is not None:
            sess.deck_state = deck
        return sess
    sid = session_id or uuid.uuid4().hex[:16]
    sess = ChatSession(session_id=sid, game=game, deck_state=deck)
    _sessions[sid] = sess
    return sess


# ---------------------------------------------------------------------------
# Chat deps (injected into agent tools)
# ---------------------------------------------------------------------------


@dataclass
class ChatDeps:
    """Dependencies injected into pydantic-ai tools at runtime."""

    game: str
    embeddings: Any  # KeyedVectors
    graph: dict[str, dict[str, float]]
    card_attrs: dict[str, dict] | None = None
    deck: dict[str, int] | None = None


# ---------------------------------------------------------------------------
# Agent tools (adapted from scripts/deck_assistant.py)
# ---------------------------------------------------------------------------


def find_similar_cards(
    ctx: RunContext[ChatDeps],
    card_name: str,
    top_k: int = 10,
    method: str = "embedding",
) -> list[dict[str, Any]]:
    """Find cards similar to a given card.

    Args:
        card_name: The card to find similar cards for.
        top_k: Number of results (default 10).
        method: "embedding" (vector similarity) or "cooccurrence" (tournament co-play).
    """
    dc = ctx.deps

    if method == "cooccurrence":
        neighbors = dc.graph.get(card_name, {})
        if not neighbors:
            return [{"error": f"'{card_name}' not found in co-occurrence graph"}]
        sorted_n = sorted(neighbors.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [{"card": c, "score": round(w, 4), "source": "cooccurrence"} for c, w in sorted_n]

    if card_name not in dc.embeddings:
        candidates = [k for k in dc.embeddings.key_to_index if card_name.lower() in k.lower()]
        if candidates:
            card_name = candidates[0]
        else:
            return [{"error": f"'{card_name}' not found. Try a different spelling."}]

    results = dc.embeddings.most_similar(card_name, topn=top_k)
    return [
        {"card": card, "score": round(float(score), 4), "source": "embedding"}
        for card, score in results
    ]


def search_cards_by_name(
    ctx: RunContext[ChatDeps],
    query: str,
    limit: int = 10,
) -> list[str]:
    """Search for card names containing the query string (case-insensitive)."""
    dc = ctx.deps
    query_lower = query.lower()
    matches = [k for k in dc.embeddings.key_to_index if query_lower in k.lower()]
    return sorted(matches)[:limit]


def get_card_info(
    ctx: RunContext[ChatDeps],
    card_name: str,
) -> dict[str, Any]:
    """Get information about a specific card: attributes and co-occurrence stats."""
    dc = ctx.deps
    info: dict[str, Any] = {"name": card_name}

    if dc.card_attrs and card_name in dc.card_attrs:
        info["attributes"] = dc.card_attrs[card_name]

    neighbors = dc.graph.get(card_name, {})
    info["num_cooccurrence_partners"] = len(neighbors)
    if neighbors:
        top5 = sorted(neighbors.items(), key=lambda x: x[1], reverse=True)[:5]
        info["top_cooccurrence"] = [{"card": c, "weight": round(w, 4)} for c, w in top5]

    info["has_embedding"] = card_name in dc.embeddings
    return info


def analyze_deck(
    ctx: RunContext[ChatDeps],
    deck_cards: list[str],
) -> dict[str, Any]:
    """Analyze a deck's composition: internal synergy and co-occurrence coverage.

    Args:
        deck_cards: List of card names in the deck.
    """
    dc = ctx.deps
    analysis: dict[str, Any] = {
        "total_cards": len(deck_cards),
        "unique_cards": len(set(deck_cards)),
    }

    found = [c for c in deck_cards if c in dc.embeddings]
    missing = [c for c in deck_cards if c not in dc.embeddings]
    analysis["cards_with_embeddings"] = len(found)
    if missing:
        analysis["cards_not_found"] = missing[:10]

    if len(found) >= 2:
        sims = []
        for i, c1 in enumerate(found[:30]):
            for c2 in found[i + 1 : 30]:
                try:
                    sims.append(float(dc.embeddings.similarity(c1, c2)))
                except KeyError:
                    pass
        if sims:
            analysis["internal_synergy"] = {
                "mean": round(sum(sims) / len(sims), 4),
                "max": round(max(sims), 4),
                "min": round(min(sims), 4),
            }

    cooccur_pairs = 0
    for i, c1 in enumerate(deck_cards):
        for c2 in deck_cards[i + 1 :]:
            if c2 in dc.graph.get(c1, {}):
                cooccur_pairs += 1
    total_pairs = len(deck_cards) * (len(deck_cards) - 1) // 2
    analysis["cooccurrence_coverage"] = round(cooccur_pairs / total_pairs, 4) if total_pairs > 0 else 0

    return analysis


def suggest_additions(
    ctx: RunContext[ChatDeps],
    deck_cards: list[str],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Suggest cards to add to a deck based on aggregate synergy with existing cards.

    Args:
        deck_cards: List of card names currently in the deck.
        top_k: Number of suggestions.
    """
    dc = ctx.deps
    candidate_scores: dict[str, float] = defaultdict(float)
    candidate_sources: dict[str, int] = defaultdict(int)
    deck_set = set(deck_cards)

    for card in deck_cards:
        if card not in dc.embeddings:
            continue
        try:
            similar = dc.embeddings.most_similar(card, topn=30)
            for cand, score in similar:
                if cand not in deck_set:
                    candidate_scores[cand] += float(score)
                    candidate_sources[cand] += 1
        except KeyError:
            pass

    ranked = sorted(
        candidate_scores.items(),
        key=lambda x: x[1] * (1 + 0.2 * candidate_sources[x[0]]),
        reverse=True,
    )[:top_k]

    return [
        {"card": card, "synergy_score": round(score, 4), "synergizes_with": candidate_sources[card]}
        for card, score in ranked
    ]


def suggest_replacements(
    ctx: RunContext[ChatDeps],
    card_to_replace: str,
    deck_cards: list[str],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Suggest replacement cards for a specific card in a deck.

    Args:
        card_to_replace: Card to find replacements for.
        deck_cards: List of card names in the deck.
        top_k: Number of suggestions.
    """
    dc = ctx.deps
    deck_set = set(deck_cards) - {card_to_replace}

    if card_to_replace not in dc.embeddings:
        return [{"error": f"'{card_to_replace}' not found in embeddings"}]

    similar = dc.embeddings.most_similar(card_to_replace, topn=50)
    results = []
    for cand, sim_score in similar:
        if cand in deck_set or cand == card_to_replace:
            continue
        deck_sims = []
        for dc_card in list(deck_set)[:20]:
            if dc_card in dc.embeddings:
                try:
                    deck_sims.append(float(dc.embeddings.similarity(cand, dc_card)))
                except KeyError:
                    pass
        avg_deck_sim = sum(deck_sims) / len(deck_sims) if deck_sims else 0
        combined = 0.6 * float(sim_score) + 0.4 * avg_deck_sim
        results.append({
            "card": cand,
            "similarity": round(float(sim_score), 4),
            "deck_synergy": round(avg_deck_sim, 4),
            "combined": round(combined, 4),
        })
        if len(results) >= top_k:
            break

    results.sort(key=lambda x: x["combined"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are DeckSage, an expert trading card game assistant.

You help players with:
- Finding similar cards (substitutes, synergies, alternatives)
- Building and improving decks
- Understanding card interactions and strategy
- Exploring the card pool

RULES:
1. Always use your tools to look up cards before making claims. Do not guess card names or effects.
2. When a user mentions a card, use search_cards_by_name first if unsure of the exact name.
3. For deck advice, use analyze_deck to understand the deck before suggesting changes.
4. Explain your reasoning -- why a card fits, what role it fills, how it synergizes.
5. Be honest about limitations: if a card isn't in your data, say so.
6. Keep responses focused and actionable. Avoid generic advice.

GAME CONTEXT:
You are assisting with: {game}

When suggesting cards:
- Consider both embedding similarity (functional similarity) and co-occurrence (tournament-proven combinations)
- High co-occurrence + low embedding similarity = synergy/combo relationship
- High embedding similarity + low co-occurrence = untested but functionally similar option
"""


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def _build_agent(game: str) -> Agent:
    provider = os.getenv("LLM_PROVIDER", "openrouter")
    model_name = os.getenv("CHAT_MODEL", os.getenv("DEFAULT_LLM_MODEL", "anthropic/claude-sonnet-4.5"))
    model_id = f"{provider}:{model_name}"

    tools = [
        Tool(find_similar_cards),
        Tool(search_cards_by_name),
        Tool(get_card_info),
        Tool(analyze_deck),
        Tool(suggest_additions),
        Tool(suggest_replacements),
    ]

    return Agent(
        model_id,
        deps_type=ChatDeps,
        system_prompt=SYSTEM_PROMPT.format(game=game),
        tools=tools,
        model_settings=ModelSettings(temperature=0.4, max_tokens=2000),
    )


# Cache one agent per game (they differ only in system prompt)
_agents: dict[str, Agent] = {}


def _get_agent(game: str) -> Agent:
    if game not in _agents:
        _agents[game] = _build_agent(game)
    return _agents[game]


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@chat_router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    """Stream a chat response with tool calls via SSE."""
    if not HAS_PYDANTIC_AI:
        raise HTTPException(status_code=501, detail="pydantic-ai not installed")

    # Resolve game state
    game = req.game.lower().strip()
    if game not in {"magic", "pokemon", "yugioh"}:
        raise HTTPException(status_code=400, detail=f"Unknown game: {req.game}")

    api_by_game = getattr(request.app.state, "api_by_game", {})
    api_state = api_by_game.get(game)
    if not api_state or not api_state.embeddings:
        raise HTTPException(status_code=503, detail=f"Game '{game}' not loaded")

    # Build deps
    deps = ChatDeps(
        game=game,
        embeddings=api_state.embeddings,
        graph=api_state.graph_data or {},
        card_attrs=api_state.card_attrs,
    )

    # Parse deck if provided
    if req.deck:
        deck_cards: dict[str, int] = {}
        partitions = req.deck.get("partitions", [])
        if partitions:
            for p in partitions:
                for card in p.get("cards", []):
                    name = card.get("name", "")
                    count = card.get("count", 1)
                    if name:
                        deck_cards[name] = deck_cards.get(name, 0) + count
        else:
            # Legacy format: {"Main": ["card1", ...]}
            for section_cards in req.deck.values():
                if isinstance(section_cards, list):
                    for c in section_cards:
                        if isinstance(c, str):
                            deck_cards[c] = deck_cards.get(c, 0) + 1
        deps.deck = deck_cards or None

    # Session
    sess = _get_or_create_session(req.session_id, game, req.deck)

    # Restore message history
    message_history: list[ModelMessage] = []
    for msg_bytes in sess.messages_json:
        message_history.extend(ModelMessagesTypeAdapter.validate_json(msg_bytes))

    agent = _get_agent(game)

    async def event_stream():
        try:
            # Emit session ID
            yield _sse_event({"type": "session", "session_id": sess.session_id})

            async with agent.run_stream(
                req.message,
                deps=deps,
                message_history=message_history,
            ) as result:
                async for text in result.stream_output(debounce_by=0.01):
                    yield _sse_event({"type": "token", "content": text})

            # Persist new messages to session
            sess.messages_json.append(result.new_messages_json())

            yield _sse_event({"type": "done", "session_id": sess.session_id})

        except Exception as e:
            logger.exception("Chat stream error")
            yield _sse_event({"type": "error", "content": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
