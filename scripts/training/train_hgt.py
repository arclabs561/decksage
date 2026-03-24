#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#     "torch>=2.0.0",
#     "torch-geometric>=2.4.0",
#     "torch-sparse",
#     "gensim>=4.3.0",
#     "numpy>=1.24.0",
# ]
# ///
"""
Train HGT (Heterogeneous Graph Transformer) embeddings on typed card graph.

Unlike MetaPath2Vec (random walks on typed paths), HGT learns per-edge-type
attention weights via multi-head attention, so dominant edge types (Commander
16M edges) don't dilute minority signal (enriched 1.5M).

Reference: Hu et al. 2020, "Heterogeneous Graph Transformer"

Node features: card annotations (role, power_level, archetype) when available,
otherwise random init. Annotations are used as features only -- no annotation
edges are created (train/eval separation).

Training: self-supervised link prediction (default) or contrastive (InfoNCE)
loss on co-occurrence edges. Contrastive mode directly optimizes embedding
similarity between connected cards, which better aligns with downstream
similarity search tasks.

Usage:
    uv run scripts/training/train_hgt.py --game magic
    uv run scripts/training/train_hgt.py --game magic --epochs 50 --heads 4 --layers 3
    uv run scripts/training/train_hgt.py --game magic --batch-size 512 --num-neighbors 15,15
    uv run scripts/training/train_hgt.py --game magic --loss contrastive --temperature 0.07
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

# Force unbuffered stdout so logs appear immediately in redirected files
if not sys.stdout.isatty():
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from gensim.models import KeyedVectors

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))


# ---------------------------------------------------------------------------
# Data loading (via shared edge_registry)
# ---------------------------------------------------------------------------


def load_typed_edges(game: str) -> dict[str, list[tuple[str, str, float]]]:
    """Load all training-safe edge types for a game via edge_registry."""
    from edge_registry import get_edge_files, load_edges_from_files

    graph_dir = DATA_DIR / "graphs"
    edge_file_map = get_edge_files(game, graph_dir)
    edge_types = load_edges_from_files(edge_file_map)
    for etype, edges in edge_types.items():
        print(f"  {etype}: {len(edges):,} edges")

    return edge_types


def build_hetero_data(
    edge_types: dict[str, list[tuple[str, str, float]]],
    node_features: torch.Tensor | None = None,
) -> tuple[object, list[str], dict[str, int]]:
    """Build HeteroData object for PyG (compatible with NeighborLoader)."""
    from torch_geometric.data import HeteroData

    all_cards: set[str] = set()
    for edges in edge_types.values():
        for c1, c2, _ in edges:
            all_cards.add(c1)
            all_cards.add(c2)

    card_list = sorted(all_cards)
    card_to_idx = {name: i for i, name in enumerate(card_list)}
    num_nodes = len(card_list)
    print(f"  Total unique cards: {num_nodes:,}")

    data = HeteroData()

    # Node features (placeholder if not provided yet; will be replaced before training)
    if node_features is not None:
        data["card"].x = node_features
    else:
        data["card"].x = torch.zeros(num_nodes, 1)
    data["card"].num_nodes = num_nodes

    for etype, edges in edge_types.items():
        src, dst = [], []
        for c1, c2, _ in edges:
            i, j = card_to_idx[c1], card_to_idx[c2]
            src.extend([i, j])  # undirected
            dst.extend([j, i])
        data["card", etype, "card"].edge_index = torch.tensor([src, dst], dtype=torch.long)
        print(f"  Edge type '{etype}': {len(src):,} directed edges")

    return data, card_list, card_to_idx


# ---------------------------------------------------------------------------
# Node features from card annotations
# ---------------------------------------------------------------------------

# Role vocabulary for one-hot encoding
ROLE_VOCAB = [
    "threat",
    "removal",
    "utility",
    "combo_piece",
    "ramp",
    "draw",
    "protection",
    "tutor",
    "finisher",
    "enabler",
    "disruption",
    "support",
    "staple",
    "filler",
    "hate",
    "land",
    "other",
]

# Archetype vocabulary for multi-hot encoding
ARCHETYPE_VOCAB = [
    "Aggro",
    "Midrange",
    "Control",
    "Combo",
    "Tempo",
    "Ramp",
    "Stax",
    "Prison",
    "Mill",
    "Burn",
    "Tribal",
    "Reanimator",
    "Toolbox",
    "Voltron",
    "Storm",
    "Aristocrats",
    "Tokens",
    "Lands",
    "Enchantress",
    "Artifacts",
    "Other",
]


def load_node_features(
    game: str,
    card_list: list[str],
    card_to_idx: dict[str, int],
    dim: int,
) -> tuple[torch.Tensor, int]:
    """Load card annotations as node features.

    Feature vector per card:
      - role: one-hot (len ROLE_VOCAB)
      - secondary_roles: multi-hot (len ROLE_VOCAB)
      - power_level: scalar normalized to [0, 1]
      - is_staple: binary
      - complexity: scalar normalized to [0, 1]
      - archetype_fit: multi-hot (len ARCHETYPE_VOCAB)

    Total raw feature dim = 2*len(ROLE_VOCAB) + 3 + len(ARCHETYPE_VOCAB).
    Linearly projected to `dim` by the model.

    Falls back to random init for cards without annotations.
    """
    ann_path = DATA_DIR / "test_sets" / f"card_annotations_{game}.json"
    num_cards = len(card_list)
    role_dim = len(ROLE_VOCAB)
    arch_dim = len(ARCHETYPE_VOCAB)
    feat_dim = 2 * role_dim + 3 + arch_dim  # primary + secondary + scalars + archetypes

    role_to_idx = {r: i for i, r in enumerate(ROLE_VOCAB)}
    arch_to_idx = {a: i for i, a in enumerate(ARCHETYPE_VOCAB)}

    features = torch.zeros(num_cards, feat_dim)
    annotated = 0

    if ann_path.exists():
        with open(ann_path) as f:
            ann_data = json.load(f)
        cards = ann_data.get("cards", {})

        for card_name, card_ann in cards.items():
            if card_name not in card_to_idx:
                continue
            idx = card_to_idx[card_name]

            # Primary role (one-hot)
            role = card_ann.get("role", "")
            if role in role_to_idx:
                features[idx, role_to_idx[role]] = 1.0

            # Secondary roles (multi-hot, offset by role_dim)
            for sr in card_ann.get("secondary_roles", []):
                if sr in role_to_idx:
                    features[idx, role_dim + role_to_idx[sr]] = 1.0

            # Scalars
            offset = 2 * role_dim
            power = card_ann.get("power_level", 5)
            features[idx, offset] = power / 10.0  # normalize to [0, 1]
            features[idx, offset + 1] = 1.0 if card_ann.get("is_staple", False) else 0.0
            features[idx, offset + 2] = card_ann.get("complexity", 2) / 5.0

            # Archetype fit (multi-hot)
            arch_offset = offset + 3
            for arch in card_ann.get("archetype_fit", []):
                if arch in arch_to_idx:
                    features[idx, arch_offset + arch_to_idx[arch]] = 1.0

            annotated += 1

        print(f"  Card annotations: {annotated:,}/{num_cards:,} cards have features")
    else:
        print(f"  No card annotations found at {ann_path}, using zero-init")

    # For unannotated cards, leave as zeros (the model will learn from structure)
    return features, feat_dim


# ---------------------------------------------------------------------------
# HGT model
# ---------------------------------------------------------------------------


class HGTEncoder(nn.Module):
    """Heterogeneous Graph Transformer encoder for card embeddings.

    Uses HGTConv layers with per-edge-type attention to produce
    node embeddings that respect edge type heterogeneity.
    """

    def __init__(
        self,
        in_dim: int,
        hidden_dim: int,
        out_dim: int,
        num_heads: int,
        num_layers: int,
        edge_types: list[str],
    ):
        super().__init__()
        from torch_geometric.nn import HGTConv

        self.node_types = ["card"]
        metadata = (self.node_types, [("card", et, "card") for et in edge_types])

        # Project raw features to hidden dim
        self.input_proj = nn.Linear(in_dim, hidden_dim)

        # HGT layers
        self.convs = nn.ModuleList()
        for _ in range(num_layers):
            self.convs.append(
                HGTConv(
                    in_channels=hidden_dim,
                    out_channels=hidden_dim,
                    metadata=metadata,
                    heads=num_heads,
                )
            )

        # Output projection
        self.output_proj = nn.Linear(hidden_dim, out_dim)

    def forward(
        self,
        x_dict: dict[str, torch.Tensor],
        edge_index_dict: dict[tuple, torch.Tensor],
    ) -> dict[str, torch.Tensor]:
        # Project input features
        x_dict = {"card": F.relu(self.input_proj(x_dict["card"]))}

        # HGT message passing
        for conv in self.convs:
            x_dict = conv(x_dict, edge_index_dict)
            x_dict = {"card": F.relu(x_dict["card"])}

        # Final projection
        x_dict = {"card": self.output_proj(x_dict["card"])}
        return x_dict


# ---------------------------------------------------------------------------
# Link prediction training
# ---------------------------------------------------------------------------


def sample_negative_edges(
    edge_index: torch.Tensor,
    num_nodes: int,
    num_neg: int,
) -> torch.Tensor:
    """Sample negative edges (pairs not in edge_index)."""
    # Use a set for fast membership check
    existing = set()
    src, dst = edge_index[0], edge_index[1]
    for i in range(src.size(0)):
        existing.add((src[i].item(), dst[i].item()))

    neg_src, neg_dst = [], []
    attempts = 0
    max_attempts = num_neg * 10
    while len(neg_src) < num_neg and attempts < max_attempts:
        s = torch.randint(0, num_nodes, (num_neg,))
        d = torch.randint(0, num_nodes, (num_neg,))
        for i in range(num_neg):
            si, di = s[i].item(), d[i].item()
            if si != di and (si, di) not in existing:
                neg_src.append(si)
                neg_dst.append(di)
                if len(neg_src) >= num_neg:
                    break
        attempts += num_neg

    n = min(len(neg_src), num_neg)
    return torch.tensor([neg_src[:n], neg_dst[:n]], dtype=torch.long)


def compute_contrastive_loss(
    z: torch.Tensor,
    pos_edges: torch.Tensor,
    num_sub_nodes: int,
    neg_ratio: int,
    temperature: float,
) -> torch.Tensor:
    """InfoNCE / NT-Xent loss on mini-batch embeddings.

    For each positive pair (anchor, positive), samples `neg_ratio` random
    non-neighbor nodes as negatives. The loss pushes connected nodes together
    and unconnected nodes apart in embedding space.

    Args:
        z: L2-normalized node embeddings [num_sub_nodes, dim].
        pos_edges: [2, num_pos] edge index within the subgraph.
        num_sub_nodes: number of nodes in the subgraph.
        neg_ratio: number of negatives per positive pair.
        temperature: softmax temperature (lower = sharper).

    Returns:
        Scalar InfoNCE loss.
    """
    device = z.device
    num_pos = pos_edges.size(1)
    if num_pos == 0:
        return torch.tensor(0.0, device=device, requires_grad=True)

    anchors = z[pos_edges[0]]  # [num_pos, dim]
    positives = z[pos_edges[1]]  # [num_pos, dim]

    # Sample random negatives for each anchor
    neg_idx = torch.randint(0, num_sub_nodes, (num_pos, neg_ratio), device=device)
    negatives = z[neg_idx]  # [num_pos, neg_ratio, dim]

    # Positive similarity: [num_pos, 1]
    pos_sim = (anchors * positives).sum(dim=1, keepdim=True) / temperature

    # Negative similarities: [num_pos, neg_ratio]
    neg_sim = torch.bmm(negatives, anchors.unsqueeze(2)).squeeze(2) / temperature

    # InfoNCE: -log(exp(pos) / (exp(pos) + sum(exp(neg))))
    # = -pos + log(exp(pos) + sum(exp(neg)))
    # Numerically stable via logsumexp over [pos, neg1, neg2, ...]
    logits = torch.cat([pos_sim, neg_sim], dim=1)  # [num_pos, 1 + neg_ratio]
    labels = torch.zeros(num_pos, dtype=torch.long, device=device)  # positive is index 0
    return F.cross_entropy(logits, labels)


def train_hgt(
    data: object,  # HeteroData
    num_nodes: int,
    edge_type_names: list[str],
    feat_dim: int,
    dim: int = 128,
    hidden_dim: int = 256,
    heads: int = 4,
    layers: int = 2,
    epochs: int = 50,
    lr: float = 0.001,
    neg_ratio: int = 5,
    batch_size: int = 1024,
    num_neighbors: list[int] | None = None,
    loss_log_path: Path | None = None,
    suffix: str = "",
    game: str = "magic",
    loss_mode: str = "link_prediction",
    temperature: float = 0.07,
) -> tuple[np.ndarray, list[dict]]:
    """Train HGT with NeighborLoader mini-batching.

    loss_mode:
        'link_prediction' -- BPR margin loss on edge existence (default).
        'contrastive' -- InfoNCE/NT-Xent on L2-normalized embeddings.
    """
    from torch_geometric.loader import NeighborLoader

    if num_neighbors is None:
        num_neighbors = [10, 10]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Device: {device}")
    print(
        f"  Loss: {loss_mode}"
        + (f" (temperature={temperature})" if loss_mode == "contrastive" else "")
    )
    print(f"  Mini-batch: batch_size={batch_size}, num_neighbors={num_neighbors}")

    model = HGTEncoder(
        in_dim=feat_dim,
        hidden_dim=hidden_dim,
        out_dim=dim,
        num_heads=heads,
        num_layers=layers,
        edge_types=edge_type_names,
    ).to(device)

    param_count = sum(p.numel() for p in model.parameters())
    print(f"  Model parameters: {param_count:,}")

    # NeighborLoader for mini-batch training over all card nodes
    train_loader = NeighborLoader(
        data,
        num_neighbors=num_neighbors,
        batch_size=batch_size,
        input_nodes="card",
        shuffle=True,
    )
    print(f"  NeighborLoader: {len(train_loader)} batches/epoch")

    # Merge all edges (on CPU) for validation split
    all_src, all_dst = [], []
    for etype in edge_type_names:
        ei = data["card", etype, "card"].edge_index
        all_src.append(ei[0])
        all_dst.append(ei[1])
    all_edges = torch.stack([torch.cat(all_src), torch.cat(all_dst)])
    num_total_edges = all_edges.size(1)

    # Hold out 5% of edges for validation (evaluated on full graph periodically)
    perm = torch.randperm(num_total_edges)
    val_size = max(num_total_edges // 20, 1000)
    val_edges = all_edges[:, perm[:val_size]]
    val_neg = sample_negative_edges(all_edges, num_nodes, val_size)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    # Checkpoint setup
    ckpt_dir = DATA_DIR / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    suffix_tag = f"_{suffix}" if suffix else ""
    ckpt_path = ckpt_dir / f"hgt_{game}_{num_nodes}n_{dim}d{suffix_tag}.pt"

    # Loss log
    loss_history: list[dict] = []
    loss_csv = None
    loss_writer = None
    if loss_log_path:
        loss_log_path.parent.mkdir(parents=True, exist_ok=True)
        loss_csv = open(loss_log_path, "w", newline="")
        loss_writer = csv.DictWriter(
            loss_csv, fieldnames=["epoch", "train_loss", "val_auc", "wall_s"]
        )
        loss_writer.writeheader()

    train_start = time.monotonic()

    # Resume from checkpoint
    start_epoch = 0
    if ckpt_path.exists():
        try:
            ckpt = torch.load(str(ckpt_path), weights_only=False, map_location=device)
            model.load_state_dict(ckpt["model"])
            optimizer.load_state_dict(ckpt["optimizer"])
            start_epoch = ckpt["epoch"] + 1
            prev_loss = ckpt["loss"]
            print(f"    Resumed from checkpoint: epoch {start_epoch} (loss {prev_loss:.4f})")
        except Exception as e:
            print(f"    Checkpoint load failed ({e}), starting fresh")

    if start_epoch >= epochs:
        print(f"    Already trained to epoch {start_epoch}, skipping (requested {epochs})")

    for epoch in range(start_epoch, epochs):
        model.train()

        total_loss = 0.0
        n_batches = 0

        for batch in train_loader:
            batch = batch.to(device)

            optimizer.zero_grad()

            # Forward on the subgraph
            out = model(batch.x_dict, batch.edge_index_dict)
            z = out["card"]  # embeddings for all nodes in this subgraph

            # Collect edges from the subgraph for link prediction
            # These are already re-indexed to [0, batch.num_nodes)
            sub_src, sub_dst = [], []
            for etype in edge_type_names:
                key = ("card", etype, "card")
                if key in batch.edge_index_dict:
                    ei = batch.edge_index_dict[key]
                    sub_src.append(ei[0])
                    sub_dst.append(ei[1])

            if not sub_src:
                continue

            pos_edges = torch.stack([torch.cat(sub_src), torch.cat(sub_dst)])
            num_sub_nodes = z.size(0)

            # Subsample positive edges if there are too many (cap at 2x batch_size)
            num_pos_batch = pos_edges.size(1)
            max_pos = batch_size * 2
            if num_pos_batch > max_pos:
                sel = torch.randperm(num_pos_batch, device=device)[:max_pos]
                pos_edges = pos_edges[:, sel]
                num_pos_batch = max_pos

            if loss_mode == "contrastive":
                # L2-normalize for cosine similarity in InfoNCE
                z_norm = F.normalize(z, p=2, dim=1)
                loss = compute_contrastive_loss(
                    z_norm, pos_edges, num_sub_nodes, neg_ratio, temperature
                )
            else:
                # Link prediction: BPR-style margin loss
                neg_src = torch.randint(
                    0, num_sub_nodes, (num_pos_batch * neg_ratio,), device=device
                )
                neg_dst = torch.randint(
                    0, num_sub_nodes, (num_pos_batch * neg_ratio,), device=device
                )

                pos_score = (z[pos_edges[0]] * z[pos_edges[1]]).sum(dim=1)
                neg_score = (z[neg_src] * z[neg_dst]).sum(dim=1)

                pos_expanded = pos_score.unsqueeze(1).expand(-1, neg_ratio)
                neg_reshaped = neg_score.view(num_pos_batch, neg_ratio)
                loss = -F.logsigmoid(pos_expanded - neg_reshaped).mean()

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1

        scheduler.step()
        avg_loss = total_loss / max(n_batches, 1)
        wall_s = time.monotonic() - train_start

        # Validation AUC (every 5 epochs) -- chunked full-graph inference
        val_auc = float("nan")
        if (epoch + 1) % 5 == 0 or epoch == epochs - 1:
            model.eval()
            with torch.no_grad():
                z = _infer_all_embeddings(model, data, num_nodes, num_neighbors, device)
                vp = (z[val_edges[0]] * z[val_edges[1]]).sum(dim=1)
                vn = (z[val_neg[0]] * z[val_neg[1]]).sum(dim=1)
                scores = torch.cat([vp, vn])
                labels = torch.cat(
                    [
                        torch.ones(vp.size(0)),
                        torch.zeros(vn.size(0)),
                    ]
                ).to(device)
                sorted_idx = scores.argsort(descending=True)
                sorted_labels = labels[sorted_idx]
                n_pos = sorted_labels.sum().item()
                n_neg = len(sorted_labels) - n_pos
                if n_pos > 0 and n_neg > 0:
                    pos_mask = sorted_labels == 1
                    rank_sum = (
                        torch.arange(1, len(sorted_labels) + 1, device=device).float()[pos_mask]
                    ).sum()
                    val_auc = 1.0 - (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
                    val_auc = val_auc.item()

        print(
            f"    Epoch {epoch + 1}/{epochs}: loss={avg_loss:.4f}"
            f"  val_auc={val_auc:.4f}  ({wall_s:.0f}s)"
        )

        row = {
            "epoch": epoch + 1,
            "train_loss": round(avg_loss, 6),
            "val_auc": round(val_auc, 6) if not np.isnan(val_auc) else "",
            "wall_s": round(wall_s, 1),
        }
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
            "loss": avg_loss if "avg_loss" in dir() else float("nan"),
        },
        str(ckpt_path),
    )

    if loss_csv:
        loss_csv.close()

    # Extract all embeddings via chunked inference
    model.eval()
    with torch.no_grad():
        z = _infer_all_embeddings(model, data, num_nodes, num_neighbors, device)
        embeddings = z.cpu().numpy()

    return embeddings, loss_history


def _infer_all_embeddings(
    model: nn.Module,
    data: object,  # HeteroData
    num_nodes: int,
    num_neighbors: list[int],
    device: torch.device,
    infer_batch_size: int = 2048,
) -> torch.Tensor:
    """Produce embeddings for ALL nodes via chunked NeighborLoader inference.

    Uses larger neighbor counts than training (2x) and processes all nodes
    in batches to avoid OOM during inference.
    """
    from torch_geometric.loader import NeighborLoader

    # Use more neighbors at inference for better quality
    infer_neighbors = [n * 2 for n in num_neighbors]

    loader = NeighborLoader(
        data,
        num_neighbors=infer_neighbors,
        batch_size=infer_batch_size,
        input_nodes="card",
        shuffle=False,
    )

    all_embeddings = torch.zeros(num_nodes, model.output_proj.out_features, device=device)
    model.eval()

    for batch in loader:
        batch = batch.to(device)
        out = model(batch.x_dict, batch.edge_index_dict)
        z = out["card"]

        # batch['card'].n_id maps subgraph indices -> original graph indices
        # batch['card'].batch_size is the number of seed nodes (first N)
        n_id = batch["card"].n_id
        bs = batch["card"].batch_size
        # Only write the seed node embeddings (first batch_size entries)
        all_embeddings[n_id[:bs]] = z[:bs]

    return all_embeddings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Train HGT embeddings")
    parser.add_argument("--game", default="magic")
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--hidden-dim", type=int, default=256)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--heads", type=int, default=4)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument(
        "--neg-ratio", type=int, default=5, help="Negative samples per positive edge"
    )
    parser.add_argument(
        "--batch-size", type=int, default=1024, help="NeighborLoader seed node batch size"
    )
    parser.add_argument(
        "--num-neighbors",
        type=str,
        default="10,10",
        help="Neighbors per hop, comma-separated (e.g. '10,10' for 2-hop)",
    )
    parser.add_argument(
        "--output-suffix",
        type=str,
        default="",
        help="Suffix for output filename (for parallel runs)",
    )
    parser.add_argument(
        "--loss",
        type=str,
        default="link_prediction",
        choices=["link_prediction", "contrastive"],
        help="Loss function: link_prediction (BPR margin, default) or "
        "contrastive (InfoNCE/NT-Xent, better for similarity tasks)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.07,
        help="Temperature for contrastive loss (default: 0.07, ignored for link_prediction)",
    )
    parser.add_argument(
        "--edge-types",
        type=str,
        default="",
        help="Comma-separated edge types to use (default: all available). "
        "E.g. --edge-types deck,enriched,keyword",
    )
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"HGT Training [{args.game}]")
    print(f"{'=' * 60}")

    # Load edges
    print(f"\n[1/5] Loading typed edges...")
    edge_types = load_typed_edges(args.game)

    # Filter to requested edge types
    if args.edge_types:
        requested = [e.strip() for e in args.edge_types.split(",")]
        missing = [e for e in requested if e not in edge_types]
        if missing:
            print(f"  WARNING: requested edge types not found: {missing}")
        edge_types = {k: v for k, v in edge_types.items() if k in requested}
        print(f"  Filtered to: {list(edge_types.keys())}")

    if not edge_types:
        print("No edge types found. Check data/graphs/ directory.")
        return 1

    # Build heterogeneous graph (without features first to get card_list)
    print(f"\n[2/5] Building heterogeneous graph...")
    data, card_list, card_to_idx = build_hetero_data(edge_types)
    num_nodes = len(card_list)

    # Load node features and attach to HeteroData
    print(f"\n[3/5] Loading node features from card annotations...")
    node_features, feat_dim = load_node_features(args.game, card_list, card_to_idx, args.dim)
    data["card"].x = node_features

    # Parse num_neighbors
    num_neighbors = [int(x.strip()) for x in args.num_neighbors.split(",")]

    # Prepare log paths
    suffix = f"_{args.output_suffix}" if args.output_suffix else ""
    logs_dir = DATA_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    loss_log_path = logs_dir / f"{args.game}_hgt{suffix}_loss.csv"

    # Train
    edge_type_names = list(edge_types.keys())
    loss_tag = args.loss
    if args.loss == "contrastive":
        loss_tag = f"contrastive(tau={args.temperature})"
    print(
        f"\n[4/5] Training HGT (dim={args.dim}, hidden={args.hidden_dim}, "
        f"heads={args.heads}, layers={args.layers}, epochs={args.epochs}, "
        f"batch_size={args.batch_size}, neighbors={num_neighbors}, "
        f"loss={loss_tag})..."
    )
    print(f"  Edge types: {edge_type_names}")
    t0 = time.monotonic()

    embeddings, loss_history = train_hgt(
        data,
        num_nodes=num_nodes,
        edge_type_names=edge_type_names,
        feat_dim=feat_dim,
        dim=args.dim,
        hidden_dim=args.hidden_dim,
        heads=args.heads,
        layers=args.layers,
        epochs=args.epochs,
        lr=args.lr,
        neg_ratio=args.neg_ratio,
        batch_size=args.batch_size,
        num_neighbors=num_neighbors,
        loss_log_path=loss_log_path,
        suffix=args.output_suffix,
        game=args.game,
        loss_mode=args.loss,
        temperature=args.temperature,
    )

    elapsed = time.monotonic() - t0
    print(f"\n  Training complete in {elapsed:.1f}s")
    print(f"  Loss log: {loss_log_path}")

    # L2 normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    embeddings = (embeddings / norms).astype(np.float32)

    # Save as KeyedVectors
    print(f"\n[5/5] Saving embeddings...")
    kv = KeyedVectors(vector_size=args.dim)
    kv.add_vectors(card_list, embeddings)

    out_path = DATA_DIR / "embeddings" / f"{args.game}_hgt{suffix}.wv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
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

    # Auto-eval: run eval_per_mode
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
                    f"{args.game}_hgt{suffix}",
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
                        else raw.get("novelty"),
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

    # Downstream task evals
    downstream = {}
    print(f"\n  Downstream evals...")

    test_set_path = DATA_DIR / "test_sets" / f"annotated_{args.game}_v2.json"
    if test_set_path.exists():
        try:
            with open(test_set_path) as f:
                test_data = json.load(f)
            test_queries = test_data.get("queries", {})

            # Contextual recall
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

            # Deck completion proxy
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
                try:
                    seed_vec = sum(kv[c] for c in seed) / len(seed)
                    n = np.linalg.norm(seed_vec)
                    if n > 0:
                        seed_vec /= n
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
        "model": "hgt",
        "git_sha": git_sha,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "params": {
            "dim": args.dim,
            "hidden_dim": args.hidden_dim,
            "epochs": args.epochs,
            "heads": args.heads,
            "layers": args.layers,
            "lr": args.lr,
            "neg_ratio": args.neg_ratio,
            "batch_size": args.batch_size,
            "num_neighbors": num_neighbors,
            "loss": args.loss,
            "temperature": args.temperature if args.loss == "contrastive" else None,
            "edge_types_filter": args.edge_types if args.edge_types else "all",
        },
        "data": {
            "edge_types": {k: len(v) for k, v in edge_types.items()},
            "num_cards": num_nodes,
            "node_feature_dim": feat_dim,
        },
        "training": {
            "duration_s": round(elapsed, 1),
            "final_loss": loss_history[-1]["train_loss"] if loss_history else None,
            "loss_log": str(loss_log_path),
        },
        "quality_pairs": quality_pairs,
        "eval": eval_results.get(args.game) if eval_results and args.game in eval_results else None,
        "downstream": downstream if downstream else None,
        "artifacts": {
            "embeddings": str(out_path),
            "checkpoint": str(
                DATA_DIR / "checkpoints" / f"hgt_{args.game}_{num_nodes}n_{args.dim}d.pt"
            ),
            "loss_log": str(loss_log_path),
        },
    }

    summary_path = logs_dir / f"{args.game}_hgt{suffix}_run.json"
    with open(summary_path, "w") as f:
        json.dump(run_summary, f, indent=2)
    print(f"\n  Run summary: {summary_path}")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
