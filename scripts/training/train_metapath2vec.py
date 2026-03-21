#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#     "torch>=2.0.0",
#     "torch-geometric>=2.4.0",
#     "gensim>=4.3.0",
#     "numpy>=1.26.0",
# ]
# ///
"""
Train MetaPath2Vec embeddings on heterogeneous card graph.

Unlike PecanPy (homogeneous walks), MetaPath2Vec walks typed paths:
  card --[deck]--> card --[set]--> card --[keyword]--> card

This preserves signal per edge type instead of diluting them.
Uses PyG's MetaPath2Vec implementation.

Usage:
    uv run scripts/training/train_metapath2vec.py --game magic
    uv run scripts/training/train_metapath2vec.py --game magic --dim 128 --epochs 5
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch
from gensim.models import KeyedVectors

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))


def load_typed_edges(game: str) -> dict[str, list[tuple[str, str, float]]]:
    """Load all edge types for a game."""
    graph_dir = DATA_DIR / "graphs"
    edge_types = {}

    # Map file patterns to edge type names
    edge_files = {
        "deck": graph_dir / f"{game}_merged_all.edg",
        "enriched": graph_dir / f"{game}_merged_enriched.edg",
        "annotation": graph_dir / f"{game}_annotation_edges.edg",
        "set": graph_dir / f"{game}_set_cooccurrence.edg",
        "precon": graph_dir / f"{game}_precon_cooccurrence.edg",
        "keyword": graph_dir / f"{game}_keyword_sharing.edg",
        "archetype": graph_dir / f"{game}_archetype_cooccurrence.edg",
        "commander": graph_dir / f"{game}_archidekt_commander.edg",
        "diverse": graph_dir / f"{game}_diverse_annotation_edges.edg",
    }

    for etype, path in edge_files.items():
        if not path.exists():
            continue
        edges = []
        with open(path) as f:
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    try:
                        edges.append((parts[0], parts[1], float(parts[2])))
                    except ValueError:
                        continue
        if edges:
            edge_types[etype] = edges
            print(f"  {etype}: {len(edges):,} edges")

    return edge_types


def build_hetero_data(
    edge_types: dict[str, list[tuple[str, str, float]]],
) -> tuple[dict, list[str], dict[str, int]]:
    """Build heterogeneous graph data for PyG MetaPath2Vec."""
    # Collect all unique card names
    all_cards: set[str] = set()
    for edges in edge_types.values():
        for c1, c2, _ in edges:
            all_cards.add(c1)
            all_cards.add(c2)

    card_list = sorted(all_cards)
    card_to_idx = {name: i for i, name in enumerate(card_list)}
    print(f"  Total unique cards: {len(card_list):,}")

    # Build edge_index per type
    edge_index_dict = {}
    for etype, edges in edge_types.items():
        src, dst = [], []
        for c1, c2, _ in edges:
            i, j = card_to_idx[c1], card_to_idx[c2]
            src.extend([i, j])  # undirected
            dst.extend([j, i])
        edge_index_dict[("card", etype, "card")] = torch.tensor([src, dst], dtype=torch.long)
        print(f"  Edge type '{etype}': {len(src):,} directed edges")

    return edge_index_dict, card_list, card_to_idx


def train_metapath2vec(
    edge_index_dict: dict,
    num_nodes: int,
    metapaths: list[list[tuple[str, str, str]]],
    dim: int = 128,
    walk_length: int = 20,
    walks_per_node: int = 10,
    context_size: int = 7,
    num_negative_samples: int = 5,
    epochs: int = 5,
    batch_size: int = 128,
    lr: float = 0.01,
    loss_log_path: Path | None = None,
) -> tuple[np.ndarray, list[dict]]:
    """Train MetaPath2Vec and return embeddings."""
    from torch_geometric.nn import MetaPath2Vec

    model = MetaPath2Vec(
        edge_index_dict,
        embedding_dim=dim,
        metapath=metapaths[0],  # MetaPath2Vec uses one metapath
        walk_length=walk_length,
        context_size=context_size,
        walks_per_node=walks_per_node,
        num_negative_samples=num_negative_samples,
        num_nodes_dict={"card": num_nodes},
    )

    device = "cpu"  # MetaPath2Vec training is CPU-based in PyG
    model = model.to(device)
    # SparseAdam fails with dense gradients in some PyG versions; use Adam
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    loader = model.loader(batch_size=batch_size, shuffle=True)

    # Checkpoint dir
    ckpt_dir = Path(__file__).resolve().parent.parent.parent / "data" / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = ckpt_dir / f"metapath2vec_{num_nodes}n_{dim}d.pt"

    # Loss log (CSV: epoch, loss, wall_time_s)
    loss_history: list[dict] = []
    loss_csv = None
    loss_writer = None
    if loss_log_path:
        loss_log_path.parent.mkdir(parents=True, exist_ok=True)
        loss_csv = open(loss_log_path, "w", newline="")
        loss_writer = csv.DictWriter(loss_csv, fieldnames=["epoch", "loss", "wall_s"])
        loss_writer.writeheader()

    train_start = time.monotonic()

    # Resume from checkpoint if exists
    start_epoch = 0
    avg_loss = float("nan")
    if ckpt_path.exists():
        try:
            ckpt = torch.load(str(ckpt_path), weights_only=False)
            model.load_state_dict(ckpt["model"])
            optimizer.load_state_dict(ckpt["optimizer"])
            start_epoch = ckpt["epoch"] + 1
            avg_loss = ckpt["loss"]
            print(f"    Resumed from checkpoint: epoch {start_epoch} (loss {avg_loss:.4f})")
        except Exception as e:
            print(f"    Checkpoint load failed ({e}), starting fresh")

    if start_epoch >= epochs:
        print(f"    Already trained to epoch {start_epoch}, skipping (requested {epochs})")

    for epoch in range(start_epoch, epochs):
        model.train()
        total_loss = 0
        n_batches = 0
        for pos_rw, neg_rw in loader:
            optimizer.zero_grad()
            loss = model.loss(pos_rw.to(device), neg_rw.to(device))
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1

        avg_loss = total_loss / max(n_batches, 1)
        wall_s = time.monotonic() - train_start
        print(f"    Epoch {epoch + 1}/{epochs}: loss={avg_loss:.4f} ({wall_s:.0f}s)")

        row = {"epoch": epoch + 1, "loss": round(avg_loss, 6), "wall_s": round(wall_s, 1)}
        loss_history.append(row)
        if loss_writer:
            loss_writer.writerow(row)
            loss_csv.flush()

        # Checkpoint every 10 epochs
        if (epoch + 1) % 10 == 0:
            torch.save(
                {
                    "epoch": epoch,
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "loss": avg_loss,
                },
                str(ckpt_path),
            )

    # Final checkpoint
    torch.save(
        {
            "epoch": epochs - 1,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "loss": avg_loss,
        },
        str(ckpt_path),
    )

    if loss_csv:
        loss_csv.close()

    # Extract embeddings
    model.eval()
    with torch.no_grad():
        embeddings = model("card").cpu().numpy()

    return embeddings, loss_history


def main() -> int:
    parser = argparse.ArgumentParser(description="Train MetaPath2Vec embeddings")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--walk-length", type=int, default=20)
    parser.add_argument("--walks-per-node", type=int, default=10)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument(
        "--output-suffix",
        type=str,
        default="",
        help="Suffix for output filename (for parallel runs)",
    )
    parser.add_argument(
        "--edge-types",
        type=str,
        default="",
        help="Comma-separated edge types to use (default: all available). "
        "E.g. --edge-types deck,enriched,annotation",
    )
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"MetaPath2Vec Training [{args.game}]")
    print(f"{'=' * 60}")

    # Load edges
    print(f"\n[1/4] Loading typed edges...")
    edge_types = load_typed_edges(args.game)

    # Filter to requested edge types
    if args.edge_types:
        requested = [e.strip() for e in args.edge_types.split(",")]
        missing = [e for e in requested if e not in edge_types]
        if missing:
            print(f"  WARNING: requested edge types not found: {missing}")
        edge_types = {k: v for k, v in edge_types.items() if k in requested}
        print(f"  Filtered to: {list(edge_types.keys())}")

    if len(edge_types) < 2:
        print(f"Need at least 2 edge types for metapath. Found: {list(edge_types.keys())}")
        return 1

    # Build heterogeneous graph
    print(f"\n[2/4] Building heterogeneous graph...")
    edge_index_dict, card_list, card_to_idx = build_hetero_data(edge_types)

    # Define metapaths based on available edge types
    available = list(edge_types.keys())
    print(f"\n[3/4] Available edge types: {available}")

    # Build metapath: cycle through all edge types
    # Longer metapaths capture cross-type relationships
    metapath = []
    for etype in available:
        metapath.append(("card", etype, "card"))

    print(f"  Metapath: {' -> '.join(f'({s},{e},{t})' for s, e, t in metapath)}")

    # Prepare log paths
    suffix = f"_{args.output_suffix}" if args.output_suffix else ""
    logs_dir = DATA_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    loss_log_path = logs_dir / f"{args.game}_metapath2vec{suffix}_loss.csv"

    # Train
    print(f"\n[4/4] Training MetaPath2Vec (dim={args.dim}, epochs={args.epochs})...")
    t0 = time.monotonic()

    embeddings, loss_history = train_metapath2vec(
        edge_index_dict,
        num_nodes=len(card_list),
        metapaths=[metapath],
        dim=args.dim,
        walk_length=args.walk_length,
        walks_per_node=args.walks_per_node,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        loss_log_path=loss_log_path,
    )

    elapsed = time.monotonic() - t0
    print(f"\n  Training complete in {elapsed:.1f}s")
    print(f"  Loss log: {loss_log_path}")

    # L2 normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    embeddings = (embeddings / norms).astype(np.float32)

    # Save as KeyedVectors
    kv = KeyedVectors(vector_size=args.dim)
    kv.add_vectors(card_list, embeddings)

    suffix = f"_{args.output_suffix}" if args.output_suffix else ""
    out_path = DATA_DIR / "embeddings" / f"{args.game}_metapath2vec{suffix}.wv"
    kv.save(str(out_path))
    print(f"  Saved {len(kv):,} embeddings to {out_path}")

    # Quick quality check
    test_cards = {
        "magic": [("Lightning Bolt", "Lava Spike"), ("Sol Ring", "Arcane Signet")],
        "pokemon": [("Ultra Ball", "Nest Ball")],
        "yugioh": [("Ash Blossom & Joyous Spring", 'Maxx "C"')],
    }
    quality_pairs = {}
    pairs = test_cards.get(args.game, [])
    if pairs:
        print(f"\n  Quality pairs:")
        for c1, c2 in pairs:
            if c1 in kv and c2 in kv:
                sim = float(kv.similarity(c1, c2))
                print(f"    {c1} <-> {c2}: {sim:.4f}")
                quality_pairs[f"{c1} <-> {c2}"] = round(sim, 4)

    # Auto-eval: run eval_per_mode (offline, embedding-only)
    eval_results = None
    eval_script = PROJECT_ROOT / "scripts" / "evaluation" / "eval_per_mode.py"
    if eval_script.exists():
        print(f"\n  Running evaluation...")
        try:
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    str(eval_script),
                    "--game",
                    args.game,
                    "--embedding",
                    f"{args.game}_metapath2vec{suffix}",
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
                eval_results = {
                    args.game: {
                        "sub_ndcg": raw.get("mode_substitute", {}).get("ndcg_at_k"),
                        "syn_ndcg": raw.get("mode_synergy", {}).get("ndcg_at_k"),
                        "meta_ndcg": raw.get("mode_meta", {}).get("ndcg_at_k"),
                        "substitutability_ndcg": raw.get("substitutability_ndcg"),
                        "catalog_coverage": raw.get("catalog_coverage", {}).get("coverage_pct")
                        if isinstance(raw.get("catalog_coverage"), dict)
                        else raw.get("catalog_coverage"),
                        "novelty": raw.get("novelty", {}).get("mean_self_info")
                        if isinstance(raw.get("novelty"), dict)
                        else None,
                        "bias_ratio": raw.get("stratified_ndcg", {}).get("bias_ratio")
                        if isinstance(raw.get("stratified_ndcg"), dict)
                        else None,
                    }
                }
                m = eval_results[args.game]
                print(
                    f"    sub nDCG:  {m['sub_ndcg']:.4f}" if m["sub_ndcg"] else "    sub nDCG:  N/A"
                )
                print(
                    f"    syn nDCG:  {m['syn_ndcg']:.4f}" if m["syn_ndcg"] else "    syn nDCG:  N/A"
                )
                print(
                    f"    meta nDCG: {m['meta_ndcg']:.4f}"
                    if m["meta_ndcg"]
                    else "    meta nDCG: N/A"
                )
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
            print(f"    Eval failed: {e}")

    # Downstream task evals (offline, from embeddings + annotations)
    downstream = {}
    print(f"\n  Downstream evals...")

    # Contextual: for each annotated query, check if graded buckets rank correctly
    test_set_path = DATA_DIR / "test_sets" / f"annotated_{args.game}_v2.json"
    if test_set_path.exists():
        try:
            with open(test_set_path) as f:
                test_data = json.load(f)
            test_queries = test_data.get("queries", {})

            # Contextual recall: what fraction of highly/relevant cards appear in top-K?
            ctx_hits, ctx_total = 0, 0
            for qname, qdata in test_queries.items():
                hr = qdata.get("highly_relevant", []) + qdata.get("relevant", [])
                if not hr or qname not in kv:
                    continue
                try:
                    top_k_names = {c for c, _ in kv.most_similar(qname, topn=20)}
                    hits = sum(1 for c in hr if c in top_k_names)
                    ctx_hits += hits
                    ctx_total += len(hr)
                except KeyError:
                    pass

            if ctx_total > 0:
                ctx_recall = ctx_hits / ctx_total
                downstream["contextual_recall_at_20"] = round(ctx_recall, 4)
                print(f"    contextual recall@20: {ctx_recall:.3f} ({ctx_hits}/{ctx_total})")

            # Deck completion proxy: for queries with 5+ relevant cards,
            # use first 3 as seed, check if remaining appear in top-K
            comp_hits, comp_total = 0, 0
            for qname, qdata in test_queries.items():
                all_rel = (
                    qdata.get("highly_relevant", [])
                    + qdata.get("relevant", [])
                    + qdata.get("somewhat_relevant", [])
                )
                in_vocab = [c for c in all_rel if c in kv]
                if len(in_vocab) < 5:
                    continue
                seed = in_vocab[:3]
                targets = set(in_vocab[3:])
                # Average seed vectors, find similar
                try:
                    seed_vec = sum(kv[c] for c in seed) / len(seed)
                    norms = np.linalg.norm(seed_vec)
                    if norms > 0:
                        seed_vec /= norms
                    sims = kv.similar_by_vector(seed_vec, topn=30)
                    top_names = {c for c, _ in sims}
                    hits = sum(1 for c in targets if c in top_names)
                    comp_hits += hits
                    comp_total += len(targets)
                except Exception:
                    pass

            if comp_total > 0:
                comp_recall = comp_hits / comp_total
                downstream["completion_recall_at_30"] = round(comp_recall, 4)
                print(f"    completion recall@30: {comp_recall:.3f} ({comp_hits}/{comp_total})")

        except Exception as e:
            print(f"    Downstream eval failed: {e}")

    # Git SHA
    git_sha = "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            git_sha = result.stdout.strip()
    except FileNotFoundError:
        pass

    # Write JSON run summary
    run_summary = {
        "game": args.game,
        "model": "metapath2vec",
        "git_sha": git_sha,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "params": {
            "dim": args.dim,
            "epochs": args.epochs,
            "walk_length": args.walk_length,
            "walks_per_node": args.walks_per_node,
            "lr": args.lr,
            "batch_size": args.batch_size,
        },
        "data": {
            "edge_types": {k: len(v) for k, v in edge_types.items()},
            "num_cards": len(card_list),
            "metapath": [f"{s}-{e}-{t}" for s, e, t in metapath],
        },
        "training": {
            "duration_s": round(elapsed, 1),
            "final_loss": loss_history[-1]["loss"] if loss_history else None,
            "loss_log": str(loss_log_path),
        },
        "quality_pairs": quality_pairs,
        "eval": eval_results.get(args.game) if eval_results and args.game in eval_results else None,
        "downstream": downstream if downstream else None,
        "artifacts": {
            "embeddings": str(out_path),
            "checkpoint": str(
                DATA_DIR / "checkpoints" / f"metapath2vec_{len(card_list)}n_{args.dim}d.pt"
            ),
            "loss_log": str(loss_log_path),
        },
    }

    summary_path = logs_dir / f"{args.game}_metapath2vec{suffix}_run.json"
    with open(summary_path, "w") as f:
        json.dump(run_summary, f, indent=2)
    print(f"\n  Run summary: {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
