#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27.0"]
# ///
"""
Compare deck completion methods (greedy vs OT) by hitting the live API.

Usage:
    uv run scripts/eval_completion_methods.py [--base-url http://localhost:8001]
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import httpx

# Test decks: seed cards for different archetypes
TEST_DECKS = {
    "magic_burn": {
        "game": "magic",
        "seeds": ["Lightning Bolt", "Goblin Guide", "Monastery Swiftspear", "Eidolon of the Great Revel"],
        "target": 30,
    },
    "magic_control": {
        "game": "magic",
        "seeds": ["Counterspell", "Snapcaster Mage", "Cryptic Command", "Jace, the Mind Sculptor"],
        "target": 30,
    },
    "yugioh_dragon": {
        "game": "yugioh",
        "seeds": ["Blue-Eyes White Dragon", "Dragon Shrine", "The Melody of Awakening Dragon"],
        "target": 20,
    },
}

METHODS = ["greedy", "ot"]


def run_completion(client: httpx.Client, game: str, seeds: list[str], target: int, method: str) -> dict:
    """Run a single completion and return metrics."""
    payload = {
        "game": game,
        "deck": {"Main" if game == "magic" else "Main Deck": seeds},
        "target_main_size": target,
        "method": method,
    }
    t0 = time.monotonic()
    resp = client.post("/v1/deck/complete", json=payload, timeout=30.0)
    elapsed = time.monotonic() - t0

    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "elapsed_s": elapsed}

    data = resp.json()
    steps = data.get("steps", [])
    cards_added = sum(s.get("count", 1) for s in steps)

    # Count unique cards in completed deck
    unique_cards = set()
    part_name = "Main" if game == "magic" else "Main Deck"
    for p in data.get("deck", {}).get("partitions", []):
        if p.get("name") == part_name:
            for c in p.get("cards", []):
                unique_cards.add(c.get("name"))

    return {
        "cards_added": cards_added,
        "unique_cards": len(unique_cards),
        "elapsed_s": round(elapsed, 3),
        "steps": len(steps),
        "quality": data.get("metrics", {}).get("quality"),
        "added_names": [s.get("card") for s in steps[:10]],
    }


def main():
    parser = argparse.ArgumentParser(description="Compare deck completion methods")
    parser.add_argument("--base-url", default="http://localhost:8001")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url)

    # Check readiness
    try:
        resp = client.get("/ready", timeout=5.0)
        if resp.status_code != 200:
            print(f"Server not ready: {resp.status_code}", file=sys.stderr)
            sys.exit(1)
    except httpx.ConnectError:
        print(f"Cannot connect to {args.base_url}", file=sys.stderr)
        sys.exit(1)

    print(f"Server ready at {args.base_url}")
    print("=" * 80)

    for deck_name, deck_cfg in TEST_DECKS.items():
        print(f"\n## {deck_name} ({deck_cfg['game']}, {len(deck_cfg['seeds'])} seeds -> {deck_cfg['target']})")
        print(f"   Seeds: {', '.join(deck_cfg['seeds'][:4])}")
        print()

        results = {}
        for method in METHODS:
            result = run_completion(
                client,
                deck_cfg["game"],
                deck_cfg["seeds"],
                deck_cfg["target"],
                method,
            )
            results[method] = result

            if "error" in result:
                print(f"   {method:8s}: ERROR - {result['error']}")
            else:
                print(f"   {method:8s}: +{result['cards_added']} cards, "
                      f"{result['unique_cards']} unique, "
                      f"{result['elapsed_s']}s")
                if result["added_names"]:
                    print(f"            Top adds: {', '.join(result['added_names'][:5])}")

        # Diversity comparison
        if all("added_names" in r for r in results.values()):
            greedy_set = set(results["greedy"].get("added_names", []))
            ot_set = set(results["ot"].get("added_names", []))
            overlap = greedy_set & ot_set
            print(f"\n   Overlap: {len(overlap)}/{max(len(greedy_set), len(ot_set))} cards in common")

    print("\n" + "=" * 80)
    print("Done.")


if __name__ == "__main__":
    main()
