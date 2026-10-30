#!/usr/bin/env python3
"""Write gated copies of the evaluation test sets; never touch the originals.

Removes only records that fire a *blocking* structural rule: a card judged
against itself, a creature judged against a Trainer/Energy/Spell/Trap as a
substitute, and different Pokemon evolution stages treated as substitutes.
Cross-type substitutes, duplicate rounds, bucket mismatches and evidence-poor
records are left in place and stay visible to the screen.

Each output is a copy. The ledger records input and output hashes, every removal
with its query and score, and the rule that fired, so a reviewer can disagree
with any single drop without reconstructing it from a diff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _screen_module():
    from ml.evaluation.label_gate import _load_screen

    module = _load_screen()
    if module is None:
        raise SystemExit("screen_contradictions.py not found")
    return module


def _key(card_a: str, card_b: str, score: float) -> tuple[str, str, float]:
    return (card_a.strip().casefold(), card_b.strip().casefold(), round(float(score), 6))


def blocking_keys(path: Path, module, lookup) -> tuple[dict[tuple[str, str, float], str], int]:
    """Map (query, candidate, score) -> rule id for blocking hits; count records."""
    records = [r for r in module.load_records(path) if not module.is_ineligible(r)]
    hits = module.screen_records(records, lookup)
    blocking = [h for h in hits if h.rule_id in _BLOCKING]
    keys: dict[tuple[str, str, float], str] = {}
    for hit in blocking:
        if hit.score is None:
            continue
        keys.setdefault(_key(hit.card_a, hit.card_b, hit.score), hit.rule_id)
    return keys, len(records)


from ml.evaluation.label_gate import BLOCKING_RULES as _BLOCKING


def _score_of(annotation: dict[str, Any], module=None) -> float | None:
    """Use the screen's own resolver so removal matches what the screen judged.

    Reading fields in a different order silently under-removes: a record with
    functional_score 0.2 and similarity_score 0.902 was screened on 0.902, so a
    functional-first resolver built keys that never matched the hit.
    """
    if module is not None:
        resolved = module.resolve_score(annotation)
        if isinstance(resolved, (int, float)) and not isinstance(resolved, bool):
            return float(resolved)
    for field in ("similarity_score", "score", "similarity", "functional_score", "relevance_score"):
        value = annotation.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def repair_game(game: str, source: Path, output: Path, module, lookup) -> dict[str, Any]:
    keys, examined = blocking_keys(source, module, lookup)
    raw = source.read_bytes()
    data = json.loads(raw)

    removed: list[dict[str, Any]] = []
    for query, entry in data.get("queries", {}).items():
        annotations = entry.get("annotations")
        if not isinstance(annotations, list):
            continue
        kept = []
        for annotation in annotations:
            if not isinstance(annotation, dict):
                kept.append(annotation)
                continue
            candidate = annotation.get("candidate") or annotation.get("card") or ""
            score = _score_of(annotation, module)
            rule = None
            if score is not None:
                left_names = {
                    str(query),
                    str(annotation.get("card", "")),
                    str(annotation.get("card_a", "")),
                }
                rule = next(
                    (
                        keys[_key(left, str(candidate), score)]
                        for left in left_names
                        if _key(left, str(candidate), score) in keys
                    ),
                    None,
                )
            if rule is None:
                kept.append(annotation)
                continue
            removed.append(
                {
                    "query": query,
                    "candidate": candidate,
                    "score": score,
                    "rule": rule,
                    "task": annotation.get("task"),
                    "reason": "structurally contradictory with shipped card metadata",
                }
            )
        entry["annotations"] = kept
        dropped_here = {str(r["candidate"]) for r in removed if r["query"] == query}
        if dropped_here and isinstance(entry.get("bucket"), list):
            entry["bucket"] = [name for name in entry["bucket"] if name not in dropped_here]

    output_bytes = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode()
    output.write_bytes(output_bytes)
    return {
        "game": game,
        "source": str(source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "output": str(output),
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "examined": examined,
        "removed": len(removed),
        "rules": dict(Counter(r["rule"] for r in removed)),
        "records": removed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--test-set-dir", type=Path, default=PROJECT_ROOT / "data" / "test_sets")
    parser.add_argument("--games", nargs="+", default=["magic", "pokemon", "yugioh"])
    parser.add_argument("--metadata-dir", type=Path, default=PROJECT_ROOT / "data" / "processed")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    module = _screen_module()
    lookup, _ledger = module.load_metadata(args.metadata_dir)
    if not any(lookup.values()):
        raise SystemExit("no card metadata; refusing to repair without it")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for game in args.games:
        source = args.test_set_dir / f"annotated_{game}_v2.json"
        if not source.exists():
            print(f"{game}: missing {source.name}, skipped")
            continue
        output = args.out_dir / f"annotated_{game}_v2.json"
        if args.dry_run:
            keys, examined = blocking_keys(source, module, lookup)
            print(f"{game}: would remove {len(keys)} blocking records of {examined}")
            continue
        total = 0
        rules: dict[str, int] = {}
        current = source
        for _pass in range(5):
            staged = args.out_dir / f".{game}.pass{_pass}.json"
            entry = repair_game(game, current, staged, module, lookup)
            total += entry["removed"]
            for rule, count in entry["rules"].items():
                rules[rule] = rules.get(rule, 0) + count
            staged.replace(output)
            if entry["removed"] == 0:
                break
            current = output
        remaining = len(blocking_keys(output, module, lookup)[0]) if output.exists() else -1
        summary.append(
            {
                "game": game,
                "source": str(source),
                "output": str(output),
                "removed": total,
                "rules": rules,
                "blocking_remaining": remaining,
            }
        )
        print(f"{game}: removed {total} ({rules}), blocking remaining {remaining}")

    if not args.dry_run:
        ledger = {
            "purpose": "Remove structurally contradictory judgments from evaluation copies",
            "blocking_rules": sorted(_BLOCKING),
            "games": summary,
        }
        ledger_path = args.out_dir / "ledger.json"
        ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n")
        print(f"ledger: {ledger_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
