#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "numpy>=1.24.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Log an experiment result to the experiment ledger.

Runs eval_per_mode.py metrics and appends a row to the TSV ledger.

Usage:
    uv run scripts/evaluation/log_experiment.py --game magic --embedding magic_v5_fused --notes "v5 fused alpha=0.7"
    uv run scripts/evaluation/log_experiment.py --all-games --notes "baseline after retrain"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DATA_DIR = PROJECT_ROOT / "data"
LEDGER_PATH = DATA_DIR / "experiments" / "experiment_log.tsv"

# Import eval functions
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "evaluation"))
from eval_per_mode import eval_game, load_test_set


def count_pairs(game: str) -> int:
    """Count pairs in the active pairs file."""
    env_key = f"PAIRS_PATH_{game.upper()}"
    pairs_path = os.getenv(env_key, "")
    if pairs_path:
        p = Path(pairs_path.lstrip("./"))
        if p.exists():
            return sum(1 for _ in open(p)) - 1  # subtract header
    return 0


def log_experiment(
    game: str,
    embedding_name: str | None,
    notes: str = "",
    alpha: str = "n/a",
) -> dict:
    """Run eval and log results."""
    result = eval_game(game, embedding_name)
    if "error" in result:
        print(f"{game}: {result['error']}")
        return result

    # Extract metrics
    overall = result.get("overall_ndcg", {}).get("ndcg_at_k", 0)
    sub = result.get("mode_substitute", {}).get("ndcg_at_k", 0)
    syn = result.get("mode_synergy", {}).get("ndcg_at_k", 0)
    meta = result.get("mode_meta", {}).get("ndcg_at_k", 0)
    sub_score = result.get("substitutability_ndcg", {}).get("ndcg_at_k", 0)

    pairs = count_pairs(game)
    emb_name = embedding_name or result.get("embedding", "?")

    row = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "game": game,
        "experiment": emb_name,
        "embedding": emb_name,
        "alpha": alpha,
        "pairs_count": pairs,
        "vocab": result.get("vocab_size", 0),
        "overall_ndcg": f"{overall:.4f}",
        "sub_ndcg": f"{sub:.4f}",
        "syn_ndcg": f"{syn:.4f}",
        "meta_ndcg": f"{meta:.4f}",
        "sub_score_ndcg": f"{sub_score:.4f}" if sub_score > 0 else "n/a",
        "deck_quality": "pending",
        "contextual_alt_recall": "pending",
        "notes": notes,
    }

    # Append to ledger
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not LEDGER_PATH.exists()
    with open(LEDGER_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys(), delimiter="\t")
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    print(f"Logged: {game}/{emb_name} overall={overall:.4f} sub={sub:.4f} syn={syn:.4f}")
    return row


def main():
    parser = argparse.ArgumentParser(description="Log experiment to ledger")
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--all-games", action="store_true")
    parser.add_argument("--embedding", default=None)
    parser.add_argument("--alpha", default="n/a")
    parser.add_argument("--notes", default="", required=True)
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.all_games else [args.game]
    for game in games:
        log_experiment(game, args.embedding, args.notes, args.alpha)

    print(f"\nLedger: {LEDGER_PATH}")


if __name__ == "__main__":
    main()
