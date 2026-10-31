#!/usr/bin/env python3
"""Headless tool-calling agent that audits the DeckSage API.

Uses OpenRouter's OpenAI-compatible tool calls, no extra SDK. The agent gets
the same tools a real client would; it must call them and report friction.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx


BASE = os.getenv("DECKSAGE_API", "http://127.0.0.1:8000")
MODEL = os.getenv("CRITIQUE_MODEL", "google/gemini-2.5-flash")
OUT = (
    Path(__file__).resolve().parents[2] / ".agents" / "reports" / "2026-10-31-api-agent-critique.md"
)


def tool_schemas() -> list[dict]:
    def schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        }

    return [
        schema(
            "search",
            "Search cards by name or effect text.",
            {"game": {"type": "string"}, "query": {"type": "string"}},
            ["game", "query"],
        ),
        schema(
            "autocomplete",
            "Type-ahead card names by prefix (handles typos).",
            {
                "game": {"type": "string", "enum": ["magic", "pokemon", "yugioh"]},
                "prefix": {"type": "string"},
            },
            ["game", "prefix"],
        ),
        schema(
            "similar",
            "Find cards similar to one card. mode: embedding, text or union.",
            {
                "game": {"type": "string", "enum": ["magic", "pokemon", "yugioh"]},
                "card": {"type": "string"},
                "mode": {"type": "string", "enum": ["embedding", "text", "union"]},
            },
            ["game", "card"],
        ),
        schema(
            "card_info",
            "Fetch one card's metadata.",
            {"game": {"type": "string"}, "card": {"type": "string"}},
            ["game", "card"],
        ),
        schema(
            "legality",
            "Fetch format legality and ban status for a card.",
            {"game": {"type": "string"}, "card": {"type": "string"}},
            ["game", "card"],
        ),
        schema(
            "graph_neighbors",
            "Typed neighbours (text, tag, cooccurrence, attribute).",
            {
                "game": {"type": "string"},
                "card": {"type": "string"},
                "relations": {"type": "string"},
            },
            ["game", "card"],
        ),
        schema(
            "complete_deck",
            "Complete a deck from raw deck list text.",
            {
                "game": {"type": "string"},
                "deck_text": {"type": "string"},
                "target": {"type": "integer"},
            },
            ["game", "deck_text"],
        ),
        schema("index_status", "Catalog/index coverage per game.", {}, []),
    ]


def call_tool(name: str, args: dict) -> dict:
    with httpx.Client(base_url=BASE, timeout=60) as client:
        if name == "search":
            return client.post(
                "/v1/search", json={"game": args["game"], "query": args["query"], "limit": 5}
            ).json()
        if name == "similar":
            return client.post(
                "/v1/similar",
                json={
                    "game": args["game"],
                    "query": args["card"],
                    "top_k": 5,
                    "mode": args.get("mode", "union"),
                },
            ).json()
        if name == "autocomplete":
            return client.get(
                "/v1/cards", params={"game": args["game"], "prefix": args["prefix"], "limit": 5}
            ).json()
        if name == "card_info":
            return client.get(f"/v1/cards/{args['card']}", params={"game": args["game"]}).json()
        if name == "legality":
            return client.get(
                f"/v1/cards/{args['card']}/legality", params={"game": args["game"]}
            ).json()
        if name == "graph_neighbors":
            return client.get(
                "/v1/graph/neighbors",
                params={
                    "game": args["game"],
                    "card": args["card"],
                    "relations": args.get("relations", "text,tag,cooccurrence"),
                    "limit": 5,
                },
            ).json()
        if name == "complete_deck":
            return client.post(
                "/v1/deck/complete",
                json={
                    "game": args["game"],
                    "deck_text": args["deck_text"],
                    "target_main_size": args.get("target", 30),
                    "max_steps": 5,
                    "method": "greedy",
                },
            ).json()
        if name == "index_status":
            return client.get("/v1/index/status").json()
    return {"error": f"unknown tool {name}"}


def main() -> int:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("OPENROUTER_API_KEY missing", file=sys.stderr)
        return 2
    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior API reviewer dogfooding DeckSage as an autonomous agent. "
                "Call the tools, do not guess. Be opinionated: name missing capabilities, "
                "awkward contracts, inconsistent shapes, and latency traps. "
                "Then give 5 concrete fixes ranked by impact. Max 350 words."
            ),
        },
        {
            "role": "user",
            "content": (
                "Audit the DeckSage API by using it. At minimum: search an exact card and an effect; "
                "similar in three modes; card info and legality; graph neighbours; complete a deck from text; "
                "index status. Note anything that made tool use harder than it should be."
            ),
        },
    ]
    transcript = []
    with httpx.Client(timeout=90) as client:
        for _ in range(8):
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": messages,
                    "tools": tool_schemas(),
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            messages.append(message)
            calls = message.get("tool_calls") or []
            if not calls:
                answer = message.get("content") or ""
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(answer + "\n", encoding="utf-8")
                print(answer)
                return 0
            for call in calls:
                name = call["function"]["name"]
                args = json.loads(call["function"].get("arguments") or "{}")
                result = call_tool(name, args)
                transcript.append({"tool": name, "args": args, "result": result})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps(result)[:6000],
                    }
                )
    print("agent did not finish within 8 steps", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
