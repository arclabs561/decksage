#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#     "numpy>=1.26.0",
#     "gensim>=4.3.0",
#     "scipy>=1.12.0",
# ]
# ///
"""
Train Cleora-style embeddings at different iteration counts.

Cleora (Rychalska et al. 2021) uses iterated matrix multiplication on a
transition matrix. The key insight (Tkachuk et al. 2022):
  - 1 iteration  = complement embeddings (direct co-occurrence)
  - 5+ iterations = substitute embeddings (structural equivalence)

This gives us a dial between complement and substitute signal without
any labeled data.

We implement Cleora's core algorithm: random feature initialization,
then iterated averaging over neighbor features via sparse matrix multiply.

Usage:
    uv run scripts/training/train_cleora.py --game magic --iterations 1,3,5,7
    uv run scripts/training/train_cleora.py --game magic --iterations 6 --eval
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from scipy import sparse
from gensim.models import KeyedVectors

if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def load_edges(game: str) -> list[tuple[str, str, float]]:
    """Load all training-safe edge files for a game via shared registry."""
    sys.path.insert(0, str(Path(__file__).parent))
    from edge_registry import get_edge_files, load_edges_from_files

    graph_dir = DATA_DIR / "graphs"
    edge_files = get_edge_files(game, graph_dir)
    typed_edges = load_edges_from_files(edge_files)

    all_edges = []
    for edges in typed_edges.values():
        all_edges.extend(edges)

    return all_edges


def build_transition_matrix(
    edges: list[tuple[str, str, float]],
) -> tuple[sparse.csr_matrix, list[str], dict[str, int]]:
    """Build row-normalized transition matrix from edges."""
    # Collect nodes
    nodes: set[str] = set()
    for a, b, _ in edges:
        nodes.add(a)
        nodes.add(b)

    node_list = sorted(nodes)
    node_to_idx = {n: i for i, n in enumerate(node_list)}
    n = len(node_list)
    print(f"  {n:,} nodes")

    # Build adjacency (undirected, weighted)
    rows, cols, vals = [], [], []
    for a, b, w in edges:
        i, j = node_to_idx[a], node_to_idx[b]
        rows.extend([i, j])
        cols.extend([j, i])
        vals.extend([w, w])

    adj = sparse.csr_matrix((vals, (rows, cols)), shape=(n, n))

    # Row-normalize to get transition matrix
    row_sums = np.array(adj.sum(axis=1)).flatten()
    row_sums[row_sums == 0] = 1.0
    diag_inv = sparse.diags(1.0 / row_sums)
    transition = diag_inv @ adj

    return transition, node_list, node_to_idx


def cleora_embed(
    transition: sparse.csr_matrix,
    dim: int = 128,
    iterations: int = 5,
    seed: int = 42,
) -> np.ndarray:
    """Compute Cleora embeddings via iterated matrix multiplication.

    Initialize random features, then repeatedly average over neighbors.
    More iterations = more structural equivalence (substitute signal).
    Fewer iterations = more direct co-occurrence (complement signal).
    """
    n = transition.shape[0]
    rng = np.random.RandomState(seed)

    # Random initialization (Gaussian)
    X = rng.randn(n, dim).astype(np.float32)

    # L2 normalize
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    X = X / norms

    for it in range(iterations):
        X = transition @ X
        # L2 normalize after each iteration
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        X = X / norms

    return X


def main() -> int:
    parser = argparse.ArgumentParser(description="Train Cleora embeddings")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument(
        "--iterations",
        type=str,
        default="1,3,5,7",
        help="Comma-separated iteration counts to train",
    )
    parser.add_argument("--eval", action="store_true", help="Run eval after each")
    args = parser.parse_args()

    iter_counts = [int(x.strip()) for x in args.iterations.split(",")]

    print(f"{'=' * 60}")
    print(f"Cleora Embeddings [{args.game}]")
    print(f"  iterations: {iter_counts}")
    print(f"{'=' * 60}")

    # Load edges
    print(f"\n[1/3] Loading edges...")
    edges = load_edges(args.game)
    print(f"  Total: {len(edges):,} edges")

    # Build transition matrix
    print(f"\n[2/3] Building transition matrix...")
    transition, node_list, node_to_idx = build_transition_matrix(edges)

    # Train at each iteration count
    print(f"\n[3/3] Training embeddings...")
    results = []
    logs_dir = DATA_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    for n_iter in iter_counts:
        print(f"\n  --- {n_iter} iteration(s) ---")
        t0 = time.monotonic()
        embeddings = cleora_embed(transition, dim=args.dim, iterations=n_iter)
        elapsed = time.monotonic() - t0
        print(f"  Computed in {elapsed:.1f}s")

        # Save as KeyedVectors
        kv = KeyedVectors(vector_size=args.dim)
        kv.add_vectors(node_list, embeddings)

        suffix = f"cleora_{n_iter}iter"
        out_path = DATA_DIR / "embeddings" / f"{args.game}_{suffix}.wv"
        kv.save(str(out_path))
        print(f"  Saved {len(kv):,} embeddings to {out_path}")

        # Quality pairs
        from edge_registry import QUALITY_PAIRS

        quality = {}
        for c1, c2 in QUALITY_PAIRS.get(args.game, []):
            if c1 in kv and c2 in kv:
                sim = float(kv.similarity(c1, c2))
                quality[f"{c1} <-> {c2}"] = round(sim, 4)
                print(f"    {c1} <-> {c2}: {sim:.4f}")

        # Eval
        eval_metrics = None
        if args.eval:
            eval_script = PROJECT_ROOT / "scripts" / "evaluation" / "eval_per_mode.py"
            if eval_script.exists():
                try:
                    result = subprocess.run(
                        [
                            "uv",
                            "run",
                            str(eval_script),
                            "--game",
                            args.game,
                            "--embedding",
                            f"{args.game}_{suffix}",
                            "--json",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=300,
                        cwd=str(PROJECT_ROOT),
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        raw = json.loads(result.stdout)
                        if isinstance(raw, list):
                            raw = raw[0] if raw else {}
                        sub = raw.get("mode_substitute", {}).get("ndcg_at_k", 0)
                        syn = raw.get("mode_synergy", {}).get("ndcg_at_k", 0)
                        meta = raw.get("mode_meta", {}).get("ndcg_at_k", 0)
                        eval_metrics = {"sub": sub, "syn": syn, "meta": meta}
                        print(f"    sub nDCG:  {sub:.4f}")
                        print(f"    syn nDCG:  {syn:.4f}")
                        print(f"    meta nDCG: {meta:.4f}")
                except Exception as e:
                    print(f"    Eval failed: {e}")

        results.append(
            {
                "iterations": n_iter,
                "duration_s": round(elapsed, 1),
                "quality_pairs": quality,
                "eval": eval_metrics,
            }
        )

    # Write summary
    git_sha = "unknown"
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(PROJECT_ROOT),
        )
        if r.returncode == 0:
            git_sha = r.stdout.strip()
    except FileNotFoundError:
        pass

    summary = {
        "game": args.game,
        "model": "cleora",
        "git_sha": git_sha,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "params": {"dim": args.dim, "iterations": iter_counts},
        "data": {"num_nodes": len(node_list), "num_edges": len(edges)},
        "results": results,
    }

    summary_path = logs_dir / f"{args.game}_cleora_run.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  Run summary: {summary_path}")

    # Print comparison table
    if len(results) > 1 and all(r.get("eval") for r in results):
        print(f"\n{'=' * 50}")
        print(f"{'Iter':>6} {'sub':>8} {'syn':>8} {'meta':>8}")
        print("-" * 36)
        for r in results:
            ev = r["eval"]
            print(f"{r['iterations']:>6} {ev['sub']:>8.4f} {ev['syn']:>8.4f} {ev['meta']:>8.4f}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
