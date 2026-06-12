#!/usr/bin/env python3
"""End-to-end tests for deck_assistant tool logic (no LLM calls).

Tests each tool function by directly invoking the underlying logic
with real YGO embeddings and co-occurrence data.

Usage:
  PYTHONPATH=src .venv/bin/python scripts/test_deck_assistant.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Setup paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
EMBEDDINGS_PATH = ROOT / "data" / "embeddings" / "yugioh_cmp_pecanpy.wv"
PAIRS_PATH = ROOT / "data" / "processed" / "pairs_yugioh_ygoprodeck-tournament.csv"

# Import from deck_assistant
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from deck_assistant import DeckContext, load_graph
from gensim.models import KeyedVectors


# ---------------------------------------------------------------------------
# Fake RunContext that just exposes .deps
# ---------------------------------------------------------------------------


class FakeRunContext:
    """Minimal stand-in for pydantic_ai.RunContext[DeckContext]."""

    def __init__(self, deps: DeckContext):
        self.deps = deps


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        msg = f"  FAIL  {name}"
        if detail:
            msg += f"  -- {detail}"
        print(msg)


# ---------------------------------------------------------------------------
# Load data once
# ---------------------------------------------------------------------------

print("Loading embeddings...")
t0 = time.time()
wv = KeyedVectors.load(str(EMBEDDINGS_PATH))
print(f"  {len(wv.key_to_index)} cards in {time.time() - t0:.1f}s")

print("Loading co-occurrence graph...")
t0 = time.time()
graph = load_graph(PAIRS_PATH)
print(f"  {len(graph)} cards in {time.time() - t0:.1f}s")

dc = DeckContext(game="yugioh", embeddings=wv, graph=graph)
ctx = FakeRunContext(dc)

# Pick some known cards for testing
all_cards = list(wv.key_to_index.keys())
card_a = all_cards[0]
card_b = all_cards[1]
card_c = all_cards[2]
print(f"\nTest cards: {card_a!r}, {card_b!r}, {card_c!r}\n")

# ---------------------------------------------------------------------------
# Import tool functions
# ---------------------------------------------------------------------------

from deck_assistant import (
    analyze_deck,
    find_similar_cards,
    get_card_info,
    search_cards_by_name,
    suggest_additions,
    suggest_replacements,
)


# ===========================================================================
# Test 1: find_similar_cards (embedding)
# ===========================================================================

print("[1] find_similar_cards -- embedding method")
results = find_similar_cards(ctx, card_a, top_k=5, method="embedding")
check("returns list", isinstance(results, list))
check("returns 5 results", len(results) == 5, f"got {len(results)}")
check(
    "each has card+score+source",
    all("card" in r and "score" in r and "source" in r for r in results),
)
check("scores in (0,1]", all(0 < r["score"] <= 1.0 for r in results))
check("source is embedding", all(r["source"] == "embedding" for r in results))
check("does not include query card", all(r["card"] != card_a for r in results))

# Test fuzzy match: use partial name
partial = card_a[:5].lower()
results_fuzzy = find_similar_cards(ctx, partial, top_k=3, method="embedding")
if results_fuzzy and "error" not in results_fuzzy[0]:
    check("fuzzy match works", len(results_fuzzy) > 0)
else:
    # Partial name might be too short to match; not a failure of logic
    check("fuzzy match returns error for ambiguous partial", "error" in results_fuzzy[0])

# Test not-found
results_bad = find_similar_cards(ctx, "ZZZZNONEXISTENT999", top_k=3, method="embedding")
check("not-found returns error", len(results_bad) == 1 and "error" in results_bad[0])

# ===========================================================================
# Test 2: find_similar_cards (cooccurrence)
# ===========================================================================

print("\n[2] find_similar_cards -- cooccurrence method")
# Find a card that exists in both embeddings and graph
graph_cards = [c for c in all_cards[:100] if c in graph]
if graph_cards:
    gc = graph_cards[0]
    results_co = find_similar_cards(ctx, gc, top_k=5, method="cooccurrence")
    check("returns list", isinstance(results_co, list))
    check("returns <= 5 results", 0 < len(results_co) <= 5, f"got {len(results_co)}")
    check("source is cooccurrence", all(r["source"] == "cooccurrence" for r in results_co))
    check("scores > 0", all(r["score"] > 0 for r in results_co))
    check(
        "sorted descending",
        all(
            results_co[i]["score"] >= results_co[i + 1]["score"] for i in range(len(results_co) - 1)
        ),
    )
else:
    print("  SKIP  no cards in both embeddings and graph (first 100)")

# ===========================================================================
# Test 3: search_cards_by_name
# ===========================================================================

print("\n[3] search_cards_by_name")
# Use a common YGO substring
results_search = search_cards_by_name(ctx, "dragon", limit=10)
check("returns list", isinstance(results_search, list))
check("non-empty", len(results_search) > 0, f"got {len(results_search)}")
check("<= 10 results", len(results_search) <= 10)
check("all contain 'dragon' (case-insensitive)", all("dragon" in c.lower() for c in results_search))
check("sorted alphabetically", results_search == sorted(results_search))

# Edge case: empty query matches all (just check bounded)
results_empty = search_cards_by_name(ctx, "", limit=5)
check("empty query returns cards (up to limit)", len(results_empty) == 5)

# ===========================================================================
# Test 4: get_card_info
# ===========================================================================

print("\n[4] get_card_info")
info = get_card_info(ctx, card_a)
check("returns dict", isinstance(info, dict))
check("has name", info.get("name") == card_a)
check("has has_embedding=True", info.get("has_embedding") is True)
check("has num_cooccurrence_partners", "num_cooccurrence_partners" in info)
check("has attributes field", "attributes" in info)

# Card in graph should have top_cooccurrence
if card_a in graph:
    check("has top_cooccurrence", "top_cooccurrence" in info)
    check("top_cooccurrence is list", isinstance(info.get("top_cooccurrence"), list))

# Unknown card
info_unk = get_card_info(ctx, "ZZZZNONEXISTENT999")
check("unknown card has_embedding=False", info_unk.get("has_embedding") is False)
check("unknown card attrs='not available'", info_unk.get("attributes") == "not available")

# ===========================================================================
# Test 5: analyze_deck
# ===========================================================================

print("\n[5] analyze_deck")
# Build a small test deck from known cards
deck_cards = all_cards[:10]
analysis = analyze_deck(ctx, deck_cards)
check("returns dict", isinstance(analysis, dict))
check("total_cards=10", analysis.get("total_cards") == 10)
check("unique_cards=10", analysis.get("unique_cards") == 10)
check("cards_with_embeddings=10", analysis.get("cards_with_embeddings") == 10)
check("has internal_synergy", "internal_synergy" in analysis)
syn = analysis.get("internal_synergy", {})
check(
    "synergy has mean/max/min",
    all(k in syn for k in ("mean_similarity", "max_similarity", "min_similarity")),
)
check("mean in [-1,1]", -1 <= syn.get("mean_similarity", 99) <= 1)
check("has cooccurrence_coverage", "cooccurrence_coverage" in analysis)
cov = analysis.get("cooccurrence_coverage", {})
check("coverage_ratio in [0,1]", 0 <= cov.get("coverage_ratio", -1) <= 1)

# Deck with unknown cards
analysis2 = analyze_deck(ctx, ["ZZZZFAKE1", "ZZZZFAKE2"])
check("unknown deck: cards_with_embeddings=0", analysis2.get("cards_with_embeddings") == 0)
check("unknown deck: cards_not_found present", "cards_not_found" in analysis2)

# ===========================================================================
# Test 6: suggest_additions
# ===========================================================================

print("\n[6] suggest_additions")
suggestions = suggest_additions(ctx, deck_cards[:5], top_k=8)
check("returns list", isinstance(suggestions, list))
check("non-empty", len(suggestions) > 0, f"got {len(suggestions)}")
check("<= 8 results", len(suggestions) <= 8)
check(
    "each has card+synergy_score+synergizes_with_n_cards",
    all(
        "card" in s and "synergy_score" in s and "synergizes_with_n_cards" in s for s in suggestions
    ),
)
check(
    "no suggestions already in deck", all(s["card"] not in set(deck_cards[:5]) for s in suggestions)
)
check("synergy_score > 0", all(s["synergy_score"] > 0 for s in suggestions))
check("synergizes_with >= 1", all(s["synergizes_with_n_cards"] >= 1 for s in suggestions))

# ===========================================================================
# Test 7: suggest_replacements
# ===========================================================================

print("\n[7] suggest_replacements")
replacements = suggest_replacements(ctx, deck_cards[0], deck_cards[:5], top_k=5)
check("returns list", isinstance(replacements, list))
check("non-empty", len(replacements) > 0, f"got {len(replacements)}")
check("<= 5 results", len(replacements) <= 5)
check(
    "each has card+similarity_to_replaced+avg_deck_synergy+combined_score",
    all(
        all(
            k in r for k in ("card", "similarity_to_replaced", "avg_deck_synergy", "combined_score")
        )
        for r in replacements
    ),
)
check("no replacement is the replaced card", all(r["card"] != deck_cards[0] for r in replacements))
check(
    "no replacement already in deck",
    all(r["card"] not in set(deck_cards[:5]) for r in replacements),
)

# Not-found card
repl_bad = suggest_replacements(ctx, "ZZZZNONEXISTENT999", deck_cards[:5], top_k=3)
check("not-found returns error", len(repl_bad) == 1 and "error" in repl_bad[0])

# ===========================================================================
# Summary
# ===========================================================================

print(f"\n{'=' * 60}")
print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
print(f"{'=' * 60}")

sys.exit(1 if failed > 0 else 0)
