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


def evaluate_embedding(emb_path: str, game: str) -> dict[str, float]:
    """Evaluate via canonical eval_per_mode.py, returning per-mode nDCG@10."""
    # eval_per_mode expects just the stem name, not a full path
    emb_name = Path(emb_path).stem  # e.g. "magic_sweep_ot5_fused"

    ret = subprocess.run(
        [
            VENV_PYTHON,
            "scripts/evaluation/eval_per_mode.py",
            "--game", game,
            "--embedding", emb_name,
            "--json",
        ],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
    )
    if ret.returncode != 0:
        print(f"  ERROR evaluating: {ret.stderr.decode()[-200:]}")
        return {}

    # Parse JSON array output from eval_per_mode.py
    try:
        data = json.loads(ret.stdout.decode())
        if isinstance(data, list) and data:
            r = data[0]
            results = {}
            for mode in ("substitute", "synergy", "meta"):
                mode_key = f"mode_{mode}"
                if mode_key in r and isinstance(r[mode_key], dict):
                    results[mode] = r[mode_key].get("ndcg_at_k", 0.0)
            if "overall_ndcg" in r:
                results["overall"] = r["overall_ndcg"].get("ndcg_at_k", 0.0)
            return results
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"  ERROR parsing eval output: {e}")

    return {}


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
                "--edgelist",
                str(edgelist_path),
                "--weight",
                "1.0",
                "--output",
                str(emb_path),
                "--dim",
                "128",
                "--walks",
                "10",
                "--walk-length",
                "80",
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
                    "--embeddings",
                    str(emb_path),
                    "--card-attrs",
                    card_attrs,
                    "--output",
                    str(fused_path),
                    "--alpha",
                    "0.7",
                    "--dim",
                    "128",
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
    parser.add_argument(
        "--weights", default="1,3,5,7,10", help="Comma-separated oracle_text weight multipliers"
    )
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
            print(
                f"{r['game']:<10} {r['oracle_text_weight']:>6.0f} {sub:>8.4f} {syn:>8.4f} {meta:>8.4f}"
            )

    # Save results
    out_path = PROJECT_ROOT / "data" / "experiments" / "sweep_oracle_text_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(all_results, open(out_path, "w"), indent=2)
    print(f"\nResults saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
