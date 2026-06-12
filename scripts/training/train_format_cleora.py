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
Train per-format Cleora embeddings and evaluate.

Different formats (Standard, Modern, Commander) have different metas
and different substitution relationships. This trains separate Cleora
embeddings per format using format-specific co-occurrence edges.

Usage:
    uv run scripts/training/train_format_cleora.py --game magic
    uv run scripts/training/train_format_cleora.py --game magic --formats standard,modern
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from gensim.models import KeyedVectors
from scipy import sparse


if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

sys.path.insert(0, str(Path(__file__).parent))
from edge_registry import QUALITY_PAIRS


def load_format_edges(game: str, fmt: str) -> list[tuple[str, str, float]]:
    """Load edges for a specific format."""
    graph_dir = DATA_DIR / "graphs"
    path = graph_dir / f"{game}_{fmt}_cooccurrence.edg"
    if not path.exists():
        print(f"  No edge file for {fmt}: {path}")
        return []

    edges = []
    with open(path) as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 3:
                try:
                    edges.append((parts[0], parts[1], float(parts[2])))
                except ValueError:
                    continue
    print(f"  {fmt}: {len(edges):,} edges")
    return edges


def cleora_embed(edges: list[tuple[str, str, float]], dim: int, iterations: int, seed: int = 42):
    """Cleora embeddings from edges."""
    nodes: set[str] = set()
    for a, b, _ in edges:
        nodes.add(a)
        nodes.add(b)

    node_list = sorted(nodes)
    node_to_idx = {n: i for i, n in enumerate(node_list)}
    n = len(node_list)

    rows, cols, vals = [], [], []
    for a, b, w in edges:
        i, j = node_to_idx[a], node_to_idx[b]
        rows.extend([i, j])
        cols.extend([j, i])
        vals.extend([w, w])

    adj = sparse.csr_matrix((vals, (rows, cols)), shape=(n, n))
    row_sums = np.array(adj.sum(axis=1)).flatten()
    row_sums[row_sums == 0] = 1.0
    transition = sparse.diags(1.0 / row_sums) @ adj

    rng = np.random.RandomState(seed)
    X = rng.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    X = X / norms

    for _ in range(iterations):
        X = transition @ X
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        X = X / norms

    return X, node_list


def main() -> int:
    parser = argparse.ArgumentParser(description="Train per-format Cleora embeddings")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument(
        "--formats",
        type=str,
        default="standard,modern,commander",
        help="Comma-separated formats to train",
    )
    args = parser.parse_args()

    formats = [f.strip() for f in args.formats.split(",")]

    print(f"{'=' * 60}")
    print(f"Per-Format Cleora [{args.game}]")
    print(f"  formats: {formats}, dim={args.dim}, iterations={args.iterations}")
    print(f"{'=' * 60}")

    results = []
    for fmt in formats:
        print(f"\n--- {fmt} ---")
        edges = load_format_edges(args.game, fmt)
        if not edges:
            continue

        t0 = time.monotonic()
        embeddings, node_list = cleora_embed(edges, args.dim, args.iterations)
        elapsed = time.monotonic() - t0

        kv = KeyedVectors(vector_size=args.dim)
        kv.add_vectors(node_list, embeddings)

        out_name = f"{args.game}_cleora_{fmt}_{args.iterations}iter"
        out_path = DATA_DIR / "embeddings" / f"{out_name}.wv"
        kv.save(str(out_path))
        print(f"  {len(kv):,} cards, {elapsed:.1f}s -> {out_path.name}")

        # Quality pairs
        for c1, c2 in QUALITY_PAIRS.get(args.game, []):
            if c1 in kv and c2 in kv:
                sim = float(kv.similarity(c1, c2))
                print(f"    {c1} <-> {c2}: {sim:.4f}")

        # Eval
        eval_script = PROJECT_ROOT / "scripts" / "evaluation" / "eval_per_mode.py"
        eval_metrics = None
        if eval_script.exists():
            try:
                r = subprocess.run(
                    [
                        "uv",
                        "run",
                        str(eval_script),
                        "--game",
                        args.game,
                        "--embedding",
                        out_name,
                        "--json",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(PROJECT_ROOT),
                )
                if r.returncode == 0 and r.stdout.strip():
                    raw = json.loads(r.stdout)
                    if isinstance(raw, list):
                        raw = raw[0] if raw else {}
                    sub = raw.get("mode_substitute", {}).get("ndcg_at_k", 0)
                    syn = raw.get("mode_synergy", {}).get("ndcg_at_k", 0)
                    ctx = raw.get("contextual_recall_at_20", {}).get("recall", 0)
                    comp = raw.get("completion_recall_at_30", {}).get("recall", 0)
                    eval_metrics = {"sub": sub, "syn": syn, "ctx": ctx, "comp": comp}
                    print(f"    sub nDCG: {sub:.4f}, ctx@20: {ctx:.4f}, comp@30: {comp:.4f}")
            except Exception as e:
                print(f"    Eval failed: {e}")

        results.append(
            {
                "format": fmt,
                "num_cards": len(node_list),
                "num_edges": len(edges),
                "duration_s": round(elapsed, 1),
                "eval": eval_metrics,
            }
        )

    # Comparison table
    if len(results) > 1:
        print(f"\n{'=' * 60}")
        print(f"{'Format':<15} {'Cards':>8} {'Edges':>10} {'sub':>8} {'ctx':>8} {'comp':>8}")
        print("-" * 60)
        for r in results:
            ev = r.get("eval") or {}
            print(
                f"{r['format']:<15} {r['num_cards']:>8,} {r['num_edges']:>10,} "
                f"{ev.get('sub', 0):>8.4f} {ev.get('ctx', 0):>8.4f} {ev.get('comp', 0):>8.4f}"
            )

    # Save summary
    logs_dir = DATA_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "game": args.game,
        "model": "cleora_format",
        "results": results,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    summary_path = logs_dir / f"{args.game}_cleora_format_run.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nRun summary: {summary_path}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
