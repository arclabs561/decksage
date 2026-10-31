#!/usr/bin/env python3
"""Annotate a fixed pair list with OpenRouter judges, resumably.

The key is read from the process environment only. Do not call
``load_dotenv()`` here: the repo's ``.env`` carries a stale copy that returns
401 "User not found", while the launcher-injected ``OPENROUTER_API_KEY`` works.
Overriding the environment with that file is what produced the false "labeling
is blocked" conclusion.

Usage:
    scripts/annotation/annotate_pairs_openrouter.py \
        --pairs data-local/human-review-20261031-reprints/review.json \
        --output data/annotations/refined/reprint_llm_labels.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "annotation"))

# Importing multi_model_annotate loads the project .env; keep the launcher's
# working key, since the file copy can be stale (it was, and returned 401).
_WORKING_KEY = os.environ.get("OPENROUTER_API_KEY", "")
from multi_model_annotate import build_annotation_prompt


if _WORKING_KEY:
    os.environ["OPENROUTER_API_KEY"] = _WORKING_KEY

DEFAULT_MODELS = [
    ("anthropic/claude-sonnet-4-6", "claude_sonnet_4_6"),
    ("openai/gpt-5.2", "gpt_5_2"),
    ("google/gemini-2.5-flash", "gemini_2_5_flash"),
]
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


async def judge(
    session: Any,
    model: str,
    prompt: str,
    semaphore: asyncio.Semaphore,
    retries: int = 3,
) -> dict[str, float] | None:
    async with semaphore:
        for attempt in range(retries):
            try:
                response = await asyncio.to_thread(
                    session.post,
                    ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a card game expert. Respond with JSON only.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 500,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=60,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"].strip()
                start, end = content.find("{"), content.rfind("}") + 1
                parsed = json.loads(content[start:end])
                scores = {k: float(parsed[k]) for k in ("similarity_score", "functional_score")}
                if all(0 <= v <= 1 for v in scores.values()):
                    return scores
            except Exception as exc:
                if attempt == retries - 1:
                    print(f"  {model} failed: {exc}", file=sys.stderr)
                await asyncio.sleep(1.5 * (attempt + 1))
    return None


async def run(args: argparse.Namespace) -> int:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is not in the environment")
    pairs = json.loads(args.pairs.read_text(encoding="utf-8"))
    items = pairs.get("items", pairs)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict[str, Any]] = {}
    if output.exists():
        existing = {
            f"{row['query']}\u0000{row['candidate']}": row
            for row in json.loads(output.read_text(encoding="utf-8")).get("pairs", [])
        }

    models = [tuple(chunk.split("=", 1)) for chunk in args.models.split(",")]
    import requests

    session = requests.Session()
    session.trust_env = False
    semaphore = asyncio.Semaphore(args.concurrency)
    rows: list[dict[str, Any]] = []
    for item in items:
        query, candidate = item["query"], item["candidate"]
        key_ = f"{query}\u0000{candidate}"
        row = existing.get(key_, {"query": query, "candidate": candidate, "judges": {}})
        prompt = build_annotation_prompt(
            item.get("query_context", query), item.get("candidate_context", candidate), args.game
        )
        for model, short in models:
            if short in row["judges"]:
                continue
            scores = await judge(session, model, prompt, semaphore)
            if scores:
                row["judges"][short] = scores
        functional = [v["functional_score"] for v in row["judges"].values()]
        if functional:
            row["median_functional"] = round(statistics.median(functional), 4)
            row["spread"] = round(statistics.pstdev(functional), 4) if len(functional) > 1 else 0.0
            row["n_judges"] = len(functional)
        rows.append(row)
        output.write_text(
            json.dumps(
                {"version": "openrouter-pairs-v1", "game": args.game, "pairs": rows}, indent=1
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            f"{query} -> {candidate}: {row.get('median_functional')} ({row.get('n_judges')} judges)"
        )

    done = [r for r in rows if r.get("n_judges") == len(models)]
    print(f"\n{len(done)}/{len(rows)} pairs with all {len(models)} judges")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--game", default="magic")
    parser.add_argument(
        "--models",
        default=",".join(f"{model}={short}" for model, short in DEFAULT_MODELS),
        help="comma-separated model=short pairs",
    )
    parser.add_argument("--concurrency", type=int, default=6)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
