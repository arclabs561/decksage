#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Pipeline orchestrator for DeckSage data -> graph -> embeddings.

Runs the full pipeline (or a subset) for one or more games:
  1. Scrape card data (attributes, images, sets)
  2. Scrape/download decklists
  3. Build unified graph (co-occurrence + PPMI + oracle text + annotations)
  4. Train ProNE embeddings
  5. Evaluate embeddings (if eval script exists)

Usage:
    uv run scripts/run_pipeline.py --game pokemon
    uv run scripts/run_pipeline.py --game magic --steps scrape-decks build-graph train
    uv run scripts/run_pipeline.py --game all --dry-run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

ALL_GAMES = ["magic", "pokemon", "yugioh"]

ALL_STEPS = [
    "scrape-cards",
    "scrape-decks",
    "build-graph",
    "train",
    "evaluate",
]

# Per-game deck scraping commands
DECK_SCRAPE_COMMANDS: dict[str, list[list[str]]] = {
    "magic": [
        [
            sys.executable, str(PROJECT_ROOT / "scripts/data/download_magic_decks.py"),
            "--source", "goldfish",
            "--output", str(PROJECT_ROOT / "data/decks/decks_magic_goldfish.jsonl"),
        ],
    ],
    "pokemon": [
        [
            sys.executable, str(PROJECT_ROOT / "scripts/data/scrape_limitless_decks.py"),
            "--output", str(PROJECT_ROOT / "data/decks/decks_pokemon_limitless.jsonl"),
        ],
    ],
    "yugioh": [
        [
            sys.executable, str(PROJECT_ROOT / "scripts/data/scrape_ygoprodeck_decks.py"),
            "--output", str(PROJECT_ROOT / "data/decks/decks_yugioh_ygoprodeck_recent.jsonl"),
            "--archetypes-only", "--community-decks",
        ],
    ],
}

# Per-game edgelist paths for training
EDGELISTS: dict[str, str] = {
    "magic": "data/graphs/pairs_large.edg",
    "pokemon": "data/graphs/pokemon_blended.edg",
    "yugioh": "data/graphs/yugioh_blended.edg",
}

CARD_ATTRIBUTES: dict[str, str] = {
    "magic": "data/processed/card_attributes_enriched.csv",
    "pokemon": "data/processed/card_attributes_pokemon.csv",
    "yugioh": "data/processed/card_attributes_yugioh.csv",
}


def run_step(label: str, cmd: list[str], dry_run: bool = False) -> bool:
    """Run a subprocess step, returning True on success."""
    print(f"\n{'─'*60}")
    print(f"  [{label}]")
    print(f"  cmd: {' '.join(cmd)}")
    print(f"{'─'*60}")

    if dry_run:
        print("  [dry-run] skipped")
        return True

    t0 = time.monotonic()
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    elapsed = time.monotonic() - t0

    if result.returncode != 0:
        print(f"  FAILED (exit {result.returncode}) after {elapsed:.1f}s")
        return False

    print(f"  OK ({elapsed:.1f}s)")
    return True


def run_pipeline(game: str, steps: list[str], dry_run: bool = False) -> bool:
    """Run the pipeline for a single game. Returns True if all steps succeed."""
    print(f"\n{'='*60}")
    print(f"  Pipeline: {game.upper()}")
    print(f"  Steps: {', '.join(steps)}")
    print(f"{'='*60}")

    ok = True

    # 1. Scrape card data
    if "scrape-cards" in steps:
        ok = run_step(
            f"{game}/scrape-cards",
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts/data/scrape_card_data.py"),
                "--game", game,
                "--data-type", "sets",
            ],
            dry_run,
        )
        if not ok:
            return False

    # 2. Scrape decklists
    if "scrape-decks" in steps:
        for cmd in DECK_SCRAPE_COMMANDS.get(game, []):
            ok = run_step(f"{game}/scrape-decks", cmd, dry_run)
            if not ok:
                return False

    # 3. Build unified graph
    if "build-graph" in steps:
        ok = run_step(
            f"{game}/build-graph",
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts/training/build_unified_graph.py"),
                "--game", game,
            ],
            dry_run,
        )
        if not ok:
            return False

    # 4. Train ProNE embeddings
    if "train" in steps:
        edgelist = PROJECT_ROOT / EDGELISTS.get(game, "")
        output = PROJECT_ROOT / "data" / "embeddings" / f"{game}_prone.wv"
        card_attrs = PROJECT_ROOT / CARD_ATTRIBUTES.get(game, "")

        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts/training/train_prone.py"),
            "--edgelist", str(edgelist),
            "--output", str(output),
            "--dim", "128",
        ]
        if card_attrs.exists():
            cmd.extend(["--card-attributes", str(card_attrs)])

        ok = run_step(f"{game}/train", cmd, dry_run)
        if not ok:
            return False

    # 5. Evaluate
    if "evaluate" in steps:
        eval_script = PROJECT_ROOT / "scripts" / "training" / "evaluate_embeddings.py"
        if eval_script.exists():
            ok = run_step(
                f"{game}/evaluate",
                [sys.executable, str(eval_script), "--game", game],
                dry_run,
            )
        else:
            print(f"  [{game}/evaluate] SKIPPED (no evaluate_embeddings.py)")

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DeckSage pipeline orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--game",
        choices=[*ALL_GAMES, "all"],
        default="all",
        help="Which game(s) to run (default: all)",
    )
    parser.add_argument(
        "--steps",
        nargs="+",
        choices=ALL_STEPS,
        default=ALL_STEPS,
        help=f"Pipeline steps to run (default: all). Choices: {', '.join(ALL_STEPS)}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing",
    )
    args = parser.parse_args()

    games = ALL_GAMES if args.game == "all" else [args.game]

    print("DeckSage Pipeline")
    print(f"  Games: {', '.join(games)}")
    print(f"  Steps: {', '.join(args.steps)}")
    print(f"  Dry run: {args.dry_run}")

    results: dict[str, bool] = {}
    for game in games:
        results[game] = run_pipeline(game, args.steps, args.dry_run)

    # Summary
    print(f"\n{'='*60}")
    print("  Pipeline Summary")
    print(f"{'='*60}")
    for game, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {game}: {status}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
