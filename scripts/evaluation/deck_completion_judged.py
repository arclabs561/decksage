#!/usr/bin/env python3
"""0089: judged functional score for deck completion, on (seed deck, added card) pairs.

0088 scored completion's added cards against ``data/test_sets/annotated_magic_v2.json``,
which is keyed on retrieval queries, so 0 of 45 (embedding) and 4 of 45 (text) added
cards had a label. This harness builds the missing surface: for each magic seed deck
it runs completion in both candidate modes, samples added cards, and asks three
OpenRouter judges the completion question directly -- does this card fill a role the
seed deck needs?

Judging reuses ``scripts/annotation/annotate_pairs_openrouter.py`` (its ``judge``
call and its aggregation convention: median across judges, pstdev spread, n_judges),
and the guardrails reuse ``scripts/evaluation/eval_deck_completion.py``'s copy
limits, target sizes and extractor. Only the prompt is new, because the pair prompt
asks about similarity between two cards, not about fit to a deck.

Raw judgments go to data-local (untracked); the compact summary goes to
data/results (tracked).

Usage:
    uv run python scripts/evaluation/deck_completion_judged.py
    uv run python scripts/evaluation/deck_completion_judged.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[2]
for extra in (ROOT / "scripts" / "evaluation", ROOT / "scripts" / "annotation", ROOT / "src"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from annotate_pairs_openrouter import DEFAULT_MODELS, judge
from eval_deck_completion import COPY_LIMITS, SEED_DECKS, TARGET_SIZES, extract_cards

from ml.annotation.card_context import load_card_context


GAME = "magic"
ARMS = ("embedding", "text")
TARGET_SIZE = TARGET_SIZES[GAME]
COPY_LIMIT = COPY_LIMITS[GAME]
DATA_DIR = ROOT / "data"
RAW_DIR = ROOT / "data-local" / "deck-completion-judged-20261101"
RAW_OUT = RAW_DIR / "judgments.json"
SUMMARY_OUT = DATA_DIR / "results" / "deck_completion_judged_20261101.json"

PROMPT_VERSION = "deck_fit_v1"
# 0088's pre-registered threshold, restated so the script can compute the verdict.
MIN_DELTA = 0.02
MIN_COVERAGE = 0.30

PROMPT = """Does this card fill a role the seed deck needs?

Seed deck ({game}): the deck currently contains only these cards, and the deck
builder asked for help completing it.

{seed_context}

Candidate card:
{candidate_context}

Judge the CANDIDATE as a completion of the SEED DECK, not as a copy of any one
seed card. A card can fit by filling a missing role (mana base, removal,
card advantage, a threat at the top of the curve) even if it resembles no seed
card. Weigh colour identity, mana cost vs the rest of the curve, and whether
the deck has a use for the effect.

SCORING SCALE for functional_score (use the full range):
- 0.00: Wrong. Off-colour, or the deck can never use this effect.
- 0.20: Marginal. Legal but the deck has no role for it; a filler card.
- 0.40: Plausible. Fills a role the deck will eventually want, at some cost.
- 0.60: Good. Fills a real role at a reasonable cost for this deck.
- 0.80: Strong. Clearly needed role, on-colour, on-curve, efficient.
- 1.00: Ideal. Exactly the missing piece; a deck builder adds it immediately.

Also give similarity_score: how close the candidate is to a like-for-like
substitute for the existing seed cards (0.0 unrelated role, 1.0 interchangeable).
This is secondary; functional_score is what is being measured.

Do not assume a metagame, sideboard, or card pool beyond the cards shown.

Respond ONLY with JSON:
{{"functional_score": 0.0, "similarity_score": 0.0}}"""


# ---------------------------------------------------------------------------
# Completion and sampling
# ---------------------------------------------------------------------------


def complete(base_url: str, seed: list[str], mode: str) -> dict:
    body: dict[str, Any] = {
        "game": GAME,
        "deck": {"Main": seed},
        "target_main_size": TARGET_SIZE,
        "method": "greedy",
        "mode": mode,
    }
    # trust_env=False: a shell proxy in the environment must not intercept localhost.
    for attempt in range(5):
        try:
            with httpx.Client(trust_env=False, timeout=300) as client:
                response = client.post(f"{base_url}/v1/deck/complete", json=body)
            response.raise_for_status()
            return response.json()
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 4:
                raise
            time.sleep(min(5 * (attempt + 1), 20))
    raise RuntimeError("completion failed")


def added_cards(payload: dict, seed: list[str]) -> list[str]:
    """Added card names in step order (deduplicated), matching 0088's extraction."""
    names: list[str] = []
    for step in payload.get("steps", []):
        name = step.get("card") or step.get("name")
        if name and name not in seed and name not in names:
            names.append(name)
    if names:
        return names
    for partition in (payload.get("deck") or {}).get("partitions") or []:
        for card in partition.get("cards", []):
            name = card.get("name")
            if name and name not in seed and name not in names:
                names.append(name)
    return names


def stride_sample(cards: list[str], limit: int) -> list[str]:
    """Deterministic even-stride sample: covers the whole step order, not the head."""
    if len(cards) <= limit:
        return list(cards)
    step = len(cards) / limit
    picked = [cards[int(i * step)] for i in range(limit)]
    seen: list[str] = []
    for name in picked:
        if name not in seen:
            seen.append(name)
    return seen


def guardrails(payload: dict, seed_config: dict, metadata: dict[str, dict]) -> dict:
    """Size, copy, colour and bad-card checks, as eval_deck_completion.py defines them."""
    cards = extract_cards(payload)
    total = sum(count for _, count in cards)
    expected_colors = seed_config.get("expected_colors") or set()
    color_violations = []
    if expected_colors:
        for name, _count in cards:
            colors = (metadata.get(name) or {}).get("colors", "")
            if colors and colors not in ("", "nan"):
                card_colors = set(colors.replace(",", ""))
                if card_colors and not card_colors.issubset(expected_colors | {"C", ""}):
                    color_violations.append(name)
    bad_found = [name for name, _count in cards if name in seed_config.get("bad_cards", [])]
    return {
        "total_cards": total,
        "size_correct": total == TARGET_SIZE,
        "copy_violations": [name for name, count in cards if count > COPY_LIMIT],
        "color_violations": color_violations,
        "bad_cards": bad_found,
        "unique_cards": len(cards),
    }


# ---------------------------------------------------------------------------
# Judging
# ---------------------------------------------------------------------------


def build_prompt(seed_context: str, candidate_context: str) -> str:
    return PROMPT.format(
        game=GAME.upper(), seed_context=seed_context, candidate_context=candidate_context
    )


def deck_context(seed: list[str], context: dict[str, str]) -> str:
    lines = []
    for name in seed:
        lines.append(context.get(name) or f"Name: {name}\nText: (no card text available)")
    return "\n\n".join(lines)


async def judge_pairs(rows: list[dict], models: list[tuple[str, str]], concurrency: int) -> None:
    """Fill ``row['judges']`` for rows that still need judges (resumable)."""
    import requests

    session = requests.Session()
    session.trust_env = False
    semaphore = asyncio.Semaphore(concurrency)

    async def one(row: dict) -> None:
        prompt = build_prompt(row["seed_context"], row["candidate_context"])
        for model, short in models:
            if short in row["judges"]:
                continue
            scores = await judge(session, model, prompt, semaphore)
            if scores:
                row["judges"][short] = scores
            else:
                print(f"  {short} failed: {row['deck']} / {row['card']}", file=sys.stderr)

    await asyncio.gather(*(one(row) for row in rows))


def score_row(row: dict) -> None:
    functional = [v["functional_score"] for v in row["judges"].values()]
    if not functional:
        row["median_functional"] = None
        row["spread"] = None
        row["n_judges"] = 0
        return
    row["median_functional"] = round(statistics.median(functional), 4)
    row["spread"] = round(statistics.pstdev(functional), 4) if len(functional) > 1 else 0.0
    row["n_judges"] = len(functional)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def arm_summary(rows: list[dict], deck_info: dict[str, dict]) -> dict:
    judged = [row for row in rows if row.get("median_functional") is not None]
    values = [row["median_functional"] for row in judged]
    spreads = [row["spread"] for row in judged if row["spread"] is not None]
    added_total = sum(info["added"] for info in deck_info.values())
    per_deck = {}
    for deck, info in deck_info.items():
        deck_rows = [row for row in judged if row["deck"].split("|")[0] == deck]
        deck_values = [row["median_functional"] for row in deck_rows]
        per_deck[deck] = {
            "added": info["added"],
            "sampled": info["sampled"],
            "judged": len(deck_rows),
            "mean_functional": round(statistics.fmean(deck_values), 4) if deck_values else None,
            "sd_functional": round(statistics.pstdev(deck_values), 4)
            if len(deck_values) > 1
            else None,
            "mean_spread": round(statistics.fmean([r["spread"] for r in deck_rows]), 4)
            if deck_rows
            else None,
        }
    return {
        "added_cards": added_total,
        "sampled_cards": sum(info["sampled"] for info in deck_info.values()),
        "judged_cards": len(judged),
        "judgments": sum(row["n_judges"] for row in judged),
        "coverage": round(len(judged) / added_total, 4) if added_total else 0.0,
        "mean_functional_score": round(statistics.fmean(values), 4) if values else None,
        "sd_functional_score": round(statistics.pstdev(values), 4) if len(values) > 1 else None,
        "mean_judge_spread": round(statistics.fmean(spreads), 4) if spreads else None,
        # multi_model_annotate.py's confidence convention, applied to judge spread.
        "mean_confidence": round(statistics.fmean([max(0.0, 1.0 - s * 3) for s in spreads]), 4)
        if spreads
        else None,
        "per_deck": per_deck,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--per-deck-sample", type=int, default=12)
    parser.add_argument(
        "--models",
        default=",".join(f"{model}={short}" for model, short in DEFAULT_MODELS),
        help="comma-separated model=short pairs for the judge ensemble",
    )
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument(
        "--refresh-completions",
        action="store_true",
        help="ignore data-local/completions.json and re-call /v1/deck/complete",
    )
    parser.add_argument("--dry-run", action="store_true", help="no LLM calls; write prompt sample")
    args = parser.parse_args()

    models = [tuple(chunk.split("=", 1)) for chunk in args.models.split(",")]
    context = load_card_context(DATA_DIR, GAME)
    metadata = {name: dict(row) for name, row in _load_metadata().items()}

    deck_info: dict[str, dict] = {}
    arm_rows: dict[str, list[dict]] = {arm: [] for arm in ARMS}
    arm_guardrails: dict[str, dict] = {arm: {} for arm in ARMS}

    # Completion payloads are cached: the API is shared with a profiling session and
    # restarts under load, so a refetch per run would make the judged set unstable.
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = RAW_DIR / "completions.json"
    cache: dict[str, dict] = {}
    if cache_path.exists() and not args.refresh_completions:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

    for seed_config in SEED_DECKS[GAME]:
        seed = seed_config["seed"]
        seed_context = deck_context(seed, context)
        for arm in ARMS:
            key = f"{seed_config['name']}|{arm}"
            cached = cache.get(key)
            if cached is None or args.refresh_completions:
                payload = complete(args.api_url, seed, arm)
                cached = {
                    "added": added_cards(payload, seed),
                    "guardrails": guardrails(payload, seed_config, metadata),
                    "steps": len(payload.get("steps", [])),
                    "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
                cache[key] = cached
                cache_path.write_text(json.dumps(cache, indent=1) + "\n", encoding="utf-8")
            cards = cached["added"]
            sampled = stride_sample(cards, args.per_deck_sample)
            deck_info[key] = {"added": len(cards), "sampled": len(sampled)}
            arm_guardrails[arm][seed_config["name"]] = cached["guardrails"]
            for card in sampled:
                arm_rows[arm].append(
                    {
                        "deck": key,
                        "arm": arm,
                        "seed": seed,
                        "card": card,
                        "seed_context": seed_context,
                        "candidate_context": context.get(card)
                        or f"Name: {card}\nText: (no card text available)",
                        "judges": {},
                    }
                )

    rows = [row for arm in ARMS for row in arm_rows[arm]]
    if args.dry_run:
        print(build_prompt(rows[0]["seed_context"], rows[0]["candidate_context"]))
        print(f"\n{len(rows)} pairs x {len(models)} judges = {len(rows) * len(models)} judgments")
        return 0

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_OUT.exists():
        existing = json.loads(RAW_OUT.read_text(encoding="utf-8"))
        prior = {f"{r['deck']}\u0000{r['card']}": r for r in existing.get("pairs", [])}
        for row in rows:
            previous = prior.get(f"{row['deck']}\u0000{row['card']}")
            if previous and previous.get("judges"):
                row["judges"] = previous["judges"]

    asyncio.run(judge_pairs(rows, models, args.concurrency))
    for row in rows:
        score_row(row)

    payload = {
        "version": "deck-completion-judged-v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "game": GAME,
        "prompt_version": PROMPT_VERSION,
        "models": [{"model": model, "short": short} for model, short in models],
        "target_size": TARGET_SIZE,
        "per_deck_sample": args.per_deck_sample,
        "pairs": [
            {
                key: row[key]
                for key in (
                    "deck",
                    "arm",
                    "seed",
                    "card",
                    "judges",
                    "median_functional",
                    "spread",
                    "n_judges",
                )
            }
            for row in rows
        ],
    }
    RAW_OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")

    by_arm = {
        arm: arm_summary([r for r in rows if r["arm"] == arm], _arm_deck_info(deck_info, arm))
        for arm in ARMS
    }
    for arm in ARMS:
        by_arm[arm]["guardrails"] = _guardrail_summary(arm_guardrails[arm])

    embedding_mean = by_arm["embedding"]["mean_functional_score"]
    text_mean = by_arm["text"]["mean_functional_score"]
    delta = (
        round(text_mean - embedding_mean, 4) if None not in (text_mean, embedding_mean) else None
    )
    coverage_ok = all(by_arm[arm]["coverage"] >= MIN_COVERAGE for arm in ARMS)
    guardrail_ok = not _guardrail_regression(
        by_arm["embedding"]["guardrails"], by_arm["text"]["guardrails"]
    )
    if delta is None:
        verdict = "inconclusive_no_judgments"
    elif delta >= MIN_DELTA and coverage_ok and guardrail_ok:
        verdict = "text_replaces_default"
    else:
        verdict = "default_stays_embedding"

    summary = {
        "experiment": "0089",
        "generated_at": payload["generated_at"],
        "game": GAME,
        "prompt_version": PROMPT_VERSION,
        "models": payload["models"],
        "threshold": {
            "min_delta": MIN_DELTA,
            "min_coverage": MIN_COVERAGE,
            "guardrail_rule": "no size, copy, colour or bad-card regression",
        },
        "arms": by_arm,
        "comparison": {
            "delta_text_minus_embedding": delta,
            "coverage_ok": coverage_ok,
            "guardrail_ok": guardrail_ok,
            "verdict": verdict,
        },
        "raw_artifact": str(RAW_OUT.relative_to(ROOT)),
    }
    SUMMARY_OUT.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    for arm in ARMS:
        result = by_arm[arm]
        print(
            f"{arm}: mean={result['mean_functional_score']} coverage={result['coverage']} "
            f"judged={result['judged_cards']}/{result['added_cards']} "
            f"spread={result['mean_judge_spread']} judgments={result['judgments']}"
        )
    print(f"delta(text-embedding)={delta} verdict={verdict}")
    return 0


def _load_metadata() -> dict[str, dict]:
    import csv

    path = DATA_DIR / "processed" / f"card_attributes_{GAME}_enriched.csv"
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {row.get("name", "").strip(): dict(row) for row in csv.DictReader(handle)}


def _arm_deck_info(deck_info: dict[str, dict], arm: str) -> dict[str, dict]:
    return {
        key.split("|", 1)[0]: info for key, info in deck_info.items() if key.endswith(f"|{arm}")
    }


def _guardrail_summary(per_deck: dict[str, dict]) -> dict:
    return {
        "size_correct": f"{sum(1 for g in per_deck.values() if g['size_correct'])}/{len(per_deck)}",
        "copy_violations": sum(len(g["copy_violations"]) for g in per_deck.values()),
        "color_violations": sum(len(g["color_violations"]) for g in per_deck.values()),
        "bad_cards": sum(len(g["bad_cards"]) for g in per_deck.values()),
        "per_deck": per_deck,
    }


def _guardrail_regression(before: dict, after: dict) -> list[str]:
    """Names of guardrails that got worse from ``before`` (embedding) to ``after`` (text)."""
    regressions = []
    if after["size_correct"] != before["size_correct"]:
        if after["size_correct"].split("/")[0] < before["size_correct"].split("/")[0]:
            regressions.append("size_correct")
    for key in ("copy_violations", "color_violations", "bad_cards"):
        if after[key] > before[key]:
            regressions.append(key)
    return regressions


if __name__ == "__main__":
    raise SystemExit(main())
