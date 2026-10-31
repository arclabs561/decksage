#!/usr/bin/env python3
"""Build one refined, deduplicated pair-label table per game.

Two corpora exist and do not overlap:

* ``data/annotations/{game}_*_v4.json`` — 2000 curated pairs with six judge
  verdicts each and a stored consensus.
* ``data/annotations/diverse_checkpoint_{game}.jsonl`` — ~20 judgments per pair
  over a disjoint pair set, one row per judge call.

Aggregating them expands the pair pool by roughly 2k pairs per game, and the
per-judge rows let us replace a single stored consensus with a robust median,
a spread, and an explicit confidence band. Nothing is relabelled by a model
here: this is a deterministic reduction of judgments that already exist.

Outputs (deterministic for fixed inputs):

* ``data/annotations/refined/{game}_pairs.json`` — one record per pair.
* ``data/results/label_refinement.json`` — counts, flags, judge reliability.
* ``data/annotations/refined/{game}_review_queue.json`` — pairs whose median
  sits near the decision boundary, worst first, for the next human/LLM batch.

Usage:
    scripts/annotation/build_refined_pair_labels.py
    scripts/annotation/build_refined_pair_labels.py --game magic
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANNOTATIONS = PROJECT_ROOT / "data" / "annotations"
REFINED = ANNOTATIONS / "refined"
AUDIT_PATH = PROJECT_ROOT / "data" / "results" / "label_refinement.json"

BANDS = (
    ("highly_relevant", 0.70),
    ("relevant", 0.50),
    ("somewhat_relevant", 0.30),
    ("marginally_relevant", 0.15),
    ("irrelevant", 0.0),
)

# Below this many judges a pair is flagged; a single verdict is not a label.
MIN_JUDGES = 3


def band_of(score: float) -> str:
    for name, floor in BANDS:
        if score >= floor:
            return name
    return "irrelevant"


def judge_key(row: dict[str, Any]) -> str:
    raw = str(row.get("llm_model") or row.get("judge") or "unknown")
    return raw.rsplit("/", 1)[-1].replace("-", "_").replace(".", "_").lower()


def numeric(row: dict[str, Any]) -> float | None:
    for field in ("similarity_score", "functional_score", "score"):
        value = row.get(field)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_v4(game: str) -> tuple[dict[tuple[str, str], dict[str, Any]], Path]:
    matches = sorted(ANNOTATIONS.glob(f"{game}_*_v4.json"))
    if not matches:
        raise SystemExit(f"no v4 annotation file for {game}")
    path = matches[-1]
    payload = json.loads(path.read_text(encoding="utf-8"))
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for label in payload.get("labels", []):
        key = (str(label.get("card1")), str(label.get("card2")))
        if not all(key):
            continue
        scores = {}
        subs = {}
        for judge, verdict in (label.get("per_judge") or {}).items():
            value = numeric(verdict)
            name = judge.rsplit("/", 1)[-1].replace("-", "_").lower()
            if value is not None:
                scores[name] = value
                subs[name] = bool(verdict.get("is_substitute"))
        pairs[key] = {
            "stored_consensus": (label.get("consensus") or {}).get("similarity_score"),
            "stored_substitute": (label.get("consensus") or {}).get("is_substitute"),
            "stored_agreement": label.get("agreement_level"),
            "judges": scores,
            "substitutes": subs,
        }
    return pairs, path


def load_checkpoint(game: str) -> tuple[dict[tuple[str, str], dict[str, Any]], Path, int]:
    path = ANNOTATIONS / f"diverse_checkpoint_{game}.jsonl"
    if not path.exists():
        raise SystemExit(f"no checkpoint for {game}")
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    rows = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows += 1
        key = (str(row.get("query")), str(row.get("candidate")))
        if not all(key):
            continue
        score = numeric(row)
        if score is None:
            continue
        pair = pairs.setdefault(key, {"judges": {}, "substitutes": {}})
        # A judge may appear once per prompt variant; average its variants and
        # take its majority substitute vote.
        pair["judges"].setdefault(judge_key(row), []).append(score)
        pair["substitutes"].setdefault(judge_key(row), []).append(bool(row.get("is_substitute")))
    return pairs, path, rows


def merge(
    v4: dict[tuple[str, str], dict[str, Any]],
    checkpoint: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for key in sorted(set(v4) | set(checkpoint)):
        scores: dict[str, float] = {}
        subs: dict[str, list[bool]] = {}
        sources = []
        stored = {}
        if key in v4:
            sources.append("v4")
            scores.update(v4[key]["judges"])
            for judge, verdict in v4[key]["substitutes"].items():
                subs.setdefault(judge, []).append(verdict)
            stored = {
                "consensus": v4[key]["stored_consensus"],
                "is_substitute": v4[key]["stored_substitute"],
                "agreement": v4[key]["stored_agreement"],
            }
        if key in checkpoint:
            sources.append("diverse")
            for judge, values in checkpoint[key]["judges"].items():
                scores.setdefault(judge, statistics.fmean(values))
            for judge, votes in checkpoint[key]["substitutes"].items():
                subs.setdefault(judge, []).extend(votes)

        if not scores:
            continue
        values = list(scores.values())
        per_judge_sub = [sum(votes) / len(votes) >= 0.5 for votes in subs.values() if votes]
        substitute_total = len(per_judge_sub)
        substitute_votes = sum(1 for vote in per_judge_sub if vote)
        median = statistics.median(values)
        spread = statistics.pstdev(values) if len(values) > 1 else 0.0
        flags: list[str] = []
        if len(values) < MIN_JUDGES:
            flags.append("few_judges")
        if spread >= 0.25:
            flags.append("high_spread")
        substitute = substitute_votes / substitute_total >= 0.5 if substitute_total else False
        if substitute and median < 0.3:
            flags.append("substitute_low_score")
        if not substitute and median >= 0.5:
            flags.append("high_score_not_substitute")
        if stored.get("consensus") is not None and band_of(float(stored["consensus"])) != band_of(
            median
        ):
            flags.append("bucket_flip")

        records.append(
            {
                "query": key[0],
                "candidate": key[1],
                "median_score": round(median, 4),
                "mean_score": round(statistics.fmean(values), 4),
                "score_std": round(spread, 4),
                "n_judges": len(values),
                "is_substitute": substitute,
                "substitute_vote_share": round(substitute_votes / substitute_total, 4)
                if substitute_total
                else 0.0,
                "band": band_of(median),
                "confidence": "high"
                if len(values) >= 4 and spread <= 0.15
                else "medium"
                if len(values) >= 3 and spread <= 0.25
                else "low",
                "sources": sources,
                "stored": stored,
                "flags": flags,
            }
        )
    return records


def uncertainty(pair: dict[str, Any]) -> float:
    """Rank review candidates: boundary proximity, then spread, then scarcity."""
    return abs(pair["median_score"] - 0.5) - pair["score_std"] - 0.05 * pair["n_judges"]


def summarise(game: str, records: list[dict[str, Any]], sources: dict[str, Any]) -> dict[str, Any]:
    flags = Counter(flag for record in records for flag in record["flags"])
    return {
        "game": game,
        "pairs": len(records),
        "sources": sources,
        "bands": dict(sorted(Counter(r["band"] for r in records).items())),
        "confidence": dict(sorted(Counter(r["confidence"] for r in records).items())),
        "substitutes": sum(1 for r in records if r["is_substitute"]),
        "flags": dict(sorted(flags.items())),
        "median_spread": round(statistics.median(r["score_std"] for r in records), 4),
        "new_pairs": sum(1 for r in records if r["sources"] == ["diverse"]),
        "shared_pairs": sum(1 for r in records if len(r["sources"]) == 2),
    }


def judge_reliability(records: list[dict[str, Any]], checkpoint_path: Path) -> dict[str, Any]:
    """Mean absolute deviation of each judge from the pair median."""
    deviations: dict[str, list[float]] = defaultdict(list)
    medians = {(r["query"], r["candidate"]): r["median_score"] for r in records}
    for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (str(row.get("query")), str(row.get("candidate")))
        score = numeric(row)
        if score is None or key not in medians:
            continue
        deviations[judge_key(row)].append(abs(score - medians[key]))
    return {
        judge: {
            "n": len(values),
            "mean_abs_deviation": round(statistics.fmean(values), 4),
        }
        for judge, values in sorted(deviations.items())
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", action="append", choices=("magic", "pokemon", "yugioh"))
    parser.add_argument("--review-depth", type=int, default=100)
    args = parser.parse_args()

    games = args.game or ["magic", "pokemon", "yugioh"]
    REFINED.mkdir(parents=True, exist_ok=True)
    audit: dict[str, Any] = {"version": "refined-v1", "games": {}}

    for game in games:
        v4, v4_path = load_v4(game)
        checkpoint, checkpoint_path, rows = load_checkpoint(game)
        records = merge(v4, checkpoint)
        sources = {
            "v4": {
                "path": str(v4_path.relative_to(PROJECT_ROOT)),
                "pairs": len(v4),
                "sha256": sha256(v4_path),
            },
            "diverse": {
                "path": str(checkpoint_path.relative_to(PROJECT_ROOT)),
                "pairs": len(checkpoint),
                "rows": rows,
                "sha256": sha256(checkpoint_path),
            },
        }
        summary = summarise(game, records, sources)
        summary["judge_reliability"] = judge_reliability(records, checkpoint_path)

        output = {
            "version": "refined-v1",
            "game": game,
            "sources": sources,
            "summary": {k: v for k, v in summary.items() if k != "judge_reliability"},
            "pairs": records,
        }
        (REFINED / f"{game}_pairs.json").write_text(
            json.dumps(output, indent=1, sort_keys=False) + "\n", encoding="utf-8"
        )

        queue = sorted(records, key=uncertainty)[: args.review_depth]
        queue_payload = {
            "version": "review-queue-v1",
            "game": game,
            "criterion": "abs(median-0.5) - score_std - 0.05*n_judges, ascending",
            "pairs": queue,
        }
        (REFINED / f"{game}_review_queue.json").write_text(
            json.dumps(queue_payload, indent=1) + "\n", encoding="utf-8"
        )
        audit["games"][game] = summary
        print(
            f"{game}: {summary['pairs']} pairs "
            f"({summary['new_pairs']} new, {summary['substitutes']} substitutes), "
            f"flags={summary['flags']}"
        )

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
