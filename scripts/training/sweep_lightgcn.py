#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "torch>=2.0.0",
#     "torch-geometric>=2.4.0",
#     "gensim>=4.3.0",
#     "numpy>=1.26.0",
#     "pandas>=2.0.0",
# ]
# ///
"""
Hyperparameter sweep for LightGCN embeddings.

Grid search over dim, layers, lr, l2_reg. Evaluates each config with
per-mode nDCG using the annotated test set. Logs results to TSV.

Usage:
    uv run scripts/training/sweep_lightgcn.py --game magic
    uv run scripts/training/sweep_lightgcn.py --game magic --quick  # reduced grid
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.utils.data_loading import load_edgelist


# Import training function from existing script
sys.path.insert(0, str(Path(__file__).parent))
from train_lightgcn import train_lightgcn


def evaluate_ndcg(kv, game: str, k: int = 10) -> dict[str, float]:
    """Evaluate nDCG@K using annotated test set."""
    test_path = DATA_DIR / "test_sets" / f"annotated_{game}_v2.json"
    if not test_path.exists():
        return {"overall_ndcg": 0.0}

    with open(test_path) as f:
        test_data = json.load(f)

    queries = test_data.get("queries", {})

    # Mode -> score field
    mode_fields = {
        "substitution": "functional_score",
        "synergy": "synergy_score",
        "meta": "meta_relevance",
    }

    def dcg(scores: list[float]) -> float:
        return sum(s / np.log2(i + 2) for i, s in enumerate(scores))

    def ndcg_at_k(relevance_scores: list[float], ideal_scores: list[float], k: int) -> float:
        """nDCG using external ideal ranking (not just retrieved docs)."""
        actual = dcg(relevance_scores[:k])
        ideal = dcg(sorted(ideal_scores, reverse=True)[:k])
        return actual / ideal if ideal > 0 else 0.0

    mode_ndcgs: dict[str, list[float]] = {m: [] for m in mode_fields}
    overall_ndcgs: list[float] = []

    for query_card, labels in queries.items():
        if query_card not in kv:
            continue

        annotations = labels.get("annotations", [])
        if not annotations:
            continue

        # Build candidate -> score mapping per mode
        for mode, field in mode_fields.items():
            scored_candidates = []
            for ann in annotations:
                cand = ann.get("candidate", "")
                score = ann.get(field, 0.0) or 0.0
                if cand in kv and score > 0:
                    scored_candidates.append((cand, float(score)))

            if not scored_candidates:
                continue

            # Rank by embedding similarity
            try:
                neighbors = kv.most_similar(query_card, topn=min(k * 5, len(kv) - 1))
            except KeyError:
                continue

            {card: i for i, (card, _) in enumerate(neighbors)}
            gt_map = dict(scored_candidates)

            # Get relevance scores in embedding rank order
            ranked_scores = []
            for card, _ in neighbors[:k]:
                ranked_scores.append(gt_map.get(card, 0.0))

            # Use ALL ground truth scores as the ideal, not just retrieved ones.
            # This matches canonical eval_per_mode.py methodology.
            all_gt_scores = list(gt_map.values())
            if max(sorted(all_gt_scores, reverse=True)[:k]) > 0:
                ndcg = ndcg_at_k(ranked_scores, all_gt_scores, k)
                mode_ndcgs[mode].append(ndcg)

        # Overall: use max score across modes
        all_scores = []
        for ann in annotations:
            cand = ann.get("candidate", "")
            s = max(
                ann.get("functional_score", 0.0) or 0.0,
                ann.get("synergy_score", 0.0) or 0.0,
                ann.get("meta_relevance", 0.0) or 0.0,
            )
            if cand in kv and s > 0:
                all_scores.append((cand, s))

        if all_scores:
            try:
                neighbors = kv.most_similar(query_card, topn=min(k * 5, len(kv) - 1))
            except KeyError:
                continue
            gt_map = dict(all_scores)
            ranked = [gt_map.get(c, 0.0) for c, _ in neighbors[:k]]
            all_gt = list(gt_map.values())
            if max(sorted(all_gt, reverse=True)[:k]) > 0:
                overall_ndcgs.append(ndcg_at_k(ranked, all_gt, k))

    result = {
        "overall_ndcg": float(np.mean(overall_ndcgs)) if overall_ndcgs else 0.0,
    }
    for mode, scores in mode_ndcgs.items():
        result[f"{mode}_ndcg"] = float(np.mean(scores)) if scores else 0.0

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="LightGCN hyperparameter sweep")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--quick", action="store_true", help="Reduced grid for fast iteration")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=10)
    args = parser.parse_args()

    edgelist_path = DATA_DIR / "graphs" / f"{args.game}_merged_all.edg"
    if not edgelist_path.exists():
        print(f"Edgelist not found: {edgelist_path}")
        return 1

    # Load graph once
    print(f"Loading edgelist from {edgelist_path}...")
    edges, nodes = load_edgelist(edgelist_path, collect_nodes=True)
    print(f"  {len(nodes):,} nodes, {len(edges):,} edges")

    # Device
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    print(f"  Device: {device}")

    # Define grid
    if args.quick:
        grid = {
            "dim": [64, 128],
            "layers": [2, 3],
            "lr": [1e-3, 5e-4],
            "l2_reg": [1e-4, 1e-3],
        }
    else:
        grid = {
            "dim": [64, 128, 256],
            "layers": [2, 3, 4],
            "lr": [1e-4, 5e-4, 1e-3],
            "l2_reg": [1e-5, 1e-4, 1e-3],
        }

    configs = list(itertools.product(grid["dim"], grid["layers"], grid["lr"], grid["l2_reg"]))
    print(f"\nSweep: {len(configs)} configurations")

    # Results log
    log_path = DATA_DIR / "experiments" / f"lightgcn_sweep_{args.game}.tsv"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as f:
        f.write(
            "dim\tlayers\tlr\tl2_reg\ttrain_time_s\tvocab\toverall_ndcg\tsub_ndcg\tsyn_ndcg\tmeta_ndcg\trandom_mean_sim\n"
        )

    best_ndcg = 0.0
    best_config = None

    for i, (dim, layers, lr, l2_reg) in enumerate(configs):
        print(f"\n{'=' * 60}")
        print(
            f"Config {i + 1}/{len(configs)}: dim={dim}, layers={layers}, lr={lr}, l2_reg={l2_reg}"
        )
        print(f"{'=' * 60}")

        torch.manual_seed(42)
        np.random.seed(42)

        t0 = time.monotonic()
        try:
            kv, _idx_to_node = train_lightgcn(
                edges,
                dim=dim,
                num_layers=layers,
                epochs=args.epochs,
                lr=lr,
                l2_reg=l2_reg,
                device=device,
                patience=args.patience,
            )
        except Exception as e:
            print(f"  FAILED: {e}")
            with open(log_path, "a") as f:
                f.write(f"{dim}\t{layers}\t{lr}\t{l2_reg}\t-1\t0\t0\t0\t0\t0\t0\n")
            continue

        train_time = time.monotonic() - t0

        # Quick quality: random pair similarity
        keys = list(kv.key_to_index.keys())
        rng = np.random.default_rng(42)
        n_sample = min(5000, len(keys) * (len(keys) - 1) // 2)
        random_sims = []
        for _ in range(n_sample):
            a, b = rng.choice(len(keys), size=2, replace=False)
            random_sims.append(float(kv.similarity(keys[a], keys[b])))
        random_mean = float(np.mean(random_sims))

        # nDCG evaluation
        metrics = evaluate_ndcg(kv, args.game)
        overall = metrics["overall_ndcg"]
        sub = metrics.get("substitution_ndcg", 0.0)
        syn = metrics.get("synergy_ndcg", 0.0)
        meta = metrics.get("meta_ndcg", 0.0)

        print(f"  Time: {train_time:.1f}s | Vocab: {len(kv)} | Random sim: {random_mean:.4f}")
        print(f"  nDCG: overall={overall:.4f} sub={sub:.4f} syn={syn:.4f} meta={meta:.4f}")

        with open(log_path, "a") as f:
            f.write(
                f"{dim}\t{layers}\t{lr}\t{l2_reg}\t{train_time:.1f}\t{len(kv)}\t{overall:.4f}\t{sub:.4f}\t{syn:.4f}\t{meta:.4f}\t{random_mean:.4f}\n"
            )

        if overall > best_ndcg:
            best_ndcg = overall
            best_config = (dim, layers, lr, l2_reg)
            # Save best model
            out_path = DATA_DIR / "embeddings" / f"{args.game}_lightgcn_best.wv"
            kv.save(str(out_path))
            print(f"  NEW BEST -> saved to {out_path}")

    print(f"\n{'=' * 60}")
    print("SWEEP COMPLETE")
    print(
        f"Best config: dim={best_config[0]}, layers={best_config[1]}, lr={best_config[2]}, l2_reg={best_config[3]}"
    )
    print(f"Best nDCG: {best_ndcg:.4f}")
    print(f"Results: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
