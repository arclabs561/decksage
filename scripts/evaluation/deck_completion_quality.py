#!/usr/bin/env python3
"""0088: does the mode deck completion uses change the quality of its cards?

The stock evaluation only checks size, copy limits, colours and a bad-card
list, which every arm passes. This scores the *added* cards against judged
functional labels for the seed cards, so the comparison can actually fail.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "evaluation") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from eval_deck_completion import SEED_DECKS

from ml.utils.paths import PATHS


TEST_SET = PATHS.data / "test_sets" / "annotated_magic_v2.json"
OUT = PATHS.data / "results" / "deck_completion_quality_0088.json"


def judged_scores() -> dict[tuple[str, str], float]:
    data = json.loads(TEST_SET.read_text())["queries"]
    scores: dict[tuple[str, str], float] = {}
    for query, entry in data.items():
        for annotation in entry.get("annotations", []):
            candidate = annotation.get("candidate")
            value = annotation.get("functional_score")
            if candidate and isinstance(value, (int, float)):
                scores[(query, candidate)] = float(value)
    return scores


def complete(base_url: str, seed: list[str], mode: str | None, target: int = 60) -> list[str]:
    body: dict[str, object] = {
        "game": "magic",
        "deck": {"Main": seed},
        "target_main_size": target,
        "method": "greedy",
    }
    if mode:
        body["mode"] = mode
    response = httpx.post(f"{base_url}/v1/deck/complete", json=body, timeout=300)
    response.raise_for_status()
    payload = response.json()
    names = []
    for step in payload.get("steps", []):
        name = step.get("card") or step.get("name")
        if name:
            names.append(name)
    if not names:
        deck = payload.get("deck") or {}
        partitions = deck.get("partitions") or []
        for partition in partitions:
            for card in partition.get("cards", []):
                name = card.get("name")
                if name and name not in seed:
                    names.append(name)
    return [name for name in names if name not in seed]


def evaluate(base_url: str, mode: str | None) -> dict:
    scores = judged_scores()
    per_deck = []
    all_values: list[float] = []
    judged_pairs = 0
    added = 0
    for deck in SEED_DECKS["magic"]:
        cards = complete(base_url, deck["seed"], mode)
        values: list[float] = []
        for card in cards:
            for seed_card in deck["seed"]:
                score = scores.get((seed_card, card))
                if score is None:
                    continue
                values.append(score)
                judged_pairs += 1
        added += len(cards)
        all_values.extend(values)
        per_deck.append(
            {
                "deck": deck["name"],
                "added": len(cards),
                "judged_pairs": len(values),
                "mean_score": round(sum(values) / len(values), 4) if values else None,
                "cards": cards,
            }
        )
    mean = round(sum(all_values) / len(all_values), 4) if all_values else None
    return {
        "mode": mode or "default",
        "added": added,
        "judged_pairs": judged_pairs,
        "coverage": round(judged_pairs / added, 4) if added else 0.0,
        "mean_functional_score": mean,
        "per_deck": per_deck,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--modes", default="embedding,text")
    args = parser.parse_args()

    arms = {mode.strip(): evaluate(args.api_url, mode.strip()) for mode in args.modes.split(",")}
    payload = {"arms": arms}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    for mode, result in arms.items():
        print(
            f"{mode}: mean={result['mean_functional_score']} "
            f"coverage={result['coverage']} pairs={result['judged_pairs']} "
            f"added={result['added']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
