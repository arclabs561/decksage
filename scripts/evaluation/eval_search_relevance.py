#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.25.0",
# ]
# ///
"""
Search relevance evaluation for DeckSage.

Generates natural-language search queries with ground-truth relevant cards,
then scores the API's search results against that ground truth.

Two evaluation modes:
1. Oracle text matching: queries derived from card text (e.g., "destroy all
   creatures" should return Day of Judgment). This tests MeiliSearch quality.
2. Semantic queries: conceptual queries (e.g., "cheap red burn spells")
   with hand-curated relevant sets. This tests hybrid search quality.

Outputs: precision@K, recall@K, nDCG@K, and MRR for each query.

Usage:
    uv run scripts/evaluation/eval_search_relevance.py --game magic
    uv run scripts/evaluation/eval_search_relevance.py --game magic --api-url http://localhost:8001
    uv run scripts/evaluation/eval_search_relevance.py --generate-only  # just create the test set
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TEST_SETS_DIR = DATA_DIR / "test_sets"

# Hand-curated search relevance queries with ground truth.
# Each query has:
# - query: the search string a user would type
# - relevant: cards that SHOULD appear in results (order = ideal ranking)
# - game: which game
# - type: "oracle" (text derived from card text) or "semantic" (conceptual)
SEARCH_QUERIES = {
    "magic": [
        {
            "query": "destroy all creatures",
            "relevant": [
                "Day of Judgment",
                "Wrath of God",
                "Damnation",
                "Blasphemous Act",
                "Toxic Deluge",
                "Terminus",
                "Devastation",
                "Life's Finale",
                "Plague Wind",
                "Fell the Mighty",
            ],
            "type": "oracle",
        },
        {
            "query": "draw two cards",
            "relevant": [
                "Divination",
                "Night's Whisper",
                "Sign in Blood",
                "Chart a Course",
                "Expressive Iteration",
                "Preordain",
                "Think Twice",
            ],
            "type": "oracle",
        },
        {
            "query": "counter target spell",
            "relevant": [
                "Counterspell",
                "Negate",
                "Mana Leak",
                "Force of Will",
                "Arcane Denial",
                "Swan Song",
                "Spell Pierce",
                "Dovin's Veto",
            ],
            "type": "oracle",
        },
        {
            "query": "cheap red burn spells",
            "relevant": [
                "Lightning Bolt",
                "Shock",
                "Chain Lightning",
                "Lava Spike",
                "Rift Bolt",
                "Searing Blaze",
                "Goblin Guide",
                "Monastery Swiftspear",
            ],
            "type": "semantic",
        },
        {
            "query": "mana ramp green",
            "relevant": [
                "Llanowar Elves",
                "Birds of Paradise",
                "Rampant Growth",
                "Cultivate",
                "Kodama's Reach",
                "Sol Ring",
                "Elvish Mystic",
            ],
            "type": "semantic",
        },
        {
            "query": "graveyard recursion",
            "relevant": [
                "Reanimate",
                "Animate Dead",
                "Living Death",
                "Unburial Rites",
                "Persist",
                "Eternal Witness",
                "Sun Titan",
            ],
            "type": "semantic",
        },
        {
            "query": "flying creatures blue",
            "relevant": [
                "Mulldrifter",
                "Brazen Borrower",
                "Sprite Dragon",
                "Vendilion Clique",
                "Consecrated Sphinx",
                "Dream Trawler",
            ],
            "type": "semantic",
        },
        {
            "query": "artifact removal white",
            "relevant": [
                "Disenchant",
                "Oblivion Ring",
                "Vindicate",
                "Fracture",
                "Stony Silence",
                "Seal of Cleansing",
                "Return to Dust",
            ],
            "type": "semantic",
        },
    ],
    "pokemon": [
        {
            "query": "search deck for pokemon",
            "relevant": [
                "Ultra Ball",
                "Nest Ball",
                "Quick Ball",
                "Level Ball",
                "Timer Ball",
                "Great Ball",
            ],
            "type": "oracle",
        },
        {
            "query": "draw cards supporter",
            "relevant": [
                "Professor's Research",
                "Iono",
                "Cynthia",
                "Professor Sycamore",
                "N",
                "Marnie",
            ],
            "type": "semantic",
        },
        {
            "query": "switch active pokemon",
            "relevant": [
                "Switch",
                "Escape Rope",
                "Boss's Orders",
                "Gust of Wind",
                "Air Balloon",
            ],
            "type": "oracle",
        },
    ],
    "yugioh": [
        {
            "query": "negate monster effect",
            "relevant": [
                "Ash Blossom & Joyous Spring",
                "Effect Veiler",
                "Infinite Impermanence",
                "Solemn Strike",
                "Breakthrough Skill",
            ],
            "type": "oracle",
        },
        {
            "query": "destroy spell trap",
            "relevant": [
                "Mystical Space Typhoon",
                "Harpie's Feather Duster",
                "Twin Twisters",
                "Cosmic Cyclone",
                "Heavy Storm Duster",
            ],
            "type": "oracle",
        },
        {
            "query": "hand trap disruption",
            "relevant": [
                "Ash Blossom & Joyous Spring",
                'Maxx "C"',
                "Nibiru, the Primal Being",
                "Effect Veiler",
                "Ghost Ogre & Snow Rabbit",
                "Droll & Lock Bird",
            ],
            "type": "semantic",
        },
    ],
}


def search_api(base_url: str, query: str, game: str, limit: int = 10) -> list[dict]:
    """Call the search API and return results."""
    url = f"{base_url}/v1/search"
    params = {"game": game, "q": query, "limit": limit}
    try:
        resp = httpx.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except Exception as e:
        print(f"  Search failed: {e}")
        return []


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Precision@K."""
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    return len(set(top_k) & relevant) / len(top_k)


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    """Recall@K."""
    if not relevant:
        return 0.0
    top_k = set(retrieved[:k])
    return len(top_k & relevant) / len(relevant)


def mrr(retrieved: list[str], relevant: set[str]) -> float:
    """Mean Reciprocal Rank."""
    for i, card in enumerate(retrieved):
        if card in relevant:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant_ordered: list[str], k: int) -> float:
    """nDCG@K with graded relevance based on position in ideal list."""
    import math

    # Assign relevance scores: position 0 in relevant_ordered gets highest
    rel_scores = {}
    for i, card in enumerate(relevant_ordered):
        rel_scores[card] = len(relevant_ordered) - i

    # DCG of actual ranking
    dcg = 0.0
    for i, card in enumerate(retrieved[:k]):
        rel = rel_scores.get(card, 0)
        dcg += rel / math.log2(i + 2)

    # Ideal DCG
    ideal_rels = sorted(rel_scores.values(), reverse=True)[:k]
    idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal_rels))

    return dcg / idcg if idcg > 0 else 0.0


def eval_game(game: str, base_url: str, k: int = 10) -> dict:
    """Evaluate search relevance for one game."""
    queries = SEARCH_QUERIES.get(game, [])
    if not queries:
        return {"game": game, "error": "no queries defined"}

    results = []
    for q in queries:
        t0 = time.monotonic()
        api_results = search_api(base_url, q["query"], game, limit=k)
        latency_ms = (time.monotonic() - t0) * 1000

        # Extract card names from results
        retrieved = []
        for r in api_results:
            name = r.get("card_name", r.get("card", r.get("name", "")))
            if name:
                retrieved.append(name)

        relevant_set = set(q["relevant"])
        p_at_k = precision_at_k(retrieved, relevant_set, k)
        r_at_k = recall_at_k(retrieved, relevant_set, k)
        m = mrr(retrieved, relevant_set)
        n = ndcg_at_k(retrieved, q["relevant"], k)

        results.append(
            {
                "query": q["query"],
                "type": q["type"],
                "precision_at_k": round(p_at_k, 4),
                "recall_at_k": round(r_at_k, 4),
                "mrr": round(m, 4),
                "ndcg_at_k": round(n, 4),
                "retrieved": retrieved[:k],
                "relevant_found": sorted(set(retrieved[:k]) & relevant_set),
                "relevant_missing": sorted(relevant_set - set(retrieved[:k])),
                "latency_ms": round(latency_ms, 1),
            }
        )

    # Aggregate
    oracle_results = [r for r in results if r["type"] == "oracle"]
    semantic_results = [r for r in results if r["type"] == "semantic"]

    def _avg(lst: list[dict], field: str) -> float:
        vals = [r[field] for r in lst]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    return {
        "game": game,
        "n_queries": len(results),
        "k": k,
        "overall": {
            "precision_at_k": _avg(results, "precision_at_k"),
            "recall_at_k": _avg(results, "recall_at_k"),
            "mrr": _avg(results, "mrr"),
            "ndcg_at_k": _avg(results, "ndcg_at_k"),
        },
        "oracle": {
            "n": len(oracle_results),
            "precision_at_k": _avg(oracle_results, "precision_at_k"),
            "recall_at_k": _avg(oracle_results, "recall_at_k"),
            "mrr": _avg(oracle_results, "mrr"),
            "ndcg_at_k": _avg(oracle_results, "ndcg_at_k"),
        },
        "semantic": {
            "n": len(semantic_results),
            "precision_at_k": _avg(semantic_results, "precision_at_k"),
            "recall_at_k": _avg(semantic_results, "recall_at_k"),
            "mrr": _avg(semantic_results, "mrr"),
            "ndcg_at_k": _avg(semantic_results, "ndcg_at_k"),
        },
        "per_query": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Search relevance evaluation")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--api-url", default="http://localhost:8001")
    parser.add_argument("-k", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--generate-only", action="store_true", help="Save test set without running eval"
    )
    args = parser.parse_args()

    if args.generate_only:
        out_path = TEST_SETS_DIR / "search_relevance_queries.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(SEARCH_QUERIES, f, indent=2)
        print(f"Saved search queries to {out_path}")
        total = sum(len(qs) for qs in SEARCH_QUERIES.values())
        print(f"  {total} queries across {len(SEARCH_QUERIES)} games")
        return

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    all_results = []

    for game in games:
        result = eval_game(game, args.api_url, args.k)
        all_results.append(result)

    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        for r in all_results:
            if "error" in r:
                print(f"\n{r['game']}: {r['error']}")
                continue

            print(f"\n{'=' * 60}")
            print(f"{r['game'].upper()} Search Relevance ({r['n_queries']} queries, k={r['k']})")

            ov = r["overall"]
            print(
                f"\n  Overall:  P@{r['k']}={ov['precision_at_k']:.3f}  R@{r['k']}={ov['recall_at_k']:.3f}  MRR={ov['mrr']:.3f}  nDCG@{r['k']}={ov['ndcg_at_k']:.3f}"
            )

            o = r["oracle"]
            print(
                f"  Oracle:   P@{r['k']}={o['precision_at_k']:.3f}  R@{r['k']}={o['recall_at_k']:.3f}  MRR={o['mrr']:.3f}  nDCG@{r['k']}={o['ndcg_at_k']:.3f}  (n={o['n']})"
            )

            s = r["semantic"]
            print(
                f"  Semantic: P@{r['k']}={s['precision_at_k']:.3f}  R@{r['k']}={s['recall_at_k']:.3f}  MRR={s['mrr']:.3f}  nDCG@{r['k']}={s['ndcg_at_k']:.3f}  (n={s['n']})"
            )

            print("\n  Per-query:")
            for pq in r["per_query"]:
                found = len(pq["relevant_found"])
                total = found + len(pq["relevant_missing"])
                print(
                    f'    [{pq["type"]:8s}] "{pq["query"]}"  P={pq["precision_at_k"]:.2f} R={pq["recall_at_k"]:.2f} MRR={pq["mrr"]:.2f} ({found}/{total} found, {pq["latency_ms"]:.0f}ms)'
                )
                if pq["relevant_missing"]:
                    print(f"             Missing: {', '.join(pq['relevant_missing'][:5])}")


if __name__ == "__main__":
    main()
