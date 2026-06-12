#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx>=0.25.0",
# ]
# ///
"""
Contextual endpoint evaluation for DeckSage.

Tests whether the /v1/cards/{name}/contextual endpoint returns
meaningful synergies, alternatives, upgrades, and downgrades.

Uses the enriched annotations (upgrade_direction, substitutability,
card roles) as ground truth.

Usage:
    uv run scripts/evaluation/eval_contextual.py --game magic
    uv run scripts/evaluation/eval_contextual.py --all-games
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_test_set(game: str) -> dict:
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def get_contextual(base_url: str, card: str, game: str, top_k: int = 5) -> dict:
    try:
        resp = httpx.get(
            f"{base_url}/v1/cards/{card}/contextual",
            params={"game": game, "top_k": top_k},
            timeout=30,
        )
        if resp.status_code != 200:
            return {"error": resp.status_code}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def eval_game(game: str, base_url: str, top_k: int = 5, max_queries: int = 50) -> dict:
    """Evaluate contextual endpoint against annotations."""
    test_set = load_test_set(game)
    if not test_set:
        return {"game": game, "error": "no test set"}

    queries = test_set.get("queries", {})

    # Find queries with upgrade_direction annotations
    upgrade_queries = []
    for qname, qdata in queries.items():
        upgrades = []
        downgrades = []
        for ann in qdata.get("annotations", []):
            ud = ann.get("upgrade_direction", "")
            cand = ann.get("candidate", "")
            if ud == "b_upgrades_a" and cand:
                upgrades.append(cand)
            elif ud == "a_upgrades_b" and cand:
                downgrades.append(cand)
        if upgrades or downgrades:
            upgrade_queries.append(
                {
                    "query": qname,
                    "expected_upgrades": upgrades,
                    "expected_downgrades": downgrades,
                }
            )

    # Find queries with high substitutability
    sub_queries = []
    for qname, qdata in queries.items():
        subs = []
        for ann in qdata.get("annotations", []):
            sub = ann.get("substitutability", 0)
            cand = ann.get("candidate", "")
            if sub and float(sub) > 0.5 and cand:
                subs.append(cand)
        if subs:
            sub_queries.append({"query": qname, "expected_alternatives": subs})

    # Sample queries to test
    test_queries = upgrade_queries[:max_queries]
    sub_test = sub_queries[:max_queries]

    results = {
        "game": game,
        "n_upgrade_queries": len(upgrade_queries),
        "n_sub_queries": len(sub_queries),
        "tested": 0,
    }

    # Test upgrade/downgrade accuracy
    upgrade_hits = 0
    upgrade_total = 0
    downgrade_hits = 0
    downgrade_total = 0
    empty_upgrades = 0
    empty_downgrades = 0
    latencies = []

    for tq in test_queries:
        t0 = time.monotonic()
        ctx = get_contextual(base_url, tq["query"], game, top_k)
        latencies.append((time.monotonic() - t0) * 1000)

        if "error" in ctx:
            continue

        results["tested"] = results.get("tested", 0) + 1

        api_upgrades = {r.get("card", "") for r in ctx.get("upgrades", [])}
        api_downgrades = {r.get("card", "") for r in ctx.get("downgrades", [])}

        if not api_upgrades:
            empty_upgrades += 1
        if not api_downgrades:
            empty_downgrades += 1

        for exp in tq["expected_upgrades"]:
            upgrade_total += 1
            if exp in api_upgrades:
                upgrade_hits += 1

        for exp in tq["expected_downgrades"]:
            downgrade_total += 1
            if exp in api_downgrades:
                downgrade_hits += 1

    # Test alternative accuracy
    alt_hits = 0
    alt_total = 0
    for sq in sub_test:
        ctx = get_contextual(base_url, sq["query"], game, top_k)
        if "error" in ctx:
            continue
        api_alts = {r.get("card", "") for r in ctx.get("alternatives", [])}
        for exp in sq["expected_alternatives"]:
            alt_total += 1
            if exp in api_alts:
                alt_hits += 1

    results.update(
        {
            "upgrade_recall": round(upgrade_hits / upgrade_total, 3) if upgrade_total else 0,
            "upgrade_total": upgrade_total,
            "upgrade_hits": upgrade_hits,
            "downgrade_recall": round(downgrade_hits / downgrade_total, 3)
            if downgrade_total
            else 0,
            "downgrade_total": downgrade_total,
            "downgrade_hits": downgrade_hits,
            "empty_upgrades": empty_upgrades,
            "empty_downgrades": empty_downgrades,
            "alternative_recall": round(alt_hits / alt_total, 3) if alt_total else 0,
            "alternative_total": alt_total,
            "alternative_hits": alt_hits,
            "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
            "scores_normalized": True,  # Check if scores are 0-1
        }
    )

    # Check score normalization
    if test_queries:
        ctx = get_contextual(base_url, test_queries[0]["query"], game, top_k)
        if "error" not in ctx:
            for cat in ["synergies", "alternatives", "upgrades", "downgrades"]:
                items = ctx.get(cat, [])
                if items:
                    max_score = max(r.get("score", 0) for r in items)
                    results["scores_normalized"] = max_score >= 0.9  # Should be ~1.0

    return results


def main():
    parser = argparse.ArgumentParser(description="Contextual endpoint evaluation")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--api-url", default="http://localhost:8001")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    all_results = []

    for game in games:
        result = eval_game(game, args.api_url, args.top_k)
        all_results.append(result)

    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        for r in all_results:
            if "error" in r:
                print(f"\n{r['game']}: {r['error']}")
                continue

            print(f"\n{'=' * 60}")
            print(f"{r['game'].upper()} Contextual Endpoint")
            print(f"  Tested: {r['tested']} queries")
            print(f"  Scores normalized: {'YES' if r['scores_normalized'] else 'NO'}")
            print(f"  Avg latency: {r['avg_latency_ms']}ms")
            print(
                f"\n  Upgrade recall: {r['upgrade_hits']}/{r['upgrade_total']} ({r['upgrade_recall']:.1%})"
            )
            print(
                f"  Downgrade recall: {r['downgrade_hits']}/{r['downgrade_total']} ({r['downgrade_recall']:.1%})"
            )
            print(
                f"  Alternative recall: {r['alternative_hits']}/{r['alternative_total']} ({r['alternative_recall']:.1%})"
            )
            print(f"  Empty upgrades: {r['empty_upgrades']}/{r['tested']}")
            print(f"  Empty downgrades: {r['empty_downgrades']}/{r['tested']}")


if __name__ == "__main__":
    main()
