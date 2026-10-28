#!/usr/bin/env python3
"""Prepare a blinded, reproducible review sample without altering source data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ml.annotation.card_context import load_card_context
from ml.contracts.annotations import is_evaluation_record


FIELDS = {"substitute": "functional_score", "synergy": "synergy_score", "meta": "meta_relevance"}


def sample_game(data: dict, game: str, contexts: dict[str, str], seed: int) -> tuple[list, list]:
    """Draw a random reserve then a score-stratified diagnostic sample.

    The sampling unit is an eligible pair-task, but each unordered pair is
    used at most once. The reserve is drawn before the diagnostic sample.
    """
    rng = random.Random(seed)
    pool = []
    for query, entry in sorted(data.get("queries", {}).items()):
        for ann in entry.get("annotations", []):
            candidate = ann.get("candidate")
            if (
                not candidate
                or query == candidate
                or query not in contexts
                or candidate not in contexts
            ):
                continue
            if not is_evaluation_record(ann):
                continue
            for task, field in FIELDS.items():
                if ann.get("task") not in (None, task):
                    continue
                value = ann.get(field)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if not math.isfinite(value) or not 0 <= value <= 1:
                    continue
                band = "low" if value < 0.3 else "mid" if value < 0.7 else "high"
                pool.append((query, candidate, task, field, float(value), band))
    pool.sort()
    rng.shuffle(pool)
    selected = []
    used = set()

    def add(row, group):
        pair = frozenset(row[:2])
        if pair in used:
            return False
        used.add(pair)
        selected.append((row, group))
        return True

    for row in pool:
        if len(selected) == 9:
            break
        add(row, "random_reserve")
    for task in FIELDS:
        for band in ("low", "mid", "high"):
            count = 0
            for row in pool:
                if row[2] == task and row[5] == band and add(row, "score_stratified"):
                    count += 1
                    if count == 3:
                        break
    rng.shuffle(selected)
    review, ledger = [], []
    for index, (row, group) in enumerate(selected, 1):
        query, candidate, task, field, value, band = row
        item_id = f"{game}-{index:03d}"
        review.append(
            {
                "id": item_id,
                "game": game,
                "task": task,
                "query": query,
                "candidate": candidate,
                "query_context": contexts[query],
                "candidate_context": contexts[candidate],
                "human_score": None,
                "reviewer": None,
                "reasoning": None,
            }
        )
        ledger.append(
            {
                "id": item_id,
                "selection": group,
                "score_field": field,
                "judge_score": value,
                "score_band": band,
            }
        )
    return review, ledger


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, required=True, help="new directory")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    review, ledger, sources = [], [], {}
    for offset, game in enumerate(("magic", "pokemon", "yugioh")):
        path = args.data_dir / "test_sets" / f"annotated_{game}_v2.json"
        raw = path.read_bytes()
        contexts = load_card_context(args.data_dir, game)
        if not contexts:
            raise ValueError(f"no card context available for {game}")
        rows, records = sample_game(json.loads(raw), game, contexts, args.seed + offset)
        review.extend(rows)
        ledger.extend(records)
        candidates = [args.data_dir / "processed" / f"card_attributes_{game}_enriched.csv"]
        if game == "magic":
            candidates.append(args.data_dir / "processed" / "card_attributes_enriched.csv")
        candidates.append(args.data_dir / "processed" / f"card_attributes_{game}.csv")
        context_path = next(p for p in candidates if p.is_file())
        sources[game] = {
            "evaluation": str(path),
            "evaluation_sha256": hashlib.sha256(raw).hexdigest(),
            "context": str(context_path),
            "context_sha256": hashlib.sha256(context_path.read_bytes()).hexdigest(),
            "selected": len(rows),
        }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "review.json").write_text(
        json.dumps(review, indent=2, ensure_ascii=False) + "\n"
    )
    manifest = {
        "seed": args.seed,
        "sources": sources,
        "records": ledger,
        "method": "9 random pair-task draws then up to 3 per task and score band; unique unordered pairs",
        "note": "Unreviewed; diagnostic sample is not representative or gold.",
    }
    (args.output_dir / "private_selection_ledger.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"prepared {len(review)} unreviewed items in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
