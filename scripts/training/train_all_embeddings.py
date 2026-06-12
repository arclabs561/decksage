#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy<2.0.0", "nodevectors>=0.2.0", "networkx>=3.0"]
# ///
"""
Reproducible embedding training pipeline for all games.

Orchestrates the full pipeline from unified SQLite graph to trained embeddings:

0. Build unified graph (all edge sources -> SQLite with source_type tags)
1. Export filtered edgelist (SQL query with per-source weight multipliers)
2. Training: ProNE (fast SVD) and PecanPy (node2vec)
3. Fusion with card attributes (weighted concat + PCA)
4. Evaluation on annotated test sets
5. Visual review HTML

The build step replaces the old 8-step workflow (PPMI, oracle text, annotations,
propagation, merge) with a single script that writes everything to SQLite.

Usage:
    # Train everything for all games
    python scripts/training/train_all_embeddings.py

    # Train specific game
    python scripts/training/train_all_embeddings.py --game pokemon

    # Skip slow PecanPy training (ProNE only)
    python scripts/training/train_all_embeddings.py --skip-pecanpy

    # Dry run (show what would be done)
    python scripts/training/train_all_embeddings.py --dry-run

    # Skip rebuild (use existing .db)
    python scripts/training/train_all_embeddings.py --skip-build
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


VENV_PYTHON = ".venv/bin/python"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Game configurations ──

GAME_CONFIGS = {
    "pokemon": {
        "card_attributes": "data/processed/card_attributes_pokemon.csv",
        "test_set": "data/test_set_annotated_pokemon.json",
        "image_urls": "data/processed/pokemon_image_urls.json",
        # Export weights: per-source-type multipliers for the merged edgelist
        # Matches old pipeline: ppmi x1.0, enriched x5.0, propagated x3.0, oracle x5.0
        "export_weights": {
            "ppmi": 1.0,
            "enriched": 5.0,
            "propagated": 3.0,
            "oracle_text": 5.0,
        },
    },
    "yugioh": {
        "card_attributes": "data/processed/card_attributes_yugioh.csv",
        "test_set": "data/test_set_annotated_yugioh.json",
        "image_urls": "data/processed/yugioh_image_urls.json",
        "export_weights": {
            "ppmi": 1.0,
            "enriched": 5.0,
            "propagated": 3.0,
            "oracle_text": 5.0,
        },
    },
    "magic": {
        "card_attributes": "data/processed/card_attributes_enriched.csv",
        "test_set": "data/test_set_annotated_magic.json",
        "image_urls": "data/processed/card_attributes_enriched_image_urls.json",
        "export_weights": {
            "ppmi": 1.0,
            "enriched": 5.0,
            "propagated": 3.0,
            "oracle_text": 5.0,
        },
    },
}


def run(cmd: list[str], dry_run: bool = False) -> int:
    """Run a command, printing it first."""
    cmd_str = " ".join(str(c) for c in cmd)
    if dry_run:
        print(f"  [DRY RUN] {cmd_str}")
        return 0
    print(f"  $ {cmd_str}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"  ERROR: exit code {result.returncode}")
    return result.returncode


def step_build_unified_graph(game: str, dry_run: bool) -> Path:
    """Step 0: Build the unified SQLite graph from all edge sources."""
    db_path = PROJECT_ROOT / "data" / "graphs" / f"{game}_unified.db"
    print(f"\n[0] Build unified graph -> {db_path.name}")
    run(
        [
            VENV_PYTHON,
            "scripts/training/build_unified_graph.py",
            "--game",
            game,
        ],
        dry_run,
    )
    return db_path


def step_export_edgelist(game: str, config: dict, db_path: Path, dry_run: bool) -> str:
    """Step 1: Export filtered edgelist from unified graph."""
    output = f"data/graphs/{game}_merged_all.edg"
    source_types = list(config["export_weights"].keys())
    weights = config["export_weights"]

    print(f"\n[1] Export filtered edgelist -> {output}")

    if dry_run:
        print(f"  [DRY RUN] export from {db_path.name}")
        print(f"  source_types={source_types}")
        print(f"  weights={weights}")
        return output

    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from ml.data.incremental_graph import IncrementalCardGraph

    graph = IncrementalCardGraph(graph_path=db_path, use_sqlite=True)
    game_code = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}[game]
    graph.export_edgelist_filtered(
        output_path=PROJECT_ROOT / output,
        game=game_code,
        source_types=source_types,
        weights=weights,
        min_weight=0.0,
    )
    return output


def step_train_prone(game: str, merged_edgelist: str, dry_run: bool) -> str:
    """Step 2a: Train ProNE embeddings."""
    output = f"data/embeddings/{game}_prone_propagated.wv"
    print(f"\n[2a] ProNE training: {merged_edgelist} -> {output}")
    run(
        [
            VENV_PYTHON,
            "scripts/training/train_prone.py",
            "--edgelist",
            merged_edgelist,
            "--output",
            output,
            "--dim",
            "128",
        ],
        dry_run,
    )
    return output


def step_train_pecanpy(game: str, merged_edgelist: str, dry_run: bool) -> str:
    """Step 2b: Train PecanPy embeddings."""
    output = f"data/embeddings/{game}_pecanpy_propagated.wv"
    print(f"\n[2b] PecanPy training: {merged_edgelist} -> {output}")
    run(
        [
            VENV_PYTHON,
            "scripts/training/train_blended_embeddings.py",
            "--edgelist",
            merged_edgelist,
            "--weight",
            "1.0",
            "--output",
            output,
            "--dim",
            "128",
            "--walks",
            "10",
            "--walk-length",
            "80",
        ],
        dry_run,
    )
    return output


def step_fuse_attributes(
    game: str, config: dict, embedding_path: str, suffix: str, dry_run: bool
) -> str:
    """Step 3: Fuse structural embeddings with card attributes."""
    if not config["card_attributes"]:
        return ""
    output = f"data/embeddings/{game}_{suffix}_fused.wv"
    print(f"\n[3] Fusion: {embedding_path} + {config['card_attributes']} -> {output}")
    run(
        [
            VENV_PYTHON,
            "scripts/training/fuse_embeddings.py",
            "--embeddings",
            embedding_path,
            "--card-attrs",
            config["card_attributes"],
            "--output",
            output,
            "--alpha",
            "0.7",
            "--dim",
            "128",
        ],
        dry_run,
    )
    return output


def step_evaluate(game: str, config: dict, embedding_paths: list[str], dry_run: bool) -> None:
    """Step 4: Evaluate all embeddings on annotated test set."""
    test_set = config["test_set"]
    if not Path(test_set).exists() and not dry_run:
        print(f"\n[4] Evaluation: SKIPPED (no test set at {test_set})")
        return

    print(f"\n[4] Evaluation on {test_set}")
    existing = [p for p in embedding_paths if p and (Path(p).exists() or dry_run)]
    if not existing:
        print("  No embeddings to evaluate")
        return

    if dry_run:
        for p in existing:
            print(f"  [DRY RUN] evaluate {p}")
        return

    # Inline evaluation (same as batch_eval_ndcg.py)
    import json
    import math

    from gensim.models import KeyedVectors

    GRADES = {
        "highly_relevant": 3,
        "relevant": 2,
        "somewhat_relevant": 1,
        "marginally_relevant": 0.5,
        "irrelevant": 0,
    }

    def dcg(scores, k):
        return sum(s / math.log2(i + 2) for i, s in enumerate(scores[:k]))

    def ndcg(rels, k):
        d = dcg(rels, k)
        ideal = dcg(sorted(rels, reverse=True), k)
        return d / ideal if ideal > 0 else 0.0

    data = json.load(open(test_set))
    queries = data.get("queries", data)

    for emb_path in existing:
        try:
            kv = KeyedVectors.load(str(emb_path))
        except Exception as e:
            print(f"  {Path(emb_path).stem}: FAILED to load - {e}")
            continue
        scores, n_miss = [], 0
        for q, labels in queries.items():
            if q not in kv:
                n_miss += 1
                continue
            try:
                neighbors = kv.most_similar(q, topn=10)
            except Exception:
                n_miss += 1
                continue
            rels = []
            for card, _ in neighbors:
                grade = 0.0
                for level, w in GRADES.items():
                    if card in labels.get(level, []):
                        grade = w
                        break
                rels.append(grade)
            scores.append(ndcg(rels, 10))
        n = len(scores)
        mean_ndcg = sum(scores) / n if n else 0.0
        name = Path(emb_path).stem
        print(f"  {name}: nDCG@10={mean_ndcg:.3f}  ({n}/{n + n_miss} queries)")


def step_validate_vocab_coverage(
    game: str,
    db_path: Path,
    embedding_paths: list[str],
    min_decks: int = 10,
    dry_run: bool = False,
) -> bool:
    """Step 4b: Verify every card appearing in >= min_decks decks is in the embedding vocab.

    Catches issues like Card_XXXX numeric IDs leaking into embeddings or
    legitimate cards being dropped during training.

    Returns True if all checks pass, False if any embedding is missing cards.
    """
    import re
    import sqlite3

    print(f"\n[4b] Vocab coverage check (min_decks={min_decks})")
    if dry_run:
        print("  [DRY RUN] would check vocab coverage")
        return True

    if not db_path.exists():
        print(f"  SKIPPED: no graph DB at {db_path}")
        return True

    # Query cards with >= min_decks from the unified graph
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT name, total_decks FROM nodes WHERE total_decks >= ?",
        (min_decks,),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"  WARNING: no cards with >= {min_decks} decks in {db_path.name}")
        return True

    # Filter out Card_XXXX numeric IDs (known noise from YGOProDeck)
    numeric_id_re = re.compile(r"^Card_\d+$")
    expected_cards = {name for name, _ in rows if not numeric_id_re.match(name)}
    print(f"  {len(expected_cards)} cards with >= {min_decks} decks (excluding Card_XXXX IDs)")

    all_passed = True
    for emb_path in embedding_paths:
        if not emb_path or not Path(emb_path).exists():
            continue
        try:
            from gensim.models import KeyedVectors

            kv = KeyedVectors.load(str(emb_path))
        except Exception as e:
            print(f"  {Path(emb_path).stem}: FAILED to load - {e}")
            all_passed = False
            continue

        vocab = set(kv.key_to_index.keys())
        missing = expected_cards - vocab
        noise = {k for k in vocab if numeric_id_re.match(k)}
        coverage = len(expected_cards & vocab) / len(expected_cards) * 100

        name = Path(emb_path).stem
        if missing:
            print(
                f"  {name}: MISSING {len(missing)}/{len(expected_cards)} "
                f"cards ({coverage:.1f}% coverage)"
            )
            # Show up to 10 missing cards sorted by deck count
            missing_with_count = sorted(
                [(n, d) for n, d in rows if n in missing],
                key=lambda x: -x[1],
            )[:10]
            for card_name, deck_count in missing_with_count:
                print(f"    - {card_name} ({deck_count} decks)")
            all_passed = False
        else:
            print(f"  {name}: OK ({coverage:.1f}% coverage)")

        if noise:
            print(f"  {name}: WARNING: {len(noise)} Card_XXXX numeric IDs in vocab")
            all_passed = False

    return all_passed


def step_generate_review(
    game: str, config: dict, embedding_paths: list[str], dry_run: bool
) -> None:
    """Step 5: Generate visual review HTML with card images."""
    test_set = config["test_set"]
    image_urls = config.get("image_urls", "")
    output = f"experiments/review_{game}.html"

    existing = [p for p in embedding_paths if p and (Path(p).exists() or dry_run)]
    if not existing:
        print("\n[5] Review HTML: SKIPPED (no embeddings)")
        return

    if not Path(test_set).exists() and not dry_run:
        print(f"\n[5] Review HTML: SKIPPED (no test set at {test_set})")
        return

    # Try graph DB first for image URLs, fall back to JSON file
    db_path = PROJECT_ROOT / "data" / "graphs" / f"{game}_unified.db"
    print(f"\n[5] Review HTML: {len(existing)} models -> {output}")
    cmd = [
        VENV_PYTHON,
        "scripts/evaluation/generate_review_html.py",
        "--test-set",
        test_set,
        "--embeddings",
        *existing,
        "--game",
        game,
        "--output",
        output,
        "--top-k",
        "10",
        "--max-queries",
        "40",
    ]
    if db_path.exists() and not dry_run:
        cmd.extend(["--graph-db", str(db_path)])
    elif image_urls and (Path(image_urls).exists() or dry_run):
        cmd.extend(["--image-urls", image_urls])
    run(cmd, dry_run)


def train_game(game: str, config: dict, args: argparse.Namespace) -> None:
    """Run full training pipeline for one game."""
    print(f"\n{'=' * 60}")
    print(f"  Training pipeline: {game.upper()}")
    print(f"{'=' * 60}")

    # Step 0: Build unified graph
    if not args.skip_build:
        db_path = step_build_unified_graph(game, args.dry_run)
    else:
        db_path = PROJECT_ROOT / "data" / "graphs" / f"{game}_unified.db"
        print(f"\n[0] Build: SKIPPED (--skip-build, using {db_path.name})")

    # Step 1: Export filtered edgelist
    merged = step_export_edgelist(game, config, db_path, args.dry_run)

    # Step 2: Training
    prone_path = step_train_prone(game, merged, args.dry_run)

    pecanpy_path = ""
    if not args.skip_pecanpy:
        pecanpy_path = step_train_pecanpy(game, merged, args.dry_run)

    # Step 3: Fusion
    prone_fused = step_fuse_attributes(game, config, prone_path, "prone_merged", args.dry_run)

    pecanpy_fused = ""
    if pecanpy_path:
        pecanpy_fused = step_fuse_attributes(
            game, config, pecanpy_path, "pecanpy_merged", args.dry_run
        )

    # Step 4: Evaluate
    all_embeddings = [prone_path, pecanpy_path, prone_fused, pecanpy_fused]
    step_evaluate(game, config, all_embeddings, args.dry_run)

    # Step 4b: Vocab coverage validation
    step_validate_vocab_coverage(game, db_path, all_embeddings, min_decks=10, dry_run=args.dry_run)

    # Step 5: Visual review HTML
    step_generate_review(game, config, all_embeddings, args.dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reproducible embedding training pipeline for all games.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--game", choices=list(GAME_CONFIGS.keys()), help="Train specific game only (default: all)"
    )
    parser.add_argument(
        "--skip-pecanpy",
        action="store_true",
        help="Skip PecanPy training (ProNE only, much faster)",
    )
    parser.add_argument(
        "--skip-build", action="store_true", help="Skip unified graph build (use existing .db)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without executing"
    )
    args = parser.parse_args()

    games = [args.game] if args.game else list(GAME_CONFIGS.keys())

    for game in games:
        config = GAME_CONFIGS[game]
        train_game(game, config, args)

    print(f"\n{'=' * 60}")
    print("  Pipeline complete.")
    print(f"{'=' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
