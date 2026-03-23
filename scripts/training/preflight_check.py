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

GAME_CODE = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}

# Minimum thresholds -- fail if below these
MIN_EDGE_FRACTION = {
    # Each source type should contribute at least this fraction of total edges
    # to be worth including. Below this, it's noise.
    "oracle_text": 0.01,   # 1% -- below this, weight sweeps are meaningless
    "enriched": 0.001,     # 0.1%
    "propagated": 0.001,   # 0.1%
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
    from ml.data.incremental_graph import IncrementalCardGraph

    db_path = PROJECT_ROOT / "data" / "graphs" / f"{game}_unified.db"
    if not db_path.exists():
        return [f"FAIL: No unified graph at {db_path}"]

    graph = IncrementalCardGraph(graph_path=db_path, use_sqlite=True)

    issues = []
    total_edges = len(graph.edges)
    if total_edges == 0:
        return [f"FAIL: Graph has 0 edges"]

    # Count edges by source type
    source_counts: Counter[str] = Counter()
    for edge in graph.edges.values():
        source_counts[edge.source_type] += 1

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

    # Check for noise cards in edges (basic lands, energy)
    from ml.utils.constants import get_filter_set

    noise_cards = get_filter_set(game, level="common")
    if noise_cards:
        noise_edge_count = 0
        for edge in graph.edges.values():
            if edge.source_type == "co_occurrence":
                # Edge key is (card1, card2)
                key = list(graph.edges.keys())[0]  # check format
                break

        # Check a sample of node names
        noise_nodes = set()
        for name in graph.nodes:
            if name in noise_cards:
                noise_nodes.add(name)

        if noise_nodes:
            print(f"\n  Noise cards still in graph nodes: {len(noise_nodes)}")
            print(f"    {sorted(noise_nodes)[:5]}...")
            issues.append(
                f"INFO: {game} has {len(noise_nodes)} noise card nodes "
                f"(lands/energy). These should be filtered from co-occurrence edges."
            )

    # Check deck JSONL availability
    deck_dir = PROJECT_ROOT / "data" / "decks"
    deck_files = list(deck_dir.glob(f"decks_{game}_*.jsonl"))
    total_decks = 0
    for f in deck_files:
        total_decks += sum(1 for _ in open(f))
    print(f"\n  Deck sources: {len(deck_files)} files, {total_decks:,} decks")

    # Check test set exists and has queries
    test_set = PROJECT_ROOT / "data" / "test_sets" / f"annotated_{game}_v2.json"
    if test_set.exists():
        import json
        data = json.load(open(test_set))
        n_queries = len(data.get("queries", {}))
        print(f"  Test set: {n_queries:,} queries")
    else:
        issues.append(f"WARN: No test set at {test_set}")

    # Check embedding vocab coverage
    emb_dir = PROJECT_ROOT / "data" / "embeddings"
    latest_emb = sorted(emb_dir.glob(f"{game}_*_fused.wv"))
    if latest_emb:
        from gensim.models import KeyedVectors
        kv = KeyedVectors.load(str(latest_emb[-1]))
        vocab = set(kv.key_to_index.keys())
        graph_nodes = set(graph.nodes.keys())
        coverage = len(vocab & graph_nodes) / len(graph_nodes) if graph_nodes else 0
        print(f"  Embedding coverage: {coverage:.1%} ({len(vocab & graph_nodes):,}/{len(graph_nodes):,})")
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
