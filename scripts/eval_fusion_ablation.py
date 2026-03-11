#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy>=1.26.0", "pandas>=2.0.0"]
# ///
"""
Fusion signal ablation evaluation.

Every component earns its place through measured contribution (Sutton lens).
This script isolates each similarity signal and measures its standalone and
combined performance against fixed benchmark queries, offline (no server needed).

Usage:
    uv run scripts/eval_fusion_ablation.py
    uv run scripts/eval_fusion_ablation.py --game yugioh --k 20
    uv run scripts/eval_fusion_ablation.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# sys.path setup -- same pattern as eval_completion_methods.py
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from gensim.models import KeyedVectors

from ml.similarity.fusion import FusionWeights, WeightedLateFusion
from ml.similarity.similarity_methods import (
    jaccard_similarity,
    load_graph,
)


# ---------------------------------------------------------------------------
# Benchmark queries per game
# ---------------------------------------------------------------------------
QUERIES: dict[str, list[str]] = {
    "magic": [
        "Lightning Bolt",
        "Counterspell",
        "Dark Ritual",
        "Birds of Paradise",
        "Swords to Plowshares",
    ],
    "pokemon": [
        "Arcanine ex",
        "Charizard ex",
        "Pikachu VMAX",
    ],
    "yugioh": [
        "Ash Blossom & Joyful Spring",
        "Blue-Eyes White Dragon",
        "Dark Magician",
    ],
}

# ---------------------------------------------------------------------------
# Default embedding/pairs paths per game
# ---------------------------------------------------------------------------
DEFAULT_EMBEDDINGS: dict[str, str] = {
    "magic": "data/embeddings/magic_cleaned_v4.wv",
    "pokemon": "data/embeddings/pokemon_cleaned_v4.wv",
    "yugioh": "data/embeddings/yugioh_cleaned_v4.wv",
}

DEFAULT_PAIRS: dict[str, str] = {
    "magic": "data/processed/pairs_large.csv",
    "pokemon": "data/processed/pairs_pokemon_limitless-web.csv",
    "yugioh": "data/processed/pairs_yugioh_ygoprodeck-tournament.csv",
}


# ---------------------------------------------------------------------------
# Ablation configurations
# ---------------------------------------------------------------------------
@dataclass
class AblationConfig:
    name: str
    weights: FusionWeights | None  # None = use jaccard_similarity directly
    aggregator: str
    jaccard_only: bool = False


def build_configs() -> list[AblationConfig]:
    zero = FusionWeights(
        embed=0.0,
        jaccard=0.0,
        functional=0.0,
        text_embed=0.0,
        visual_embed=0.0,
        sideboard=0.0,
        temporal=0.0,
        gnn=0.0,
        pack_embed=0.0,
        archetype=0.0,
        format=0.0,
    )
    return [
        AblationConfig(
            name="embed_only",
            weights=FusionWeights(**{**asdict(zero), "embed": 1.0}),
            aggregator="weighted",
        ),
        AblationConfig(
            name="jaccard_only",
            weights=None,
            aggregator="n/a",
            jaccard_only=True,
        ),
        AblationConfig(
            name="text_only",
            weights=FusionWeights(**{**asdict(zero), "text_embed": 1.0}),
            aggregator="weighted",
        ),
        AblationConfig(
            name="embed+jaccard",
            weights=FusionWeights(**{**asdict(zero), "embed": 0.6, "jaccard": 0.4}),
            aggregator="weighted",
        ),
        AblationConfig(
            name="embed+text",
            weights=FusionWeights(**{**asdict(zero), "embed": 0.5, "text_embed": 0.5}),
            aggregator="weighted",
        ),
        AblationConfig(
            name="embed+jaccard+text_rrf",
            weights=FusionWeights(
                **{**asdict(zero), "embed": 0.33, "jaccard": 0.33, "text_embed": 0.34}
            ),
            aggregator="rrf",
        ),
        AblationConfig(
            name="embed+jaccard+text_weighted",
            weights=FusionWeights(
                **{**asdict(zero), "embed": 0.33, "jaccard": 0.33, "text_embed": 0.34}
            ),
            aggregator="weighted",
        ),
    ]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_data(
    game: str,
    embeddings_path: str | None = None,
    pairs_path: str | None = None,
) -> tuple[KeyedVectors | None, dict | None]:
    """Load embeddings and graph data for a game. Returns (embeddings, adj)."""
    emb = None
    adj = None

    # Resolve paths relative to project root
    emb_file = embeddings_path or DEFAULT_EMBEDDINGS.get(game)
    pairs_file = pairs_path or DEFAULT_PAIRS.get(game)

    if emb_file:
        p = _PROJECT_ROOT / emb_file if not Path(emb_file).is_absolute() else Path(emb_file)
        if p.exists():
            print(f"Loading embeddings: {p}", file=sys.stderr)
            emb = KeyedVectors.load(str(p))
            print(f"  {len(emb):,} cards, {emb.vector_size}D", file=sys.stderr)
        else:
            print(f"WARNING: embeddings not found: {p}", file=sys.stderr)

    if pairs_file:
        p = _PROJECT_ROOT / pairs_file if not Path(pairs_file).is_absolute() else Path(pairs_file)
        if p.exists():
            print(f"Loading graph: {p}", file=sys.stderr)
            filter_lands = game == "magic"
            adj_data, _weights = load_graph(csv_path=str(p), filter_lands=filter_lands)
            adj = dict(adj_data)
            print(f"  {len(adj):,} cards in graph", file=sys.stderr)
        else:
            print(f"WARNING: pairs CSV not found: {p}", file=sys.stderr)

    return emb, adj


# ---------------------------------------------------------------------------
# Run single query against a config
# ---------------------------------------------------------------------------
def run_query(
    config: AblationConfig,
    query: str,
    k: int,
    embeddings: KeyedVectors | None,
    adj: dict | None,
) -> dict:
    """Run a single ablation query. Returns result dict."""
    t0 = time.monotonic()

    if config.jaccard_only:
        if adj is None or query not in adj:
            results = []
        else:
            results = jaccard_similarity(query, adj, top_k=k, filter_lands=False)
    else:
        if config.weights is None:
            results = []
        else:
            fusion = WeightedLateFusion(
                embeddings=embeddings,
                adj=adj,
                weights=config.weights,
                aggregator=config.aggregator,
                candidate_topn=200,
            )
            results = fusion.similar(query, k=k)

    elapsed_ms = (time.monotonic() - t0) * 1000.0

    return {
        "config": config.name,
        "query": query,
        "results": [{"card": name, "score": round(score, 4)} for name, score in results],
        "top3": [name for name, _ in results[:3]],
        "count": len(results),
        "time_ms": round(elapsed_ms, 1),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fusion signal ablation -- measure each component's contribution"
    )
    parser.add_argument("--game", default="magic", choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--k", type=int, default=10, help="Top-k results per query")
    parser.add_argument("--json", action="store_true", help="Full JSON output to stdout")
    parser.add_argument("--embeddings", default=None, help="Override embeddings path")
    parser.add_argument("--pairs", default=None, help="Override pairs CSV path")
    args = parser.parse_args()

    game: str = args.game
    k: int = args.k
    queries = QUERIES.get(game, [])
    if not queries:
        print(f"No benchmark queries defined for game: {game}", file=sys.stderr)
        sys.exit(1)

    embeddings, adj = load_data(game, args.embeddings, args.pairs)
    if embeddings is None and adj is None:
        print("ERROR: no embeddings or graph data loaded", file=sys.stderr)
        sys.exit(1)

    configs = build_configs()
    all_results: list[dict] = []
    skipped_queries: list[str] = []

    print(
        f"\nRunning ablation: game={game}, k={k}, "
        f"{len(configs)} configs x {len(queries)} queries\n",
        file=sys.stderr,
    )

    # TSV header (human output)
    if not args.json:
        print(f"{'config':<32s}\t{'query':<35s}\t{'top3_cards':<80s}\t{'time_ms':>8s}")
        print("-" * 165)

    for query in queries:
        # Check if query exists in any data source
        in_emb = embeddings is not None and query in embeddings
        in_graph = adj is not None and query in adj
        if not in_emb and not in_graph:
            skipped_queries.append(query)
            if not args.json:
                print(f"{'--':<32s}\t{query:<35s}\t{'SKIPPED (not in vocab)':<80s}\t{'--':>8s}")
            continue

        for config in configs:
            # Skip text_only if no text embedder (we have no text embedder in offline mode)
            if config.name == "text_only":
                result = {
                    "config": config.name,
                    "query": query,
                    "results": [],
                    "top3": [],
                    "count": 0,
                    "time_ms": 0.0,
                    "note": "no text embedder in offline mode",
                }
            elif config.jaccard_only and adj is None:
                result = {
                    "config": config.name,
                    "query": query,
                    "results": [],
                    "top3": [],
                    "count": 0,
                    "time_ms": 0.0,
                    "note": "no graph data",
                }
            elif (
                not config.jaccard_only
                and config.weights
                and config.weights.embed > 0
                and embeddings is None
            ):
                result = {
                    "config": config.name,
                    "query": query,
                    "results": [],
                    "top3": [],
                    "count": 0,
                    "time_ms": 0.0,
                    "note": "no embeddings",
                }
            else:
                result = run_query(config, query, k, embeddings, adj)

            all_results.append(result)

            if not args.json:
                top3_str = (
                    ", ".join(result["top3"])
                    if result["top3"]
                    else result.get("note", "(no results)")
                )
                print(
                    f"{result['config']:<32s}\t{query:<35s}\t{top3_str:<80s}\t{result['time_ms']:>8.1f}"
                )

    if args.json:
        json.dump(
            {
                "game": game,
                "k": k,
                "configs": [c.name for c in configs],
                "queries": queries,
                "skipped_queries": skipped_queries,
                "results": all_results,
            },
            sys.stdout,
            indent=2,
        )
        print()
    else:
        print("-" * 165)
        if skipped_queries:
            print(f"\nSkipped (not in vocab): {', '.join(skipped_queries)}", file=sys.stderr)
        print(f"\nDone: {len(all_results)} evaluations.", file=sys.stderr)


if __name__ == "__main__":
    main()
