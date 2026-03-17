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
Train LightGCN embeddings on card co-occurrence graphs.

LightGCN (He et al., SIGIR 2020) strips GCN to pure neighborhood aggregation:
no feature transforms, no nonlinearity. Each layer is just symmetric-normalized
message passing, and the final embedding is the mean across all layer outputs
(layer 0 = raw embedding, layer K = K-hop aggregated).

Training uses BPR loss on co-occurrence edges with random negative sampling.

Usage:
    uv run scripts/training/train_lightgcn.py \\
        --game magic \\
        --edgelist data/graphs/magic_merged_all.edg \\
        --output data/embeddings/magic_lightgcn.wv \\
        --dim 128 --layers 3 --epochs 100 --lr 1e-3

    # All 3 games:
    for game in magic pokemon yugioh; do
        uv run scripts/training/train_lightgcn.py \\
            --game $game \\
            --edgelist data/graphs/${game}_merged_all.edg \\
            --output data/embeddings/${game}_lightgcn.wv
    done
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from gensim.models import KeyedVectors
from torch_geometric.nn import MessagePassing

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.utils.data_loading import load_edgelist


# ---------------------------------------------------------------------------
# LightGCN model
# ---------------------------------------------------------------------------


class LightGCNConv(MessagePassing):
    """Single LightGCN propagation layer.

    Computes: X' = D^{-1/2} A D^{-1/2} X (symmetric normalized aggregation).
    No learnable parameters -- the only learnable part is the embedding table.
    Supports weighted edges: messages are scaled by edge weight before aggregation.
    """

    def __init__(self):
        super().__init__(aggr="add")

    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_weight: torch.Tensor,
        norm: torch.Tensor,
    ) -> torch.Tensor:
        # norm is precomputed D^{-1/2}[src] * D^{-1/2}[dst] per edge
        return self.propagate(edge_index, x=x, edge_weight=edge_weight, norm=norm)

    def message(
        self,
        x_j: torch.Tensor,
        edge_weight: torch.Tensor,
        norm: torch.Tensor,
    ) -> torch.Tensor:
        return norm.unsqueeze(-1) * edge_weight.unsqueeze(-1) * x_j


class LightGCN(nn.Module):
    """LightGCN: pure neighborhood aggregation with layer-mean readout.

    Args:
        num_nodes: Number of nodes in the graph.
        embedding_dim: Embedding dimension.
        num_layers: Number of propagation layers (K in the paper).
    """

    def __init__(self, num_nodes: int, embedding_dim: int, num_layers: int = 3):
        super().__init__()
        self.num_layers = num_layers
        self.embedding = nn.Embedding(num_nodes, embedding_dim)
        nn.init.xavier_uniform_(self.embedding.weight)
        self.convs = nn.ModuleList([LightGCNConv() for _ in range(num_layers)])

    def forward(
        self,
        edge_index: torch.Tensor,
        edge_weight: torch.Tensor,
        norm: torch.Tensor,
    ) -> torch.Tensor:
        x = self.embedding.weight
        all_embeddings = [x]

        for conv in self.convs:
            x = conv(x, edge_index, edge_weight, norm)
            all_embeddings.append(x)

        # Average across all layers (LightGCN's key insight)
        return torch.stack(all_embeddings, dim=0).mean(dim=0)


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph(
    edges: list[tuple[str, str, float]],
) -> tuple[dict[str, int], list[str], torch.Tensor, torch.Tensor]:
    """Build node index and undirected edge_index + edge_weight tensors.

    Returns:
        node_to_idx: card name -> integer index
        idx_to_node: integer index -> card name
        edge_index: [2, 2*E] tensor (undirected: both directions)
        edge_weight: [2*E] tensor
    """
    node_to_idx: dict[str, int] = {}
    for c1, c2, _ in edges:
        if c1 not in node_to_idx:
            node_to_idx[c1] = len(node_to_idx)
        if c2 not in node_to_idx:
            node_to_idx[c2] = len(node_to_idx)

    idx_to_node = [""] * len(node_to_idx)
    for name, idx in node_to_idx.items():
        idx_to_node[idx] = name

    src, dst, weights = [], [], []
    for c1, c2, w in edges:
        i, j = node_to_idx[c1], node_to_idx[c2]
        # Undirected: add both directions
        src.extend([i, j])
        dst.extend([j, i])
        weights.extend([w, w])

    edge_index = torch.tensor([src, dst], dtype=torch.long)
    edge_weight = torch.tensor(weights, dtype=torch.float32)

    # Normalize edge weights to [0, 1] range
    if edge_weight.max() > 0:
        edge_weight = edge_weight / edge_weight.max()

    return node_to_idx, idx_to_node, edge_index, edge_weight


def compute_norm(
    edge_index: torch.Tensor,
    edge_weight: torch.Tensor,
    num_nodes: int,
) -> torch.Tensor:
    """Compute symmetric normalization coefficients: D^{-1/2}[src] * D^{-1/2}[dst].

    Uses weighted degree: D[i] = sum of edge weights incident to node i.
    """
    row, col = edge_index
    # Weighted degree
    deg = torch.zeros(num_nodes, dtype=edge_weight.dtype, device=edge_weight.device)
    deg.scatter_add_(0, row, edge_weight)
    deg_inv_sqrt = deg.pow(-0.5)
    deg_inv_sqrt[deg_inv_sqrt == float("inf")] = 0.0
    return deg_inv_sqrt[row] * deg_inv_sqrt[col]


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def bpr_loss(
    emb: torch.Tensor,
    pos_src: torch.Tensor,
    pos_dst: torch.Tensor,
    neg_dst: torch.Tensor,
    edge_weight: torch.Tensor | None = None,
) -> torch.Tensor:
    """Bayesian Personalized Ranking loss.

    For each positive edge (u, v) with negative sample n:
        loss = -log(sigma(score(u,v) - score(u,n)))

    Optionally weighted by edge weight (higher co-occurrence = more important).
    """
    pos_scores = (emb[pos_src] * emb[pos_dst]).sum(dim=1)
    neg_scores = (emb[pos_src] * emb[neg_dst]).sum(dim=1)
    diff = pos_scores - neg_scores

    if edge_weight is not None:
        loss = -F.logsigmoid(diff) * edge_weight
    else:
        loss = -F.logsigmoid(diff)

    return loss.mean()


def train_val_split(
    edge_index: torch.Tensor,
    edge_weight: torch.Tensor,
    val_ratio: float = 0.1,
    seed: int = 42,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Split edges into train/val sets.

    Since edges are stored as undirected pairs (i->j and j->i), we split
    by unique undirected edges then reconstruct both directions.
    """
    num_edges = edge_index.shape[1]
    # Each undirected edge appears twice (i->j and j->i)
    half = num_edges // 2

    rng = torch.Generator().manual_seed(seed)
    perm = torch.randperm(half, generator=rng)
    n_val = max(1, int(half * val_ratio))
    val_idx = perm[:n_val]
    train_idx = perm[n_val:]

    # Original edges are stored as pairs: [0..half-1] and [half..2*half-1]
    # where edge i and edge i+half are the same undirected edge in both directions.
    # But build_graph interleaves them: (i->j, j->i, i2->j2, j2->i2, ...)
    # So edge 2k and 2k+1 are the same undirected edge.
    train_edge_idx = torch.stack([train_idx * 2, train_idx * 2 + 1]).flatten().sort().values
    val_edge_idx = torch.stack([val_idx * 2, val_idx * 2 + 1]).flatten().sort().values

    train_edge_index = edge_index[:, train_edge_idx]
    train_edge_weight = edge_weight[train_edge_idx]
    val_edge_index = edge_index[:, val_edge_idx]
    val_edge_weight = edge_weight[val_edge_idx]

    return train_edge_index, train_edge_weight, val_edge_index, val_edge_weight


def train_lightgcn(
    edges: list[tuple[str, str, float]],
    dim: int = 128,
    num_layers: int = 3,
    epochs: int = 100,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
    batch_size: int = 2048,
    val_ratio: float = 0.1,
    patience: int = 10,
    device: torch.device | None = None,
) -> tuple[KeyedVectors, list[str]]:
    """Train LightGCN and return embeddings as KeyedVectors.

    Returns:
        (kv, idx_to_node) tuple.
    """
    if device is None:
        device = torch.device("cpu")

    node_to_idx, idx_to_node, edge_index, edge_weight = build_graph(edges)
    num_nodes = len(node_to_idx)

    print(f"  Graph: {num_nodes:,} nodes, {edge_index.shape[1]:,} directed edges")

    # Train/val split
    train_ei, train_ew, val_ei, val_ew = train_val_split(
        edge_index, edge_weight, val_ratio=val_ratio
    )
    print(f"  Split: {train_ei.shape[1]:,} train edges, {val_ei.shape[1]:,} val edges")

    # Move to device
    train_ei = train_ei.to(device)
    train_ew = train_ew.to(device)
    val_ei = val_ei.to(device)
    val_ew = val_ew.to(device)
    # Full graph for forward pass (LightGCN propagates over the full graph)
    full_ei = edge_index.to(device)
    full_ew = edge_weight.to(device)
    full_norm = compute_norm(full_ei, full_ew, num_nodes).to(device)

    # Build adjacency set for negative sampling
    adj_set: set[tuple[int, int]] = set()
    for k in range(edge_index.shape[1]):
        adj_set.add((int(edge_index[0, k]), int(edge_index[1, k])))

    model = LightGCN(num_nodes, dim, num_layers).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)

    print(f"  Model: LightGCN, {num_layers} layers, dim={dim}")
    print(f"  Training: {epochs} epochs, lr={lr}, batch_size={batch_size}, patience={patience}")

    best_val_loss = float("inf")
    patience_counter = 0
    best_state = None

    model.train()
    for epoch in range(epochs):
        # Forward: propagate over full graph
        emb = model(full_ei, full_ew, full_norm)

        # Sample training batches from train edges
        # Train edges are undirected pairs; use only one direction (even indices)
        train_half = train_ei.shape[1] // 2
        perm = torch.randperm(train_half, device=device)

        epoch_loss = 0.0
        n_batches = 0

        for batch_start in range(0, train_half, batch_size):
            batch_idx = perm[batch_start : batch_start + batch_size]
            # Use even-indexed edges (one direction per undirected edge)
            edge_idx = batch_idx * 2
            pos_src = train_ei[0, edge_idx]
            pos_dst = train_ei[1, edge_idx]
            batch_weights = train_ew[edge_idx]

            # Negative sampling: random nodes not connected to source
            neg_dst = torch.randint(0, num_nodes, (pos_src.shape[0],), device=device)

            optimizer.zero_grad()
            loss = bpr_loss(emb, pos_src, pos_dst, neg_dst, batch_weights)

            # L2 regularization on embeddings of involved nodes only
            unique_nodes = torch.unique(torch.cat([pos_src, pos_dst, neg_dst]))
            reg_loss = weight_decay * model.embedding.weight[unique_nodes].pow(2).sum()
            total_loss = loss + reg_loss

            total_loss.backward()
            optimizer.step()

            # Re-forward after parameter update for next batch
            emb = model(full_ei, full_ew, full_norm)

            epoch_loss += loss.item()
            n_batches += 1

        avg_train_loss = epoch_loss / max(n_batches, 1)

        # Validation loss
        with torch.no_grad():
            emb = model(full_ei, full_ew, full_norm)
            val_half = val_ei.shape[1] // 2
            val_src = val_ei[0, ::2]  # even indices = one direction
            val_dst = val_ei[1, ::2]
            val_w = val_ew[::2]
            val_neg = torch.randint(0, num_nodes, (val_src.shape[0],), device=device)
            val_loss = bpr_loss(emb, val_src, val_dst, val_neg, val_w).item()

        if val_loss < best_val_loss - 1e-5:
            best_val_loss = val_loss
            patience_counter = 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            patience_counter += 1

        if (epoch + 1) % 10 == 0 or patience_counter >= patience:
            print(
                f"    Epoch {epoch + 1}/{epochs}  "
                f"train_loss={avg_train_loss:.4f}  val_loss={val_loss:.4f}  "
                f"patience={patience_counter}/{patience}"
            )

        if patience_counter >= patience:
            print(f"    Early stopping at epoch {epoch + 1}")
            break

    # Restore best model
    if best_state is not None:
        model.load_state_dict(best_state)

    # Extract final embeddings
    model.eval()
    with torch.no_grad():
        final_emb = model(full_ei, full_ew, full_norm).cpu().numpy()

    # L2-normalize
    norms = np.linalg.norm(final_emb, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    final_emb = (final_emb / norms).astype(np.float32)

    kv = KeyedVectors(vector_size=dim)
    kv.add_vectors(idx_to_node, final_emb)
    return kv, idx_to_node


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------


def quality_check(kv: KeyedVectors, edges: list[tuple[str, str, float]]) -> None:
    """Print embedding quality metrics: random-pair similarity and top-edge similarity."""
    keys = list(kv.key_to_index.keys())
    if len(keys) < 2:
        return

    rng = np.random.default_rng(42)
    n = min(10_000, len(keys) * (len(keys) - 1) // 2)
    random_sims = []
    for _ in range(n):
        i, j = rng.choice(len(keys), size=2, replace=False)
        random_sims.append(float(kv.similarity(keys[i], keys[j])))
    random_sims_arr = np.array(random_sims)

    print(f"\n--- Quality Metrics ---")
    print(f"  Vocabulary size: {len(kv)}")
    print(f"  Random-pair cosine similarity (n={n}):")
    print(
        f"    mean={random_sims_arr.mean():.4f}  std={random_sims_arr.std():.4f}  "
        f"min={random_sims_arr.min():.4f}  max={random_sims_arr.max():.4f}"
    )

    # Top-100 weighted edges
    top_edges = sorted(edges, key=lambda x: x[2], reverse=True)[:100]
    top_sims = []
    for c1, c2, w in top_edges:
        if c1 in kv and c2 in kv:
            top_sims.append(float(kv.similarity(c1, c2)))
    if top_sims:
        top_sims_arr = np.array(top_sims)
        print(f"  Top-100 weighted edges similarity:")
        print(
            f"    mean={top_sims_arr.mean():.4f}  std={top_sims_arr.std():.4f}  "
            f"min={top_sims_arr.min():.4f}  max={top_sims_arr.max():.4f}"
        )

    # Known quality pairs (same as other training scripts)
    quality_pairs = {
        "magic": [
            ("Lightning Bolt", "Fireball", 0.70),
            ("Swords to Plowshares", "Path to Exile", 0.70),
            ("Dark Ritual", "Cabal Ritual", 0.60),
        ],
        "yugioh": [
            ("Ash Blossom & Joyous Spring", 'Maxx "C"', 0.70),
            ("Monster Reborn", "Soul Charge", 0.50),
        ],
        "pokemon": [
            ("Ultra Ball", "Nest Ball", 0.30),
            ("Professor's Research", "Cynthia", 0.30),
        ],
    }
    for game, pairs in quality_pairs.items():
        printed_header = False
        for c1, c2, threshold in pairs:
            if c1 in kv and c2 in kv:
                if not printed_header:
                    print(f"  Quality pairs ({game}):")
                    printed_header = True
                sim = float(kv.similarity(c1, c2))
                status = "PASS" if sim >= threshold else "FAIL"
                print(f"    {c1} <-> {c2}: {sim:.4f} (threshold {threshold}) [{status}]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Train LightGCN embeddings on card co-occurrence graphs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--game", type=str, default="magic", help="Game name (for logging)")
    parser.add_argument("--edgelist", type=Path, required=True, help="Edgelist file (.edg)")
    parser.add_argument("--output", type=Path, required=True, help="Output .wv file")
    parser.add_argument("--dim", type=int, default=128, help="Embedding dimension")
    parser.add_argument("--layers", type=int, default=3, help="Number of LightGCN layers")
    parser.add_argument("--epochs", type=int, default=100, help="Max training epochs")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate")
    parser.add_argument("--weight-decay", type=float, default=1e-4, help="L2 regularization")
    parser.add_argument("--batch-size", type=int, default=2048, help="BPR batch size")
    parser.add_argument("--val-ratio", type=float, default=0.1, help="Validation edge ratio")
    parser.add_argument("--patience", type=int, default=10, help="Early stopping patience")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device: auto, cpu, mps, cuda",
    )
    parser.add_argument(
        "--max-edges",
        type=int,
        default=0,
        help="Subsample to top-K weighted edges (0=no limit)",
    )
    args = parser.parse_args()

    # Seed everything
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    # Device selection
    if args.device == "auto":
        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")
    else:
        device = torch.device(args.device)

    print("=" * 70)
    print(f"LightGCN Embedding Training  [{args.game}]  [device={device}]")
    print("=" * 70)

    # Load graph
    print(f"\n[1/3] Loading edgelist from {args.edgelist}...")
    edges, nodes = load_edgelist(args.edgelist, collect_nodes=True)
    print(f"  {len(nodes):,} nodes, {len(edges):,} edges")

    if args.max_edges > 0 and len(edges) > args.max_edges:
        edges.sort(key=lambda x: -x[2])
        edges = edges[: args.max_edges]
        print(f"  Subsampled to top {args.max_edges:,} edges by weight")

    # Train
    print(f"\n[2/3] Training LightGCN...")
    t0 = time.monotonic()
    kv, idx_to_node = train_lightgcn(
        edges,
        dim=args.dim,
        num_layers=args.layers,
        epochs=args.epochs,
        lr=args.lr,
        weight_decay=args.weight_decay,
        batch_size=args.batch_size,
        val_ratio=args.val_ratio,
        patience=args.patience,
        device=device,
    )
    elapsed = time.monotonic() - t0
    print(f"\n  Training complete in {elapsed:.1f}s")

    # Save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    kv.save(str(args.output))
    print(f"  Saved {len(kv):,} embeddings to {args.output}")

    # Quality
    print(f"\n[3/3] Quality check...")
    quality_check(kv, edges)

    print(f"\n{'=' * 70}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
