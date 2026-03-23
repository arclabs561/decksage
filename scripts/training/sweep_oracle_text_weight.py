#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim>=4.3.0", "numpy<2.0.0"]
# ///
"""
Sweep oracle_text edge weight multiplier per game.

Trains PecanPy embeddings with different oracle_text weights (other weights fixed),
fuses with card attributes, and evaluates nDCG. Outputs a comparison table.

Usage:
    uv run scripts/training/sweep_oracle_text_weight.py --game magic
    uv run scripts/training/sweep_oracle_text_weight.py  # all games
    uv run scripts/training/sweep_oracle_text_weight.py --weights 1,3,5,7,10
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VENV_PYTHON = str(PROJECT_ROOT / ".venv/bin/python")

sys.path.insert(0, str(PROJECT_ROOT / "src"))
from ml.data.incremental_graph import IncrementalCardGraph

GAME_CODE = {"magic": "MTG", "pokemon": "PKM", "yugioh": "YGO"}

# Fixed weights for non-oracle sources
BASE_WEIGHTS = {"ppmi": 1.0, "enriched": 5.0, "propagated": 3.0}

GAME_ATTRS = {
    "magic": "data/processed/card_attributes_enriched.csv",
    "pokemon": "data/processed/card_attributes_pokemon.csv",
    "yugioh": "data/processed/card_attributes_yugioh.csv",
}

GRADES = {
    "highly_relevant": 3,
    "relevant": 2,
    "somewhat_relevant": 1,
    "marginally_relevant": 0.5,
    "irrelevant": 0,
}


def dcg(scores: list[float], k: int) -> float:
    return sum(s / math.log2(i + 2) for i, s in enumerate(scores[:k]))


def ndcg(rels: list[float], k: int) -> float:
    d = dcg(rels, k)
    ideal = dcg(sorted(rels, reverse=True), k)
    return d / ideal if ideal > 0 else 0.0


def evaluate_embedding(emb_path: str, game: str) -> dict[str, float]:
    """Evaluate an embedding file, returning per-mode nDCG@10."""
    from gensim.models import KeyedVectors

    test_set = PROJECT_ROOT / f"data/test_sets/annotated_{game}_v2.json"
    if not test_set.exists():
        return {}

    kv = KeyedVectors.load(str(emb_path))
    data = json.load(open(test_set))
    queries = data.get("queries", data)

    mode_scores: dict[str, list[float]] = {}
    for q in queries:
        query_card = q.get("query") or q.get("card1")
        if query_card not in kv:
            continue
        mode = q.get("mode", "substitute")
        rels = []
        for bucket_name, cards in q.get("relevance_buckets", {}).items():
            grade = GRADES.get(bucket_name, 0)
            for _ in cards:
                rels.append(grade)

        # Rank by cosine similarity
        candidates = []
        for bucket_name, cards in q.get("relevance_buckets", {}).items():
            for c in cards:
                if c in kv:
                    sim = kv.similarity(query_card, c)
                    candidates.append((c, sim, GRADES.get(bucket_name, 0)))

        if not candidates:
            continue

        candidates.sort(key=lambda x: -x[1])
        ranked_rels = [c[2] for c in candidates]
        score = ndcg(ranked_rels, 10)
        mode_scores.setdefault(mode, []).append(score)

    return {mode: sum(s) / len(s) for mode, s in mode_scores.items() if s}


def run_sweep(game: str, oracle_weights: list[float]) -> list[dict]:
    """Run sweep for one game."""
    db_path = PROJECT_ROOT / "data" / "graphs" / f"{game}_unified.db"
    if not db_path.exists():
        print(f"  [SKIP] No unified graph for {game} at {db_path}")
        return []

    game_code = GAME_CODE[game]
    graph = IncrementalCardGraph(graph_path=db_path, use_sqlite=True)
    results = []

    for ot_weight in oracle_weights:
        tag = f"sweep_ot{ot_weight:.0f}"
        edgelist_path = PROJECT_ROOT / "data" / "graphs" / f"{game}_{tag}.edg"
        emb_path = PROJECT_ROOT / "data" / "embeddings" / f"{game}_{tag}.wv"
        fused_path = PROJECT_ROOT / "data" / "embeddings" / f"{game}_{tag}_fused.wv"

        weights = {**BASE_WEIGHTS, "oracle_text": ot_weight}
        print(f"\n--- {game} oracle_text={ot_weight} ---")

        # 1. Export edgelist with this weight config
        print(f"  Exporting edgelist (weights: {weights})...")
        graph.export_edgelist_filtered(
            output_path=edgelist_path,
            game=game_code,
            source_types=list(weights.keys()),
            weights=weights,
            min_weight=0.0,
        )

        # 2. Train PecanPy
        print(f"  Training PecanPy -> {emb_path.name}...")
        ret = subprocess.run(
            [
                VENV_PYTHON,
                "scripts/training/train_blended_embeddings.py",
                "--edgelist", str(edgelist_path),
                "--weight", "1.0",
                "--output", str(emb_path),
                "--dim", "128",
                "--walks", "10",
                "--walk-length", "80",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
        )
        if ret.returncode != 0:
            print(f"  ERROR training: {ret.stderr.decode()[-200:]}")
            continue

        # 3. Fuse with card attributes
        card_attrs = GAME_ATTRS.get(game)
        if card_attrs:
            print(f"  Fusing -> {fused_path.name}...")
            ret = subprocess.run(
                [
                    VENV_PYTHON,
                    "scripts/training/fuse_embeddings.py",
                    "--embeddings", str(emb_path),
                    "--card-attrs", card_attrs,
                    "--output", str(fused_path),
                    "--alpha", "0.7",
                    "--dim", "128",
                ],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
            )
            if ret.returncode != 0:
                print(f"  ERROR fusing: {ret.stderr.decode()[-200:]}")
                continue
            eval_path = str(fused_path)
        else:
            eval_path = str(emb_path)

        # 4. Evaluate
        print(f"  Evaluating...")
        scores = evaluate_embedding(eval_path, game)
        result = {"game": game, "oracle_text_weight": ot_weight, **scores}
        results.append(result)
        print(f"  Results: {scores}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep oracle_text edge weight")
    parser.add_argument("--game", choices=["magic", "pokemon", "yugioh", "all"], default="all")
    parser.add_argument("--weights", default="1,3,5,7,10",
                        help="Comma-separated oracle_text weight multipliers")
    args = parser.parse_args()

    oracle_weights = [float(w) for w in args.weights.split(",")]
    games = ["magic", "pokemon", "yugioh"] if args.game == "all" else [args.game]

    all_results = []
    for game in games:
        print(f"\n{'=' * 60}")
        print(f"  SWEEP: {game.upper()} oracle_text weights: {oracle_weights}")
        print(f"{'=' * 60}")
        all_results.extend(run_sweep(game, oracle_weights))

    # Summary table
    if all_results:
        print(f"\n{'=' * 60}")
        print("  SWEEP RESULTS")
        print(f"{'=' * 60}")
        print(f"{'game':<10} {'ot_wt':>6} {'sub':>8} {'syn':>8} {'meta':>8}")
        print("-" * 44)
        for r in all_results:
            sub = r.get("substitute", 0)
            syn = r.get("synergy", 0)
            meta = r.get("meta", 0)
            print(f"{r['game']:<10} {r['oracle_text_weight']:>6.0f} {sub:>8.4f} {syn:>8.4f} {meta:>8.4f}")

    # Save results
    out_path = PROJECT_ROOT / "data" / "experiments" / "sweep_oracle_text_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(all_results, open(out_path, "w"), indent=2)
    print(f"\nResults saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
