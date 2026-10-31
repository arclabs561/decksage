#!/usr/bin/env python3
"""Compose the DeckSage API into one agent-ready card brief.

This is the smallest useful agentic workflow: one card in, four evidence
sections out. It exercises the interfaces the experiments validated:

  text      functional candidates (E5, 0082)
  graph     co-occurrence neighbours (synergy, not substitution)
  contextual curated synergy/alternatives/upgrades from the API
  exact     whether the name is a real card

Usage:
    scripts/agentic/card_brief.py --card "Lightning Bolt" --game magic --k 5
"""

from __future__ import annotations

import argparse
import json
import os

import httpx


def post(client: httpx.Client, path: str, payload: dict) -> dict:
    response = client.post(path, json=payload)
    response.raise_for_status()
    return response.json()


def get(client: httpx.Client, path: str, params: dict) -> dict:
    response = client.get(path, params=params)
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", required=True)
    parser.add_argument("--game", default="magic")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--base-url", default=os.getenv("DECKSAGE_API", "http://127.0.0.1:8000"))
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        text = post(
            client,
            "/v1/similar",
            {"game": args.game, "query": args.card, "top_k": args.k, "mode": "text"},
        )
        graph = post(
            client,
            "/v1/similar",
            {"game": args.game, "query": args.card, "top_k": args.k, "mode": "embedding"},
        )
        neighbours = get(
            client, "/v1/graph/neighbors", {"game": args.game, "card": args.card, "limit": args.k}
        )
        contextual = get(
            client, f"/v1/cards/{args.card}/contextual", {"game": args.game, "top_k": args.k}
        )

    brief = {
        "card": args.card,
        "game": args.game,
        "exact_match": text.get("exact_match"),
        "functional_candidates": [
            {"card": row["card"], "score": row["similarity"]} for row in text.get("results", [])
        ],
        "co_play_neighbours": [
            {"card": row["card"], "score": row["similarity"]} for row in graph.get("results", [])
        ],
        "graph_edges": neighbours.get("neighbors", []),
        "contextual": {
            key: [
                {"card": row["card"], "score": row["score"]} for row in (contextual.get(key) or [])
            ]
            for key in ("synergies", "alternatives", "upgrades", "downgrades")
        },
    }
    print(json.dumps(brief, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
