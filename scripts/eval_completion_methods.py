#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27.0"]
# ///
"""
Compare deck completion methods (greedy vs OT) by hitting the live API.

Usage:
    uv run scripts/eval_completion_methods.py [--base-url http://localhost:8001]
    uv run scripts/eval_completion_methods.py --sweep          # parameter sweep
    uv run scripts/eval_completion_methods.py --json           # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from itertools import product

import httpx

# Test decks: seed cards for different archetypes
TEST_DECKS = {
    "magic_burn": {
        "game": "magic",
        "seeds": [
            "Lightning Bolt",
            "Goblin Guide",
            "Monastery Swiftspear",
            "Eidolon of the Great Revel",
        ],
        "target": 30,
    },
    "magic_control": {
        "game": "magic",
        "seeds": [
            "Counterspell",
            "Snapcaster Mage",
            "Cryptic Command",
            "Jace, the Mind Sculptor",
        ],
        "target": 30,
    },
    "magic_midrange": {
        "game": "magic",
        "seeds": [
            "Tarmogoyf",
            "Liliana of the Veil",
            "Thoughtseize",
            "Fatal Push",
            "Bloodbraid Elf",
        ],
        "target": 30,
    },
    "yugioh_dragon": {
        "game": "yugioh",
        "seeds": [
            "Blue-Eyes White Dragon",
            "Dragon Shrine",
            "The Melody of Awakening Dragon",
        ],
        "target": 20,
    },
    "pokemon_pikachu": {
        "game": "pokemon",
        "seeds": ["Pikachu", "Raichu", "Professor's Research"],
        "target": 20,
    },
}

METHODS = ["greedy", "ot"]

# Parameter sweep grid for OT
SWEEP_GRID = {
    "sinkhorn_reg": [0.01, 0.05, 0.1, 0.5],
    "embedding_weight": [0.3, 0.5, 0.7],
    "role_weight": [0.1, 0.3, 0.5],
}


def run_completion(
    client: httpx.Client,
    game: str,
    seeds: list[str],
    target: int,
    method: str,
    **ot_params: float,
) -> dict:
    """Run a single completion and return metrics."""
    part_name = "Main" if game == "magic" else ("Main Deck" if game == "yugioh" else "Deck")
    payload: dict = {
        "game": game,
        "deck": {part_name: seeds},
        "target_main_size": target,
        "method": method,
    }
    # Add OT-specific params
    for k, v in ot_params.items():
        payload[k] = v

    t0 = time.monotonic()
    resp = client.post("/v1/deck/complete", json=payload, timeout=60.0)
    elapsed = time.monotonic() - t0

    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "elapsed_s": elapsed}

    data = resp.json()
    steps = data.get("steps", [])
    cards_added = sum(s.get("count", 1) for s in steps)

    # Count unique cards in completed deck
    unique_cards = set()
    for p in data.get("deck", {}).get("partitions", []):
        if p.get("name") == part_name:
            for c in p.get("cards", []):
                unique_cards.add(c.get("name"))

    # Extract quality metrics
    api_metrics = data.get("metrics", {})
    quality = api_metrics.get("quality")
    ot_info = api_metrics.get("ot", {})

    return {
        "method": method,
        "game": game,
        "cards_added": cards_added,
        "unique_cards": len(unique_cards),
        "elapsed_s": round(elapsed, 3),
        "elapsed_ms": api_metrics.get("elapsed_ms"),
        "steps": len(steps),
        "quality": quality,
        "overall_score": quality.get("overall_score") if quality else None,
        "curve_score": quality.get("mana_curve_score") if quality else None,
        "tag_score": quality.get("tag_balance_score") if quality else None,
        "synergy_score": quality.get("synergy_score") if quality else None,
        "ot_distance": ot_info.get("ot_distance"),
        "pool_size": ot_info.get("pool_size"),
        "added_names": [s.get("card") for s in steps[:10]],
        "ot_params": ot_params if ot_params else None,
    }


def fmt_score(val: float | None) -> str:
    return f"{val:.2f}" if val is not None else "n/a"


def run_comparison(client: httpx.Client, json_output: bool = False) -> list[dict]:
    """Compare greedy vs OT across all test decks."""
    all_results: list[dict] = []

    for deck_name, deck_cfg in TEST_DECKS.items():
        if not json_output:
            print(
                f"\n## {deck_name} ({deck_cfg['game']}, "
                f"{len(deck_cfg['seeds'])} seeds -> {deck_cfg['target']})"
            )
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
            result["deck_name"] = deck_name
            results[method] = result
            all_results.append(result)

            if not json_output:
                if "error" in result:
                    print(f"   {method:8s}: ERROR - {result['error']}")
                else:
                    quality_str = ""
                    if result["overall_score"] is not None:
                        quality_str = (
                            f"  quality={fmt_score(result['overall_score'])}/10 "
                            f"(curve={fmt_score(result['curve_score'])} "
                            f"tag={fmt_score(result['tag_score'])} "
                            f"syn={fmt_score(result['synergy_score'])})"
                        )
                    print(
                        f"   {method:8s}: +{result['cards_added']} cards, "
                        f"{result['unique_cards']} unique, "
                        f"{result['elapsed_s']}s{quality_str}"
                    )
                    if result["added_names"]:
                        print(f"            Top adds: {', '.join(result['added_names'][:5])}")

        # Diversity comparison
        if not json_output and all("added_names" in r for r in results.values()):
            greedy_set = set(results.get("greedy", {}).get("added_names", []))
            ot_set = set(results.get("ot", {}).get("added_names", []))
            if greedy_set and ot_set:
                overlap = greedy_set & ot_set
                print(
                    f"\n   Overlap: {len(overlap)}/{max(len(greedy_set), len(ot_set))} "
                    f"cards in common"
                )

    return all_results


def run_sweep(client: httpx.Client, json_output: bool = False) -> list[dict]:
    """Sweep OT parameters and find optimal configuration."""
    # Use a subset of decks for sweep (speed)
    sweep_decks = {
        k: v for k, v in TEST_DECKS.items() if k in ("magic_burn", "magic_control", "yugioh_dragon")
    }

    regs = SWEEP_GRID["sinkhorn_reg"]
    emb_ws = SWEEP_GRID["embedding_weight"]
    role_ws = SWEEP_GRID["role_weight"]

    all_results: list[dict] = []
    total = len(regs) * len(emb_ws) * len(role_ws) * len(sweep_decks)
    done = 0

    if not json_output:
        print(f"\nSweeping {total} configurations...")
        print(
            f"{'reg':>6s} {'emb_w':>6s} {'role_w':>6s} {'curve_w':>7s} | "
            f"{'quality':>8s} {'ot_dist':>8s} {'ms':>6s} {'deck':>15s}"
        )
        print("-" * 85)

    best_score = -1.0
    best_ot_dist = float("inf")
    best_params: dict = {}

    for reg, emb_w, role_w in product(regs, emb_ws, role_ws):
        curve_w = max(0.0, round(1.0 - emb_w - role_w, 2))
        if curve_w < 0:
            continue  # Invalid weight combination

        for deck_name, deck_cfg in sweep_decks.items():
            result = run_completion(
                client,
                deck_cfg["game"],
                deck_cfg["seeds"],
                deck_cfg["target"],
                "ot",
                sinkhorn_reg=reg,
                embedding_weight=emb_w,
                role_weight=role_w,
                curve_weight=curve_w,
            )
            result["deck_name"] = deck_name
            result["sinkhorn_reg"] = reg
            result["embedding_weight"] = emb_w
            result["role_weight"] = role_w
            result["curve_weight"] = curve_w
            all_results.append(result)

            done += 1
            score = result.get("overall_score")
            ot_dist = result.get("ot_distance")
            ms = result.get("elapsed_ms", "")

            if not json_output:
                score_str = fmt_score(score) if score is not None else "n/a"
                dist_str = f"{ot_dist:.4f}" if ot_dist is not None else "n/a"
                print(
                    f"{reg:6.2f} {emb_w:6.2f} {role_w:6.2f} {curve_w:7.2f} | "
                    f"{score_str:>8s} {dist_str:>8s} {str(ms):>6s} {deck_name:>15s}"
                )

            # Track best by quality score if available, else by OT distance (lower=better)
            if score is not None and score > best_score:
                best_score = score
                best_params = {
                    "sinkhorn_reg": reg,
                    "embedding_weight": emb_w,
                    "role_weight": role_w,
                    "curve_weight": curve_w,
                    "deck_name": deck_name,
                    "metric": "quality_score",
                }
            elif score is None and ot_dist is not None and ot_dist < best_ot_dist:
                best_ot_dist = ot_dist
                if best_score < 0:  # Only use OT distance if no quality scores available
                    best_params = {
                        "sinkhorn_reg": reg,
                        "embedding_weight": emb_w,
                        "role_weight": role_w,
                        "curve_weight": curve_w,
                        "deck_name": deck_name,
                        "metric": "ot_distance",
                    }

    if not json_output:
        print("-" * 85)
        if best_score >= 0:
            print(f"\nBest quality score: {best_score:.2f}/10")
        else:
            print(f"\nBest OT distance: {best_ot_dist:.4f} (lower = tighter transport fit)")
        print(f"Best params: {json.dumps(best_params, indent=2)}")

        # Compute average OT distance per parameter setting (since quality may not be available)
        param_dists: dict[str, list[float]] = {}
        param_scores: dict[str, list[float]] = {}
        for r in all_results:
            key = f"reg={r['sinkhorn_reg']:.2f} emb={r['embedding_weight']:.1f} role={r['role_weight']:.1f}"
            s = r.get("overall_score")
            d = r.get("ot_distance")
            if s is not None:
                param_scores.setdefault(key, []).append(s)
            if d is not None:
                param_dists.setdefault(key, []).append(d)

        if param_scores:
            print("\nAverage quality scores by parameter combo (top 10):")
            avg_scores = sorted(
                [(k, sum(v) / len(v), len(v)) for k, v in param_scores.items()],
                key=lambda x: x[1],
                reverse=True,
            )
            for k, avg, n in avg_scores[:10]:
                print(f"  {k}: {avg:.2f}/10 (n={n})")

        if param_dists:
            print("\nAverage OT distance by parameter combo (top 10, lower=better):")
            avg_dists = sorted(
                [(k, sum(v) / len(v), len(v)) for k, v in param_dists.items()],
                key=lambda x: x[1],
            )
            for k, avg, n in avg_dists[:10]:
                print(f"  {k}: {avg:.4f} (n={n})")

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Compare deck completion methods")
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--sweep", action="store_true", help="Run OT parameter sweep")
    parser.add_argument("--json", action="store_true", help="JSON output")
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

    if not args.json:
        print(f"Server ready at {args.base_url}")
        print("=" * 80)

    if args.sweep:
        results = run_sweep(client, json_output=args.json)
    else:
        results = run_comparison(client, json_output=args.json)

    if args.json:
        # Strip non-serializable fields
        for r in results:
            r.pop("added_names", None)
        json.dump(results, sys.stdout, indent=2)
        print()
    elif not args.sweep:
        print("\n" + "=" * 80)
        print("Done.")


if __name__ == "__main__":
    main()
