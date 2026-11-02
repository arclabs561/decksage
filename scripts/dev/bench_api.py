#!/usr/bin/env python3
"""Median latency for the serving endpoints, on one running stack.

Prints a table; the numbers are only comparable within the same host window
(see docs/PERFORMANCE.md). Usage:

    uv run python scripts/dev/bench_api.py --base-url http://127.0.0.1:8000 -n 7
"""

from __future__ import annotations

import argparse
import json
import statistics
import time

import httpx


CASES: list[tuple[str, str, str, dict]] = [
    (
        "search lexical",
        "POST",
        "/v1/search",
        {"game": "magic", "query": "draw two cards", "limit": 10},
    ),
    (
        "search card name",
        "POST",
        "/v1/search",
        {"game": "magic", "query": "Lightning Bolt", "limit": 10},
    ),
    (
        "search filtered",
        "POST",
        "/v1/search",
        {
            "game": "magic",
            "query": "draw two cards",
            "limit": 10,
            "filters": 'colors = "U" AND cmc <= 3',
        },
    ),
    (
        "similar embedding",
        "POST",
        "/v1/similar",
        {"game": "magic", "query": "Lightning Bolt", "top_k": 10, "mode": "embedding"},
    ),
    (
        "similar text",
        "POST",
        "/v1/similar",
        {"game": "magic", "query": "Lightning Bolt", "top_k": 10, "mode": "text"},
    ),
    (
        "similar union",
        "POST",
        "/v1/similar",
        {"game": "magic", "query": "Lightning Bolt", "top_k": 10, "mode": "union"},
    ),
    ("card info", "GET", "/v1/cards/Lightning Bolt", {"game": "magic"}),
    (
        "graph neighbors",
        "GET",
        "/v1/graph/neighbors",
        {"game": "magic", "card": "Lightning Bolt", "limit": 20},
    ),
    ("graph stats", "GET", "/v1/graph/stats", {"game": "magic"}),
    ("index status", "GET", "/v1/index/status", {}),
    ("cards prefix", "GET", "/v1/cards", {"game": "magic", "prefix": "light", "limit": 20}),
    (
        "deck complete",
        "POST",
        "/v1/deck/complete",
        {
            "game": "magic",
            "cards": [{"name": "Lightning Bolt", "count": 4}, {"name": "Mountain", "count": 20}],
            "target_main_size": 30,
            "max_steps": 5,
            "method": "greedy",
        },
    ),
]


def run(base_url: str, repeats: int) -> dict[str, dict[str, float]]:
    results: dict[str, dict[str, float]] = {}
    with httpx.Client(base_url=base_url, timeout=300) as client:
        for name, method, path, payload in CASES:
            samples: list[float] = []
            for _ in range(repeats):
                start = time.perf_counter()
                if method == "GET":
                    response = client.get(path, params=payload)
                else:
                    response = client.post(path, json=payload)
                elapsed = (time.perf_counter() - start) * 1000
                response.raise_for_status()
                samples.append(elapsed)
            results[name] = {
                "median_ms": round(statistics.median(samples), 1),
                "min_ms": round(min(samples), 1),
                "max_ms": round(max(samples), 1),
            }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("-n", "--repeats", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = run(args.base_url, args.repeats)
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    for name, values in results.items():
        print(
            f"{name:20s} {values['median_ms']:8.1f} ms"
            f"  (min {values['min_ms']:.1f}, max {values['max_ms']:.1f})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
