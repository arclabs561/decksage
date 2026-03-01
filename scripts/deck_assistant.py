#!/usr/bin/env python3
"""Interactive deck assistant agent powered by pydantic-ai.

Provides a conversational interface for deck building, card exploration,
and strategic advice using DeckSage's similarity search and deck tools.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/deck_assistant.py \
    --game yugioh \
    --embeddings data/processed/yugioh.wv \
    --pairs data/processed/pairs_yugioh_ygoprodeck-tournament.csv

  # With card attributes:
  PYTHONPATH=src .venv/bin/python scripts/deck_assistant.py \
    --game magic \
    --embeddings data/processed/magic.wv \
    --pairs data/processed/pairs_large.edg \
    --attrs data/processed/magic_attrs.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import readline  # noqa: F401 — enables arrow keys / history in input()
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from pydantic_ai import Agent, ModelSettings, RunContext, Tool
except ImportError:
    print("Error: pydantic-ai required. Install with: uv add pydantic-ai")
    sys.exit(1)

try:
    from gensim.models import KeyedVectors
except ImportError:
    print("Error: gensim required. Install with: uv add gensim")
    sys.exit(1)

from ml.utils.data_loading import load_graph_adjacency


# ---------------------------------------------------------------------------
# Data context (injected into agent via deps)
# ---------------------------------------------------------------------------

class DeckContext:
    """Holds loaded game data for tool access."""

    def __init__(
        self,
        game: str,
        embeddings: KeyedVectors,
        graph: dict[str, dict[str, float]],
        card_attrs: dict[str, dict] | None = None,
    ):
        self.game = game
        self.embeddings = embeddings
        self.graph = graph  # adjacency: card -> {neighbor: weight}
        self.card_attrs = card_attrs or {}
        self.deck: dict[str, int] | None = None  # card -> count (user's current deck)
        self.banned_cards: set[str] = set()  # cards banned in current format
        self.format_name: str | None = None
        # Card sets (hyperedges): card -> list of sets containing it
        self.card_sets_index: dict[str, list[dict]] = defaultdict(list)
        self.card_sets: list[dict] = []

    def set_deck(self, deck: dict[str, int]):
        self.deck = deck

    def set_banlist(self, banned: set[str], format_name: str):
        self.banned_cards = banned
        self.format_name = format_name

    def load_card_sets(self, path: Path):
        """Load card sets from JSONL and build reverse index."""
        with open(path) as f:
            for line in f:
                data = json.loads(line)
                if data.get("_meta"):
                    continue
                self.card_sets.append(data)
                for card in data["cards"]:
                    self.card_sets_index[card].append(data)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def find_similar_cards(
    ctx: RunContext[DeckContext],
    card_name: str,
    top_k: int = 10,
    method: str = "embedding",
) -> list[dict[str, Any]]:
    """Find cards similar to a given card.

    Args:
        card_name: The card to find similar cards for.
        top_k: Number of results to return (default 10).
        method: "embedding" (vector similarity) or "cooccurrence" (tournament co-play).
    """
    dc = ctx.deps

    if method == "cooccurrence":
        neighbors = dc.graph.get(card_name, {})
        if not neighbors:
            return [{"error": f"'{card_name}' not found in co-occurrence graph"}]
        sorted_n = sorted(neighbors.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [{"card": c, "score": round(w, 4), "source": "cooccurrence"} for c, w in sorted_n]

    # Embedding similarity (default)
    if card_name not in dc.embeddings:
        # Fuzzy match attempt
        candidates = [k for k in dc.embeddings.key_to_index if card_name.lower() in k.lower()]
        if candidates:
            card_name = candidates[0]
        else:
            return [{"error": f"'{card_name}' not found in embeddings. Try a different spelling."}]

    # Fetch extra results to account for banned card filtering
    fetch_k = top_k * 2 if dc.banned_cards else top_k
    results = dc.embeddings.most_similar(card_name, topn=fetch_k)
    out = []
    for card, score in results:
        entry = {"card": card, "score": round(float(score), 4), "source": "embedding"}
        if card in dc.banned_cards:
            entry["banned"] = True
        if card in dc.card_attrs:
            attrs = dc.card_attrs[card]
            if "type" in attrs:
                entry["type"] = attrs["type"]
        out.append(entry)
        if len(out) >= top_k:
            break
    return out


def search_cards_by_name(
    ctx: RunContext[DeckContext],
    query: str,
    limit: int = 10,
) -> list[str]:
    """Search for card names containing the query string (case-insensitive).

    Useful when the user mentions a card but you're not sure of the exact name.
    """
    dc = ctx.deps
    query_lower = query.lower()
    matches = [k for k in dc.embeddings.key_to_index if query_lower in k.lower()]
    return sorted(matches)[:limit]


def get_card_info(
    ctx: RunContext[DeckContext],
    card_name: str,
) -> dict[str, Any]:
    """Get detailed information about a specific card.

    Returns attributes (type, cost, color, etc.) and co-occurrence stats.
    """
    dc = ctx.deps
    info: dict[str, Any] = {"name": card_name}

    # Attributes
    if card_name in dc.card_attrs:
        info["attributes"] = dc.card_attrs[card_name]
    else:
        info["attributes"] = "not available"

    # Co-occurrence stats
    neighbors = dc.graph.get(card_name, {})
    info["num_cooccurrence_partners"] = len(neighbors)
    if neighbors:
        top5 = sorted(neighbors.items(), key=lambda x: x[1], reverse=True)[:5]
        info["top_cooccurrence"] = [{"card": c, "weight": round(w, 4)} for c, w in top5]

    # Embedding presence
    info["has_embedding"] = card_name in dc.embeddings

    return info


def check_card_legality(
    ctx: RunContext[DeckContext],
    card_names: list[str],
) -> dict[str, Any]:
    """Check whether cards are legal or banned in the current format.

    Args:
        card_names: List of card names to check.
    """
    dc = ctx.deps
    if not dc.banned_cards:
        return {"format": dc.format_name or "unknown", "note": "No ban list loaded", "all_legal": True}

    results = {}
    for card in card_names:
        results[card] = "BANNED" if card in dc.banned_cards else "legal"

    banned_count = sum(1 for s in results.values() if s == "BANNED")
    return {
        "format": dc.format_name,
        "cards_checked": len(card_names),
        "banned_count": banned_count,
        "results": results,
    }


def analyze_deck(
    ctx: RunContext[DeckContext],
    deck_cards: list[str],
) -> dict[str, Any]:
    """Analyze a deck's composition and suggest improvements.

    Args:
        deck_cards: List of card names in the deck.
    """
    dc = ctx.deps
    dc.set_deck(dict.fromkeys(deck_cards, 1))

    analysis: dict[str, Any] = {
        "total_cards": len(deck_cards),
        "unique_cards": len(set(deck_cards)),
    }

    # Check which cards have embeddings
    found = [c for c in deck_cards if c in dc.embeddings]
    missing = [c for c in deck_cards if c not in dc.embeddings]
    analysis["cards_with_embeddings"] = len(found)
    if missing:
        analysis["cards_not_found"] = missing[:10]

    # Internal synergy: average pairwise similarity within deck
    if len(found) >= 2:
        sims = []
        pairs_checked = 0
        for i, c1 in enumerate(found[:30]):  # cap at 30 for speed
            for c2 in found[i + 1 : 30]:
                try:
                    sim = float(dc.embeddings.similarity(c1, c2))
                    sims.append(sim)
                    pairs_checked += 1
                except KeyError:
                    pass
        if sims:
            analysis["internal_synergy"] = {
                "mean_similarity": round(sum(sims) / len(sims), 4),
                "max_similarity": round(max(sims), 4),
                "min_similarity": round(min(sims), 4),
                "pairs_checked": pairs_checked,
            }

    # Co-occurrence coverage: how many deck cards co-occur with each other
    cooccur_pairs = 0
    for i, c1 in enumerate(deck_cards):
        for c2 in deck_cards[i + 1 :]:
            if c2 in dc.graph.get(c1, {}):
                cooccur_pairs += 1
    total_pairs = len(deck_cards) * (len(deck_cards) - 1) // 2
    analysis["cooccurrence_coverage"] = {
        "pairs_with_cooccurrence": cooccur_pairs,
        "total_pairs": total_pairs,
        "coverage_ratio": round(cooccur_pairs / total_pairs, 4) if total_pairs > 0 else 0,
    }

    return analysis


def suggest_additions(
    ctx: RunContext[DeckContext],
    deck_cards: list[str],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Suggest cards to add to a deck based on synergy with existing cards.

    Finds cards that are similar to multiple cards in the deck (high aggregate synergy).
    """
    dc = ctx.deps

    # Score candidates by aggregate similarity to deck cards
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

    # Sort by aggregate score, prefer cards synergistic with multiple deck cards
    ranked = sorted(
        candidate_scores.items(),
        key=lambda x: x[1] * (1 + 0.2 * candidate_sources[x[0]]),
        reverse=True,
    )[:top_k]

    results = []
    for card, score in ranked:
        entry = {
            "card": card,
            "synergy_score": round(score, 4),
            "synergizes_with_n_cards": candidate_sources[card],
        }
        if card in dc.card_attrs and "type" in dc.card_attrs[card]:
            entry["type"] = dc.card_attrs[card]["type"]
        results.append(entry)

    return results


def suggest_replacements(
    ctx: RunContext[DeckContext],
    card_to_replace: str,
    deck_cards: list[str],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Suggest replacement cards for a specific card in a deck.

    Finds cards similar to the card being replaced that also synergize with the deck.
    """
    dc = ctx.deps
    deck_set = set(deck_cards) - {card_to_replace}

    if card_to_replace not in dc.embeddings:
        return [{"error": f"'{card_to_replace}' not found in embeddings"}]

    # Get cards similar to the one being replaced
    similar = dc.embeddings.most_similar(card_to_replace, topn=50)

    results = []
    for cand, sim_score in similar:
        if cand in deck_set or cand == card_to_replace:
            continue

        # Score: similarity to replaced card + avg similarity to rest of deck
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
            "similarity_to_replaced": round(float(sim_score), 4),
            "avg_deck_synergy": round(avg_deck_sim, 4),
            "combined_score": round(combined, 4),
        })

        if len(results) >= top_k:
            break

    results.sort(key=lambda x: x["combined_score"], reverse=True)
    return results


def find_card_packages(
    ctx: RunContext[DeckContext],
    card_name: str,
    min_size: int = 3,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Find card packages (combos/synergy groups) containing a specific card.

    Returns groups of 3+ cards that frequently appear together in tournament decks,
    ordered by lift (statistical significance of co-occurrence).

    Args:
        card_name: The card to find packages for.
        min_size: Minimum package size (default 3).
        top_k: Maximum number of packages to return (default 5).
    """
    dc = ctx.deps
    if not dc.card_sets_index:
        return [{"error": "No card set data loaded. Run with --card-sets to enable package search."}]

    # Find sets containing this card
    sets = dc.card_sets_index.get(card_name, [])
    if not sets:
        # Try fuzzy match
        card_lower = card_name.lower()
        for key in dc.card_sets_index:
            if card_lower in key.lower():
                sets = dc.card_sets_index[key]
                card_name = key
                break
        if not sets:
            return [{"error": f"No packages found containing '{card_name}'."}]

    # Filter by min_size and sort by lift
    filtered = [s for s in sets if s["size"] >= min_size]
    filtered.sort(key=lambda x: (-x["size"], -x["lift"]))

    results = []
    for s in filtered[:top_k]:
        other_cards = [c for c in s["cards"] if c != card_name]
        results.append({
            "package": s["cards"],
            "other_cards": other_cards,
            "size": s["size"],
            "support": s["support"],
            "support_pct": s.get("support_pct", 0),
            "lift": s["lift"],
        })

    return results


def find_deck_packages(
    ctx: RunContext[DeckContext],
    deck_cards: list[str],
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Find card packages that overlap with the user's deck.

    Identifies known synergy groups where some cards are already in the deck,
    suggesting completing the package by adding the missing cards.

    Args:
        deck_cards: List of card names in the deck.
        top_k: Maximum number of packages to return.
    """
    dc = ctx.deps
    if not dc.card_sets_index:
        return [{"error": "No card set data loaded."}]

    deck_set = set(deck_cards)
    scored: list[tuple[float, dict]] = []

    # Find all sets that overlap with the deck
    seen: set[tuple[str, ...]] = set()
    for card in deck_cards:
        for card_set in dc.card_sets_index.get(card, []):
            key = tuple(card_set["cards"])
            if key in seen:
                continue
            seen.add(key)

            set_cards = set(card_set["cards"])
            overlap = set_cards & deck_set
            missing = set_cards - deck_set

            if not missing:
                continue  # Already have all cards
            if len(overlap) < 2:
                continue  # Need at least 2 cards in deck to suggest completing

            # Score: more overlap + higher lift = better suggestion
            score = len(overlap) / len(set_cards) * card_set["lift"]
            scored.append((score, {
                "package": card_set["cards"],
                "cards_in_deck": sorted(overlap),
                "cards_to_add": sorted(missing),
                "overlap": len(overlap),
                "size": card_set["size"],
                "lift": card_set["lift"],
                "support": card_set["support"],
            }))

    scored.sort(key=lambda x: -x[0])
    return [item for _, item in scored[:top_k]]


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
You are assisting with the game: {game}

If a format filter is active, always check card legality before recommending cards.
Warn the user if their deck contains banned cards.

When suggesting cards:
- Consider both embedding similarity (functional similarity) and co-occurrence (tournament-proven combinations)
- A card with high co-occurrence but low embedding similarity suggests a synergy/combo relationship
- A card with high embedding similarity but low co-occurrence suggests an untested but functionally similar option
- When card packages are available, use find_card_packages to discover multi-card combos and engines
- Use find_deck_packages to identify incomplete packages in the user's deck -- suggest adding the missing pieces
"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_graph(pairs_path: Path) -> dict[str, dict[str, float]]:
    """Load co-occurrence graph from edgelist/CSV."""
    return load_graph_adjacency(pairs_path)


def load_attrs(attrs_path: Path) -> dict[str, dict]:
    """Load card attributes from CSV or JSON."""
    if attrs_path.suffix == ".json":
        with open(attrs_path) as f:
            return json.load(f)

    attrs: dict[str, dict] = {}
    with open(attrs_path) as f:
        reader = csv.DictReader(f)
        name_col = next((c for c in reader.fieldnames or [] if c.lower() == "name"), None)
        if not name_col:
            return attrs
        for row in reader:
            name = row.pop(name_col)
            attrs[name] = dict(row)
    return attrs


# ---------------------------------------------------------------------------
# REPL
# ---------------------------------------------------------------------------

async def chat_loop(agent: Agent, dc: DeckContext):
    """Interactive chat loop."""
    from pydantic_ai import ModelMessage

    print(f"\nDeckSage Assistant ({dc.game})")
    print(f"  {len(dc.embeddings.key_to_index)} cards in embeddings")
    print(f"  {len(dc.graph)} cards in co-occurrence graph")
    if dc.card_attrs:
        print(f"  {len(dc.card_attrs)} cards with attributes")
    print("\nType your question (or 'quit' to exit):\n")

    message_history: list[ModelMessage] = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        # Special commands
        if user_input.lower().startswith("/deck "):
            # Load a deck from card names
            cards = [c.strip() for c in user_input[6:].split(",") if c.strip()]
            dc.set_deck(dict.fromkeys(cards, 1))
            print(f"Deck loaded: {len(cards)} cards")
            continue

        if user_input.lower() == "/deck":
            if dc.deck:
                print(f"Current deck ({sum(dc.deck.values())} cards):")
                for card, count in sorted(dc.deck.items()):
                    print(f"  {count}x {card}")
            else:
                print("No deck loaded. Use /deck Card1, Card2, ... to load one.")
            continue

        try:
            result = await agent.run(
                user_input,
                deps=dc,
                message_history=message_history,
            )
            print(f"\nDeckSage: {result.output}\n")
            message_history = result.all_messages()
        except Exception as e:
            print(f"\nError: {e}\n")


def main():
    parser = argparse.ArgumentParser(description="DeckSage deck assistant agent")
    parser.add_argument("--game", required=True, choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--embeddings", type=Path, required=True, help="Path to .wv embeddings")
    parser.add_argument("--pairs", type=Path, required=True, help="Path to pairs edgelist/CSV")
    parser.add_argument("--attrs", type=Path, help="Path to card attributes CSV/JSON")
    parser.add_argument("--model", default=None, help="LLM model (default: from env or claude-sonnet-4.5)")
    parser.add_argument("--card-sets", type=Path, default=None,
                        help="Path to card sets JSONL (from extract_card_sets_fast.py)")
    parser.add_argument("--format", type=str, default=None,
                        help="Game format for ban list filtering (e.g., 'modern', 'tcg')")
    parser.add_argument("--banlist", type=Path, default=None,
                        help="Path to ban list JSON (auto-detected if not specified)")
    args = parser.parse_args()

    # Validate paths
    for path_arg, label in [(args.embeddings, "embeddings"), (args.pairs, "pairs")]:
        if not path_arg.exists():
            print(f"Error: {label} file not found: {path_arg}")
            return 1

    # Load data
    print(f"Loading embeddings from {args.embeddings}...")
    embeddings = KeyedVectors.load(str(args.embeddings))

    print(f"Loading co-occurrence graph from {args.pairs}...")
    graph = load_graph(args.pairs)

    card_attrs = None
    if args.attrs and args.attrs.exists():
        print(f"Loading card attributes from {args.attrs}...")
        card_attrs = load_attrs(args.attrs)

    dc = DeckContext(
        game=args.game,
        embeddings=embeddings,
        graph=graph,
        card_attrs=card_attrs,
    )

    # Load card sets if provided
    card_sets_path = args.card_sets
    if not card_sets_path:
        # Auto-detect
        auto_path = Path(f"data/processed/card_sets_{args.game}.jsonl")
        if auto_path.exists():
            card_sets_path = auto_path
    if card_sets_path and card_sets_path.exists():
        print(f"Loading card sets from {card_sets_path}...")
        dc.load_card_sets(card_sets_path)
        print(f"  {len(dc.card_sets)} card sets, {len(dc.card_sets_index)} cards indexed")

    # Load ban list if format specified
    if args.format:
        try:
            from ml.utils.banlist_filter import BanlistFilter
            bl_path = args.banlist or Path(f"data/banlists/{args.game}_banlists.json")
            if bl_path.exists():
                bf = BanlistFilter.load(args.game, bl_path)
                banned = bf.banned_by_format.get(args.format, set())
                dc.set_banlist(banned, args.format)
                print(f"Ban list loaded: {len(banned)} cards banned in {args.format}")
            else:
                print(f"Warning: ban list not found at {bl_path}")
        except ImportError:
            print("Warning: ml.utils.banlist_filter not available, skipping ban list")

    # Create agent
    provider = os.getenv("LLM_PROVIDER", "openrouter")
    model_name = args.model or os.getenv("DEFAULT_LLM_MODEL", "anthropic/claude-sonnet-4.5")
    model_id = f"{provider}:{model_name}"

    print(f"Using model: {model_id}")

    tools = [
        Tool(find_similar_cards),
        Tool(search_cards_by_name),
        Tool(get_card_info),
        Tool(check_card_legality),
        Tool(analyze_deck),
        Tool(suggest_additions),
        Tool(suggest_replacements),
    ]
    if dc.card_sets:
        tools.extend([
            Tool(find_card_packages),
            Tool(find_deck_packages),
        ])

    agent = Agent(
        model_id,
        deps_type=DeckContext,
        system_prompt=SYSTEM_PROMPT.format(game=args.game),
        tools=tools,
        model_settings=ModelSettings(temperature=0.4, max_tokens=2000),
    )

    import asyncio
    asyncio.run(chat_loop(agent, dc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
