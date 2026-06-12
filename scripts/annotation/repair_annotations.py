#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.26.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""
Repair deflated/broken annotations in test sets.

Identifies annotations from models known to produce bad scores (e.g., ollama
8B with 54-97% zeros) and either removes them or flags them for re-annotation.

Usage:
    # Audit: show what would be removed
    uv run scripts/annotation/repair_annotations.py audit --game magic

    # Remove zero-score annotations from broken models
    uv run scripts/annotation/repair_annotations.py remove-zeros --game magic

    # Remove all annotations from a specific model
    uv run scripts/annotation/repair_annotations.py remove-model --game magic --model ollama/llama3.2

    # Re-score with multi-model cascade (replaces bad annotations)
    uv run scripts/annotation/repair_annotations.py reannotate --game magic --budget 200
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=True)
DATA_DIR = PROJECT_ROOT / "data"

# Models known to produce bad annotations
BAD_MODELS = {
    "ollama/llama3.2": "54-97% zero scores (compact prompt, no calibration anchors)",
    "groq/llama-3.1-8b-instant": "8B too weak for calibrated scoring (corr=-0.076)",
}

INFLATED_MODELS = {
    "openai/gpt-4.1-nano": "mean 0.717 -- systematic score inflation",
}


def load_test_set(game: str) -> dict:
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(path) as f:
        return json.load(f)


def save_test_set(test_set: dict, game: str) -> Path:
    path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    with open(path, "w") as f:
        json.dump(test_set, f, indent=2, ensure_ascii=False)
    return path


def audit(game: str):
    """Show annotation quality issues."""
    ts = load_test_set(game)
    queries = ts.get("queries", {})

    total = 0
    issues = Counter()
    model_zeros = Counter()
    model_counts = Counter()

    for qdata in queries.values():
        for ann in qdata.get("annotations", []):
            total += 1
            model = ann.get("llm_model", "unknown")
            model_counts[model] += 1
            sim = ann.get("similarity_score", 0)

            if sim == 0 and ann.get("functional_score", 0) == 0:
                if model in BAD_MODELS:
                    issues["zero_from_bad_model"] += 1
                    model_zeros[model] += 1
                else:
                    issues["zero_from_ok_model"] += 1

            if model in INFLATED_MODELS and sim > 0.5:
                issues["inflated"] += 1

    print(f"Annotation audit for {game}")
    print(f"{'=' * 60}")
    print(f"Total annotations: {total}")
    print()

    print("Issues found:")
    for issue, count in issues.most_common():
        print(f"  {issue}: {count}")
    print()

    print("Bad model annotations:")
    for model, reason in BAD_MODELS.items():
        count = model_counts.get(model, 0)
        zeros = model_zeros.get(model, 0)
        if count > 0:
            print(f"  {model}: {count} annotations ({zeros} all-zero)")
            print(f"    Reason: {reason}")
    print()

    print("Inflated model annotations:")
    for model, reason in INFLATED_MODELS.items():
        count = model_counts.get(model, 0)
        if count > 0:
            print(f"  {model}: {count} annotations")
            print(f"    Reason: {reason}")
    print()

    removable = sum(
        1
        for qdata in queries.values()
        for ann in qdata.get("annotations", [])
        if ann.get("llm_model", "") in BAD_MODELS
        and ann.get("similarity_score", 0) == 0
        and ann.get("functional_score", 0) == 0
    )
    print(f"Recommended removal: {removable} zero-score annotations from bad models")
    print(f"Would keep: {total - removable} annotations")


def remove_zeros(game: str, dry_run: bool = False):
    """Remove zero-score annotations from known-bad models."""
    ts = load_test_set(game)
    queries = ts.get("queries", {})
    removed = 0
    kept = 0

    for qdata in queries.values():
        original = qdata.get("annotations", [])
        filtered = []
        for ann in original:
            model = ann.get("llm_model", "")
            is_zero = (
                ann.get("similarity_score", 0) == 0
                and ann.get("functional_score", 0) == 0
                and ann.get("synergy_score", 0) == 0
                and ann.get("meta_relevance", 0) == 0
            )
            if model in BAD_MODELS and is_zero:
                removed += 1
            else:
                filtered.append(ann)
                kept += 1
        qdata["annotations"] = filtered

    print(f"Removed {removed} zero-score annotations from bad models")
    print(f"Kept {kept} annotations")

    if not dry_run and removed > 0:
        ts["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        path = save_test_set(ts, game)
        print(f"Saved to {path}")
    elif dry_run:
        print("(dry run -- no changes saved)")


def remove_model(game: str, model_name: str, dry_run: bool = False):
    """Remove all annotations from a specific model."""
    ts = load_test_set(game)
    queries = ts.get("queries", {})
    removed = 0
    kept = 0

    for qdata in queries.values():
        original = qdata.get("annotations", [])
        filtered = []
        for ann in original:
            if ann.get("llm_model", "") == model_name:
                removed += 1
            else:
                filtered.append(ann)
                kept += 1
        qdata["annotations"] = filtered

    print(f"Removed {removed} annotations from {model_name}")
    print(f"Kept {kept} annotations")

    if not dry_run and removed > 0:
        ts["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        path = save_test_set(ts, game)
        print(f"Saved to {path}")
    elif dry_run:
        print("(dry run -- no changes saved)")


def main():
    parser = argparse.ArgumentParser(description="Repair annotation quality issues")
    parser.add_argument(
        "command",
        choices=["audit", "remove-zeros", "remove-model", "reannotate"],
    )
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--model", default="", help="Model to remove (for remove-model)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--budget", type=int, default=200)
    args = parser.parse_args()

    if args.command == "audit":
        audit(args.game)
    elif args.command == "remove-zeros":
        remove_zeros(args.game, dry_run=args.dry_run)
    elif args.command == "remove-model":
        if not args.model:
            print("--model required for remove-model")
            return 1
        remove_model(args.game, args.model, dry_run=args.dry_run)
    elif args.command == "reannotate":
        print("Re-annotation via cascade not yet implemented.")
        print("Use: uv run scripts/annotation/annotation_convergence.py --model multi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
