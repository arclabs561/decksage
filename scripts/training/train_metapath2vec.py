#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
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
) -> torch.Tensor:
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

    for epoch in range(epochs):
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
        print(f"    Epoch {epoch + 1}/{epochs}: loss={avg_loss:.4f}")

    # Extract embeddings
    model.eval()
    with torch.no_grad():
        embeddings = model("card").cpu().numpy()

    return embeddings


def main() -> int:
    parser = argparse.ArgumentParser(description="Train MetaPath2Vec embeddings")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--walk-length", type=int, default=20)
    parser.add_argument("--walks-per-node", type=int, default=10)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"MetaPath2Vec Training [{args.game}]")
    print(f"{'=' * 60}")

    # Load edges
    print(f"\n[1/4] Loading typed edges...")
    edge_types = load_typed_edges(args.game)
    if len(edge_types) < 2:
        print(f"Need at least 2 edge types for metapath. Found: {list(edge_types.keys())}")
        return 1

    # Build heterogeneous graph
    print(f"\n[2/4] Building heterogeneous graph...")
    edge_index_dict, card_list, card_to_idx = build_hetero_data(edge_types)

    # Define metapaths based on available edge types
    available = list(edge_types.keys())
    print(f"\n[3/4] Available edge types: {available}")

    # Build metapath: walk through different edge types
    # e.g., card -[deck]-> card -[set]-> card -[deck]-> card
    metapath = []
    for etype in available[:3]:  # use up to 3 edge types in the path
        metapath.append(("card", etype, "card"))

    print(f"  Metapath: {' -> '.join(f'({s},{e},{t})' for s, e, t in metapath)}")

    # Train
    print(f"\n[4/4] Training MetaPath2Vec (dim={args.dim}, epochs={args.epochs})...")
    t0 = time.monotonic()

    embeddings = train_metapath2vec(
        edge_index_dict,
        num_nodes=len(card_list),
        metapaths=[metapath],
        dim=args.dim,
        walk_length=args.walk_length,
        walks_per_node=args.walks_per_node,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )

    elapsed = time.monotonic() - t0
    print(f"\n  Training complete in {elapsed:.1f}s")

    # L2 normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    embeddings = (embeddings / norms).astype(np.float32)

    # Save as KeyedVectors
    kv = KeyedVectors(vector_size=args.dim)
    kv.add_vectors(card_list, embeddings)

    out_path = DATA_DIR / "embeddings" / f"{args.game}_metapath2vec.wv"
    kv.save(str(out_path))
    print(f"  Saved {len(kv):,} embeddings to {out_path}")

    # Quick quality check
    test_cards = {
        "magic": [("Lightning Bolt", "Lava Spike"), ("Sol Ring", "Arcane Signet")],
        "pokemon": [("Ultra Ball", "Nest Ball")],
        "yugioh": [("Ash Blossom & Joyous Spring", 'Maxx "C"')],
    }
    pairs = test_cards.get(args.game, [])
    if pairs:
        print(f"\n  Quality pairs:")
        for c1, c2 in pairs:
            if c1 in kv and c2 in kv:
                sim = float(kv.similarity(c1, c2))
                print(f"    {c1} <-> {c2}: {sim:.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
