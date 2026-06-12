#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Pre-training quality gate: catch data problems before wasting compute.

Run before any training pipeline to verify the training data meets minimum
quality thresholds. Fails loudly with actionable diagnostics.

Usage:
    uv run python scripts/training/preflight_check.py --game magic
    uv run python scripts/training/preflight_check.py  # all games
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Minimum thresholds -- fail if below these
MIN_EDGE_FRACTION = {
    # Each source type should contribute at least this fraction of total edges
    # to be worth including. Below this, weight sweeps are meaningless.
    # Exception: oracle_text works best as small, high-precision signal (0.85 cosine).
    # Lowering threshold to get more edges degrades quality (tested 0.70-0.85).
    "oracle_text": 0.001,  # 0.1% -- small but high-precision is fine
    "enriched": 0.001,  # 0.1%
    "propagated": 0.001,  # 0.1%
}

MIN_EDGES_ABSOLUTE = {
    "oracle_text": 5000,
    "enriched": 200,
    "propagated": 1000,
}

# Maximum thresholds -- warn if above (one source dominating)
MAX_EDGE_FRACTION = {
    "co_occurrence": 0.95,  # >95% means enriched signal is drowned
}


def check_game(game: str) -> list[str]:
    """Run preflight checks for one game. Returns list of issues."""
    import sqlite3

    db_path = PROJECT_ROOT / "data" / "graphs" / f"{game}_unified.db"
    if not db_path.exists():
        return [f"FAIL: No unified graph at {db_path}"]

    # Use direct SQL for speed (avoids loading full graph into memory)
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT source_type, COUNT(*) FROM edges GROUP BY source_type ORDER BY COUNT(*) DESC"
    ).fetchall()
    total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    conn.close()

    issues = []
    source_counts: Counter[str] = Counter({row[0]: row[1] for row in rows})
    total_edges = sum(source_counts.values())
    if total_edges == 0:
        return ["FAIL: Graph has 0 edges"]

    print(f"\n  Edge distribution ({total_edges:,} total):")
    for src, count in source_counts.most_common():
        frac = count / total_edges
        marker = ""

        # Check minimum fraction
        if src in MIN_EDGE_FRACTION and frac < MIN_EDGE_FRACTION[src]:
            marker = f" << BELOW {MIN_EDGE_FRACTION[src]:.1%} threshold"
            issues.append(
                f"WARN: {game} {src} edges are {frac:.2%} of total ({count:,}/{total_edges:,}). "
                f"Below {MIN_EDGE_FRACTION[src]:.1%} minimum. Weight sweeps on this source are noise. "
                f"Action: lower the similarity threshold to increase edge count."
            )

        # Check absolute minimum
        if src in MIN_EDGES_ABSOLUTE and count < MIN_EDGES_ABSOLUTE[src]:
            marker = marker or f" << BELOW {MIN_EDGES_ABSOLUTE[src]:,} minimum"
            issues.append(
                f"WARN: {game} {src} has only {count:,} edges (minimum: {MIN_EDGES_ABSOLUTE[src]:,}). "
                f"Action: check source data or lower thresholds."
            )

        # Check domination
        if src in MAX_EDGE_FRACTION and frac > MAX_EDGE_FRACTION[src]:
            marker = f" << DOMINATES ({frac:.1%})"
            issues.append(
                f"WARN: {game} {src} is {frac:.1%} of total edges. "
                f"Other sources are effectively invisible to random walks."
            )

        print(f"    {src:20s}: {count:>10,} ({frac:6.2%}){marker}")

    # Show effective weight after export multipliers
    export_weights = {"ppmi": 1.0, "enriched": 5.0, "propagated": 3.0, "oracle_text": 5.0}
    effective = {}
    for src, count in source_counts.items():
        w = export_weights.get(src, 0)
        if w > 0:
            effective[src] = count * w
    if effective:
        total_eff = sum(effective.values())
        print("\n  Effective weight after export multipliers:")
        for src, ew in sorted(effective.items(), key=lambda x: -x[1]):
            print(f"    {src:20s}: {ew:>12,.0f} ({ew / total_eff:6.2%})")

    # Check for noise cards in graph nodes (basic lands, energy)
    import sqlite3 as _sqlite3

    from ml.utils.constants import get_filter_set

    noise_cards = get_filter_set(game, level="common")
    if noise_cards:
        conn = _sqlite3.connect(str(db_path))
        placeholders = ",".join("?" for _ in noise_cards)
        cursor = conn.execute(
            f"SELECT name FROM nodes WHERE name IN ({placeholders})", list(noise_cards)
        )
        noise_nodes = [row[0] for row in cursor]
        conn.close()

        if noise_nodes:
            print(f"\n  Noise cards in graph: {len(noise_nodes)}")
            issues.append(f"INFO: {game} has {len(noise_nodes)} noise card nodes (lands/energy).")

    # Check deck JSONL availability
    deck_dir = PROJECT_ROOT / "data" / "decks"
    deck_files = list(deck_dir.glob(f"decks_{game}_*.jsonl"))
    total_decks = 0
    for df in deck_files:
        with open(df) as fh:
            total_decks += sum(1 for _ in fh)
    print(f"\n  Deck sources: {len(deck_files)} files, {total_decks:,} decks")

    # Check test set exists and has queries
    test_set = PROJECT_ROOT / "data" / "test_sets" / f"annotated_{game}_v2.json"
    if test_set.exists():
        import json

        with open(test_set) as fh:
            data = json.load(fh)
        n_queries = len(data.get("queries", {}))
        print(f"  Test set: {n_queries:,} queries")
    else:
        issues.append(f"WARN: No test set at {test_set}")

    # Check embedding vocab coverage
    emb_dir = PROJECT_ROOT / "data" / "embeddings"
    latest_emb = sorted(emb_dir.glob(f"{game}_*_fused.wv")) + sorted(
        emb_dir.glob(f"{game}_*spectral*.wv")
    )
    if latest_emb:
        from gensim.models import KeyedVectors

        kv = KeyedVectors.load(str(latest_emb[-1]))
        vocab_size = len(kv)
        coverage = vocab_size / total_nodes if total_nodes else 0
        print(f"  Embedding coverage: {coverage:.1%} ({vocab_size:,}/{total_nodes:,} graph nodes)")
        if coverage < 0.5:
            issues.append(
                f"WARN: {game} embedding covers only {coverage:.1%} of graph nodes. "
                f"Many cards have no embedding."
            )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-training quality gate")
    parser.add_argument("--game", choices=["magic", "pokemon", "yugioh", "all"], default="all")
    args = parser.parse_args()

    games = ["magic", "pokemon", "yugioh"] if args.game == "all" else [args.game]
    all_issues: list[str] = []

    for game in games:
        print(f"\n{'=' * 60}")
        print(f"  PREFLIGHT: {game.upper()}")
        print(f"{'=' * 60}")
        issues = check_game(game)
        all_issues.extend(issues)

    # Summary
    print(f"\n{'=' * 60}")
    warns = [i for i in all_issues if i.startswith("WARN")]
    fails = [i for i in all_issues if i.startswith("FAIL")]
    infos = [i for i in all_issues if i.startswith("INFO")]

    if fails:
        print(f"  PREFLIGHT FAILED: {len(fails)} blocking issue(s)")
        for f in fails:
            print(f"    {f}")
        return 1

    if warns:
        print(f"  PREFLIGHT WARNINGS: {len(warns)} issue(s)")
        for w in warns:
            print(f"    {w}")
    else:
        print("  PREFLIGHT PASSED: no issues")

    if infos:
        for i in infos:
            print(f"    {i}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
