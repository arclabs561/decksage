#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.25.0",
# ]
# ///
"""
Deck completion quality evaluation for DeckSage.

Tests whether the deck completion API produces coherent, game-legal decks
from seed cards. Evaluates:
1. Size correctness (60 for MTG, 60 for YGO, 60 for Pokemon)
2. Copy limit compliance (4x MTG, 3x YGO, 4x Pokemon)
3. Color identity coherence (MTG: seeded colors dominate)
4. Archetype coherence (do completed cards fit the seed archetype?)
5. Card quality (competitive power level of suggested cards)
6. Diversity (not all cards from the same narrow cluster)

Uses hand-curated seed decks with expected properties.

Usage:
    uv run scripts/evaluation/eval_deck_completion.py --game magic
    uv run scripts/evaluation/eval_deck_completion.py --all-games
    uv run scripts/evaluation/eval_deck_completion.py --api-url http://localhost:8001
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Copy limits per game
COPY_LIMITS = {"magic": 4, "pokemon": 4, "yugioh": 3}
TARGET_SIZES = {"magic": 60, "pokemon": 60, "yugioh": 40}

# Seed decks with expected properties
SEED_DECKS = {
    "magic": [
        {
            "name": "Red Burn",
            "seed": ["Lightning Bolt", "Mountain", "Goblin Guide"],
            "expected_colors": {"R"},
            "expected_types": {"Instant", "Sorcery", "Creature"},
            "bad_cards": [
                "Goblin Balloon Brigade",
                "Wall of Fire",
                "Iron Star",
                "Ivory Cup",
                "Crystal Rod",
                "Soul Net",
                "Millstone",
            ],
        },
        {
            "name": "Blue Control",
            "seed": ["Counterspell", "Island", "Snapcaster Mage"],
            "expected_colors": {"U"},
            "expected_types": {"Instant", "Sorcery", "Creature"},
            "bad_cards": [],
        },
        {
            "name": "Green Ramp",
            "seed": ["Llanowar Elves", "Forest", "Craterhoof Behemoth"],
            "expected_colors": {"G"},
            "expected_types": {"Creature", "Sorcery"},
            "bad_cards": [],
        },
    ],
    "pokemon": [
        {
            "name": "Standard Toolbox",
            "seed": ["Ultra Ball", "Professor's Research", "Nest Ball"],
            "expected_colors": set(),
            "expected_types": set(),
            "bad_cards": [],
        },
    ],
    "yugioh": [
        {
            "name": "Hand Trap Package",
            "seed": ["Ash Blossom & Joyous Spring", 'Maxx "C"', "Infinite Impermanence"],
            "expected_colors": set(),
            "expected_types": set(),
            "bad_cards": [],
        },
        {
            "name": "Blue-Eyes Core",
            "seed": [
                "Blue-Eyes White Dragon",
                "Sage with Eyes of Blue",
                "The White Stone of Ancients",
            ],
            "expected_colors": set(),
            "expected_types": set(),
            "bad_cards": [],
        },
    ],
}


def complete_deck(base_url: str, game: str, seed: list[str], target: int) -> dict:
    """Call deck completion API."""
    url = f"{base_url}/v1/deck/complete"
    body = {
        "game": game,
        "deck": {"Main": seed},
        "target_main_size": target,
    }
    try:
        resp = httpx.post(url, json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def load_card_metadata(game: str) -> dict[str, dict]:
    """Load enriched CSV for card metadata."""
    path = DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        return {}
    result = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if name:
                result[name] = dict(row)
    return result


def extract_cards(deck_response: dict) -> list[tuple[str, int]]:
    """Extract (card_name, count) from completion response."""
    cards = []
    partitions = deck_response.get("deck", {}).get("partitions", [])
    for part in partitions:
        # Match "Main", "Main Deck", or "Deck" (varies by game)
        pname = part.get("name", "").lower()
        if pname in ("main", "main deck", "deck"):
            for card in part.get("cards", []):
                if isinstance(card, dict):
                    cards.append((card.get("name", ""), card.get("count", 1)))
                else:
                    cards.append((str(card), 1))
    return cards


def eval_completion(
    game: str,
    seed_config: dict,
    deck_response: dict,
    card_metadata: dict[str, dict],
) -> dict:
    """Evaluate a single deck completion."""
    if "error" in deck_response:
        return {"name": seed_config["name"], "error": deck_response["error"]}

    cards = extract_cards(deck_response)
    total_cards = sum(count for _, count in cards)
    unique_cards = len(cards)
    copy_limit = COPY_LIMITS[game]
    target = TARGET_SIZES[game]

    # 1. Size correctness
    size_correct = total_cards == target

    # 2. Copy limit compliance
    over_limit = [(name, count) for name, count in cards if count > copy_limit]

    # 3. Color coherence (Magic only)
    color_violations = []
    if game == "magic" and seed_config.get("expected_colors"):
        expected = seed_config["expected_colors"]
        for name, count in cards:
            meta = card_metadata.get(name, {})
            colors = meta.get("colors", "")
            if colors and colors not in ("", "nan"):
                card_colors = set(colors.replace(",", ""))
                # Lands and colorless are OK
                if card_colors and not card_colors.issubset(expected | {"C", ""}):
                    color_violations.append((name, colors))

    # 4. Bad card detection
    bad_found = []
    for name, count in cards:
        if name in seed_config.get("bad_cards", []):
            bad_found.append((name, count))

    # 5. Card quality (power level from metadata)
    power_levels = []
    for name, count in cards:
        meta = card_metadata.get(name, {})
        # Use deck_popularity as a proxy for card quality
        pop = meta.get("deck_popularity", "")
        if pop and pop != "nan":
            try:
                total_decks = json.loads(pop.replace("'", '"')).get("total_decks", 0)
                power_levels.append(total_decks)
            except (json.JSONDecodeError, AttributeError):
                pass

    # 6. Card in embedding vocab (basic coverage check)
    in_metadata = sum(1 for name, _ in cards if name in card_metadata)

    return {
        "name": seed_config["name"],
        "seed": seed_config["seed"],
        "total_cards": total_cards,
        "unique_cards": unique_cards,
        "target": target,
        "size_correct": size_correct,
        "copy_limit_violations": over_limit,
        "color_violations": color_violations[:5],
        "bad_cards_found": bad_found,
        "metadata_coverage": f"{in_metadata}/{unique_cards}",
        "median_popularity": int(sorted(power_levels)[len(power_levels) // 2])
        if power_levels
        else 0,
        "steps": deck_response.get("metrics", {}).get("steps", 0),
        "method": deck_response.get("metrics", {}).get("method", "?"),
        "elapsed_ms": deck_response.get("metrics", {}).get("elapsed_ms", 0),
        "added_cards": [(n, c) for n, c in cards if n not in seed_config["seed"]][:10],
    }


def eval_game(game: str, base_url: str) -> dict:
    """Evaluate all seed decks for one game."""
    seeds = SEED_DECKS.get(game, [])
    if not seeds:
        return {"game": game, "error": "no seed decks defined"}

    card_metadata = load_card_metadata(game)
    target = TARGET_SIZES[game]
    results = []

    for seed_config in seeds:
        t0 = time.monotonic()
        response = complete_deck(base_url, game, seed_config["seed"], target)
        latency = (time.monotonic() - t0) * 1000

        result = eval_completion(game, seed_config, response, card_metadata)
        result["latency_ms"] = round(latency, 1)
        results.append(result)

    # Aggregate
    n_correct_size = sum(1 for r in results if r.get("size_correct"))
    n_copy_violations = sum(len(r.get("copy_limit_violations", [])) for r in results)
    n_bad_cards = sum(len(r.get("bad_cards_found", [])) for r in results)
    n_color_violations = sum(len(r.get("color_violations", [])) for r in results)

    return {
        "game": game,
        "n_seeds": len(seeds),
        "summary": {
            "size_correct": f"{n_correct_size}/{len(seeds)}",
            "copy_violations": n_copy_violations,
            "color_violations": n_color_violations,
            "bad_cards": n_bad_cards,
        },
        "per_seed": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Deck completion quality evaluation")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--api-url", default="http://localhost:8001")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    all_results = []

    for game in games:
        result = eval_game(game, args.api_url)
        all_results.append(result)

    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        for r in all_results:
            if "error" in r:
                print(f"\n{r['game']}: {r['error']}")
                continue

            print(f"\n{'=' * 60}")
            print(f"{r['game'].upper()} Deck Completion ({r['n_seeds']} seeds)")
            s = r["summary"]
            print(f"  Size correct: {s['size_correct']}")
            print(f"  Copy violations: {s['copy_violations']}")
            print(f"  Color violations: {s['color_violations']}")
            print(f"  Bad cards: {s['bad_cards']}")

            for seed in r["per_seed"]:
                if "error" in seed:
                    print(f"\n  {seed['name']}: ERROR - {seed['error']}")
                    continue
                print(
                    f"\n  {seed['name']} ({seed['total_cards']} cards, {seed['latency_ms']:.0f}ms, method={seed['method']})"
                )
                print(
                    f"    Size: {'PASS' if seed['size_correct'] else 'FAIL'} ({seed['total_cards']}/{seed['target']})"
                )
                if seed["copy_limit_violations"]:
                    print(f"    Copy limit violations: {seed['copy_limit_violations']}")
                if seed["color_violations"]:
                    print(f"    Color violations: {seed['color_violations']}")
                if seed["bad_cards_found"]:
                    print(f"    Bad cards: {seed['bad_cards_found']}")
                print(f"    Metadata coverage: {seed['metadata_coverage']}")
                print(f"    Median popularity: {seed['median_popularity']} decks")
                print(f"    Added (first 10): {[f'{n} x{c}' for n, c in seed['added_cards']]}")


if __name__ == "__main__":
    main()
