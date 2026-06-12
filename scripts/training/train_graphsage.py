#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "torch>=2.0",
#   "torch-geometric>=2.5",
#   "gensim>=4.3.0",
#   "numpy<2.0.0",
# ]
# ///
"""
Train GraphSAGE embeddings via link prediction on co-occurrence graphs.

Supports optional node features from card_attributes CSV (Magic).
Falls back to learned embeddings when no features are provided.

Outputs gensim KeyedVectors (.wv) compatible with compare_all.py.

Usage:
  # Basic (learned embeddings only):
  PYTHONPATH=src .venv/bin/python scripts/training/train_graphsage.py \
    --edgelist data/graphs/pokemon_blended.edg \
    --output data/embeddings/pokemon_graphsage_v2.wv

  # With enriched edges (higher weight):
  PYTHONPATH=src .venv/bin/python scripts/training/train_graphsage.py \
    --edgelist data/graphs/pokemon_blended.edg \
    --enriched data/graphs/pairs_enriched_pokemon_v3b.edg \
    --enriched-weight 3.0 \
    --output data/embeddings/pokemon_graphsage_enriched.wv

  # With card attribute features (Magic only):
  PYTHONPATH=src .venv/bin/python scripts/training/train_graphsage.py \
    --edgelist data/graphs/magic_blended.edg \
    --card-attrs data/processed/card_attributes_enriched.csv \
    --output data/embeddings/magic_graphsage_feat.wv

  # All 3 games quick run:
  for game in pokemon yugioh magic; do
    PYTHONPATH=src .venv/bin/python scripts/training/train_graphsage.py \
      --edgelist data/graphs/${game}_blended.edg \
      --output data/embeddings/${game}_graphsage_v2.wv
  done
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from gensim.models import KeyedVectors
from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ml.utils.data_loading import load_edgelist


def merge_edgelists(
    base_edges: list[tuple[str, str, float]],
    enriched_edges: list[tuple[str, str, float]] | None,
    enriched_weight: float = 3.0,
) -> list[tuple[str, str, float]]:
    """Merge base and enriched edgelists with weighted addition."""
    merged: dict[tuple[str, str], float] = {}
    for c1, c2, w in base_edges:
        key = (min(c1, c2), max(c1, c2))
        merged[key] = merged.get(key, 0.0) + w
    if enriched_edges:
        for c1, c2, w in enriched_edges:
            key = (min(c1, c2), max(c1, c2))
            merged[key] = merged.get(key, 0.0) + w * enriched_weight
    return [(c1, c2, w) for (c1, c2), w in merged.items()]


def build_index(edges: list[tuple[str, str, float]]) -> tuple[dict[str, int], list[str]]:
    """Build node-to-index mapping. Returns (node_to_idx, idx_to_node_list)."""
    node_to_idx: dict[str, int] = {}
    for c1, c2, _ in edges:
        if c1 not in node_to_idx:
            node_to_idx[c1] = len(node_to_idx)
        if c2 not in node_to_idx:
            node_to_idx[c2] = len(node_to_idx)
    idx_to_node = [""] * len(node_to_idx)
    for name, idx in node_to_idx.items():
        idx_to_node[idx] = name
    return node_to_idx, idx_to_node


# ---------------------------------------------------------------------------
# Card attribute features (optional)
# ---------------------------------------------------------------------------


def load_card_features(
    csv_path: Path,
    node_to_idx: dict[str, int],
) -> torch.Tensor | None:
    """Load card attributes and encode as feature vectors.

    Features encoded:
    - type: multi-hot over common types (Creature, Enchantment, etc.)
    - colors: multi-hot over WUBRG + colorless
    - cmc: scalar (log-scaled)
    - rarity: one-hot (common, uncommon, rare, mythic)
    - power/toughness: scalars (normalized)
    - keywords: multi-hot over top-K keywords
    """
    # First pass: collect all keywords
    keyword_counts: dict[str, int] = defaultdict(int)
    rows: dict[str, dict] = {}

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip().strip('"')
            if name not in node_to_idx:
                continue
            rows[name] = row
            kw_str = row.get("keywords", "")
            if kw_str:
                for kw in kw_str.split(","):
                    kw = kw.strip()
                    if kw:
                        keyword_counts[kw] += 1

    if not rows:
        return None

    # Top 50 keywords
    top_keywords = sorted(keyword_counts, key=keyword_counts.get, reverse=True)[:50]
    kw_to_idx = {kw: i for i, kw in enumerate(top_keywords)}

    # Auto-detect type categories from data
    type_counts: dict[str, int] = defaultdict(int)
    all_colors: set[str] = set()
    rarity_counts: dict[str, int] = defaultdict(int)
    for row in rows.values():
        type_str = row.get("type", "")
        for word in type_str.split():
            w = word.strip().rstrip(",")
            if len(w) > 1:
                type_counts[w] += 1
        color_str = row.get("colors", "")
        if color_str:
            for c in color_str.split(","):
                c = c.strip()
                if c:
                    all_colors.add(c)
        rarity = row.get("rarity", "").strip().lower()
        if rarity:
            rarity_counts[rarity] += 1

    # Top 15 type words, top 15 color values, top 6 rarities
    type_cats = sorted(type_counts, key=type_counts.get, reverse=True)[:15]
    type_to_idx = {t: i for i, t in enumerate(type_cats)}
    colors_list = sorted(all_colors)[:15]  # cap at 15
    rarity_list = sorted(rarity_counts, key=rarity_counts.get, reverse=True)[:6]
    rarity_to_idx = {r: i for i, r in enumerate(rarity_list)}

    num_nodes = len(node_to_idx)
    feat_dim = len(type_cats) + len(colors_list) + 1 + 1 + len(rarity_list) + 2 + len(top_keywords)

    features = torch.zeros(num_nodes, feat_dim)
    matched = 0

    for name, row in rows.items():
        idx = node_to_idx[name]
        matched += 1
        offset = 0

        # Type multi-hot
        type_str = row.get("type", "")
        for t, ti in type_to_idx.items():
            if t.lower() in type_str.lower():
                features[idx, offset + ti] = 1.0
        offset += len(type_cats)

        # Colors multi-hot (game-agnostic)
        color_str = row.get("colors", "")
        has_color = False
        if color_str:
            for c in color_str.split(","):
                c = c.strip()
                if c in colors_list:
                    ci = colors_list.index(c)
                    features[idx, offset + ci] = 1.0
                    has_color = True
        offset += len(colors_list)

        # Colorless indicator
        features[idx, offset] = 0.0 if has_color else 1.0
        offset += 1

        # CMC / level / cost (log-scaled)
        try:
            cmc = float(row.get("cmc", 0))
            features[idx, offset] = np.log1p(cmc)
        except (ValueError, TypeError):
            pass
        offset += 1

        # Rarity one-hot
        rarity = row.get("rarity", "").strip().lower()
        if rarity in rarity_to_idx:
            features[idx, offset + rarity_to_idx[rarity]] = 1.0
        offset += len(rarity_list)

        # Power/toughness or ATK/DEF or damage/HP (normalized)
        max_stat = 15.0  # works for MTG; YGO ATK/DEF uses /5000 below
        for pi, field in enumerate(["power", "toughness"]):
            try:
                val = float(row.get(field, ""))
                # Auto-scale: if values are >100, assume YGO/Pokemon scale
                if val > 100:
                    val = val / 5000.0
                else:
                    val = val / max_stat
                features[idx, offset + pi] = min(val, 1.0)
            except (ValueError, TypeError):
                pass
        offset += 2

        # Keywords multi-hot
        kw_str = row.get("keywords", "")
        if kw_str:
            for kw in kw_str.split(","):
                kw = kw.strip()
                if kw in kw_to_idx:
                    features[idx, offset + kw_to_idx[kw]] = 1.0

    coverage = matched / num_nodes * 100
    print(f"  Card features: {matched}/{num_nodes} nodes matched ({coverage:.1f}%), dim={feat_dim}")
    print(
        f"    types={len(type_cats)}, colors={len(colors_list)}, rarities={len(rarity_list)}, keywords={len(top_keywords)}"
    )
    return features


# ---------------------------------------------------------------------------
# Loss functions
# ---------------------------------------------------------------------------


def uniformity_loss(embeddings: torch.Tensor, t: float = 2.0) -> torch.Tensor:
    """Wang & Isola uniformity loss on the unit hypersphere (DirectAU).

    Pushes embeddings to spread uniformly, preventing collapse.
    Uses manual pairwise distance (torch.pdist not available on MPS).
    """
    embeddings = F.normalize(embeddings, dim=-1)
    # Manual pairwise squared distances: ||a - b||^2 = 2 - 2*a.b (for unit vectors)
    sim = embeddings @ embeddings.T  # (N, N)
    sq_dist = 2.0 - 2.0 * sim
    # Extract upper triangle (exclude diagonal)
    mask = torch.triu(
        torch.ones(sq_dist.size(0), sq_dist.size(0), device=sq_dist.device, dtype=torch.bool),
        diagonal=1,
    )
    sq_pdist = sq_dist[mask]
    return sq_pdist.mul(-t).exp().mean().log()


# ---------------------------------------------------------------------------
# GraphSAGE model
# ---------------------------------------------------------------------------


class GraphSAGENet(nn.Module):
    """Multi-layer GraphSAGE with optional input features.

    Supports both full-batch (all nodes) and mini-batch (subset of nodes)
    via the optional `node_ids` parameter to `forward()`.
    """

    def __init__(
        self,
        num_nodes: int,
        emb_dim: int = 128,
        input_features: torch.Tensor | None = None,
        num_layers: int = 3,
    ):
        super().__init__()
        self.num_layers = num_layers

        if input_features is not None:
            feat_dim = input_features.shape[1]
            self.register_buffer("input_features", input_features)
            self.feature_proj = nn.Linear(feat_dim, emb_dim)
            self.use_features = True
        else:
            self.embedding = nn.Embedding(num_nodes, emb_dim)
            nn.init.xavier_uniform_(self.embedding.weight)
            self.use_features = False

        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        for _ in range(num_layers):
            self.convs.append(SAGEConv(emb_dim, emb_dim))
            self.norms.append(nn.LayerNorm(emb_dim))

    def forward(
        self,
        edge_index: torch.Tensor,
        node_ids: list[int] | None = None,
    ) -> torch.Tensor:
        """Forward pass.

        Args:
            edge_index: [2, E] tensor with LOCAL indices (0..N_sub-1).
            node_ids: if provided, GLOBAL node IDs for each local index.
                      Used to index into the Embedding/feature table.
                      If None, assumes local == global (full-batch mode).
        """
        if self.use_features:
            if node_ids is not None:
                idx = torch.tensor(node_ids, dtype=torch.long, device=self.input_features.device)
                x = self.feature_proj(self.input_features[idx])
            else:
                x = self.feature_proj(self.input_features)
        else:
            if node_ids is not None:
                idx = torch.tensor(node_ids, dtype=torch.long, device=self.embedding.weight.device)
                x = self.embedding(idx)
            else:
                x = self.embedding.weight

        for i, (conv, norm) in enumerate(zip(self.convs, self.norms)):
            x_new = conv(x, edge_index)
            x_new = norm(x_new)
            if i < self.num_layers - 1:
                x_new = F.relu(x_new)
                x_new = F.dropout(x_new, p=0.2, training=self.training)
            x = x + x_new
        return x


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def build_pyg_data(
    edges: list[tuple[str, str, float]],
    node_to_idx: dict[str, int],
    features: torch.Tensor | None = None,
) -> tuple[Data, torch.Tensor]:
    """Build PyG Data object from edges."""
    num_nodes = len(node_to_idx)
    src, dst, weights = [], [], []
    for c1, c2, w in edges:
        i, j = node_to_idx[c1], node_to_idx[c2]
        src.extend([i, j])
        dst.extend([j, i])
        weights.extend([w, w])

    edge_index = torch.tensor([src, dst], dtype=torch.long)
    edge_weight = torch.tensor(weights, dtype=torch.float)
    if edge_weight.max() > 0:
        edge_weight = edge_weight / edge_weight.max()

    # Node features: use provided or create placeholder
    if features is not None:
        x = features
    else:
        x = torch.zeros(num_nodes, 1)  # placeholder, model uses Embedding

    data = Data(x=x, edge_index=edge_index, num_nodes=num_nodes)
    data.n_id = torch.arange(num_nodes)  # for NeighborLoader tracking
    return data, edge_weight


def train_graphsage(
    edges: list[tuple[str, str, float]],
    node_to_idx: dict[str, int],
    idx_to_node: list[str],
    features: torch.Tensor | None = None,
    dim: int = 128,
    epochs: int = 300,
    lr: float = 0.005,
    neg_ratio: int = 5,
    num_layers: int = 3,
    margin: float = 1.0,
    force_fullbatch: bool = False,
    uniformity_weight: float = 0.1,
    batch_size: int = 4096,
    device: torch.device | None = None,
) -> KeyedVectors:
    """Train GraphSAGE via margin-based link prediction.

    Uses full-batch for small graphs (<500K edges) and mini-batch
    with neighbor sampling for large graphs.
    """
    if device is None:
        device = torch.device("cpu")

    num_nodes = len(node_to_idx)
    num_edges = len(edges)

    # Auto-detect mini-batch mode for large graphs
    mini_batch = num_edges > 500_000 and not force_fullbatch

    data, edge_weight = build_pyg_data(edges, node_to_idx, features)

    model = GraphSAGENet(num_nodes, dim, features, num_layers=num_layers)
    model = model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=epochs, eta_min=lr * 0.01
    )

    mode_str = "mini-batch" if mini_batch else "full-batch"
    print(f"  Training: {num_nodes:,} nodes, {num_edges:,} edges, {epochs} max epochs ({mode_str})")
    print(
        f"  Model: {num_layers}-layer SAGEConv, dim={dim}, features={'yes' if features is not None else 'learned'}"
    )

    if mini_batch:
        return _train_minibatch(
            model,
            data,
            edge_weight,
            optimizer,
            scheduler,
            num_nodes,
            num_edges,
            dim,
            epochs,
            neg_ratio,
            margin,
            batch_size,
            idx_to_node,
            device,
            uniformity_weight=uniformity_weight,
        )
    else:
        return _train_fullbatch(
            model,
            data,
            edge_weight,
            optimizer,
            scheduler,
            num_nodes,
            num_edges,
            dim,
            epochs,
            neg_ratio,
            margin,
            idx_to_node,
            device,
            uniformity_weight=uniformity_weight,
        )


def _train_fullbatch(
    model,
    data,
    edge_weight,
    optimizer,
    scheduler,
    num_nodes,
    num_edges,
    dim,
    epochs,
    neg_ratio,
    margin,
    idx_to_node,
    device,
    uniformity_weight=0.1,
) -> KeyedVectors:
    """Full-batch training for small graphs."""
    edge_index = data.edge_index.to(device)
    edge_weight = edge_weight.to(device)
    best_loss = float("inf")
    patience_counter = 0
    patience = 30

    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        emb = model(edge_index)

        pos_src_idx = edge_index[0]
        pos_dst_idx = edge_index[1]
        pos_scores = (emb[pos_src_idx] * emb[pos_dst_idx]).sum(dim=1)

        num_neg = pos_src_idx.size(0) * neg_ratio
        neg_src = pos_src_idx.repeat(neg_ratio)
        neg_dst = torch.randint(0, num_nodes, (num_neg,), device=device)
        neg_scores = (emb[neg_src] * emb[neg_dst]).sum(dim=1)

        pos_expanded = pos_scores.repeat(neg_ratio)
        loss_margin = F.margin_ranking_loss(
            pos_expanded * edge_weight.repeat(neg_ratio),
            neg_scores,
            torch.ones_like(neg_scores),
            margin=margin,
        )

        # Uniformity loss: prevent embedding collapse (DirectAU)
        # Sample a subset for efficiency (pdist is O(n^2))
        uni_size = min(512, emb.size(0))
        uni_idx = torch.randperm(emb.size(0), device=device)[:uni_size]
        loss_uni = uniformity_loss(emb[uni_idx])
        loss = loss_margin + uniformity_weight * loss_uni

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step()

        if loss.item() < best_loss - 1e-4:
            best_loss = loss.item()
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"    Early stop at epoch {epoch + 1}, loss={loss.item():.4f}")
                break

        if (epoch + 1) % 50 == 0:
            lr_now = scheduler.get_last_lr()[0]
            print(f"    Epoch {epoch + 1}/{epochs}, loss={loss.item():.4f}, lr={lr_now:.6f}")

    return _extract_embeddings(model, edge_index, num_nodes, dim, idx_to_node, device)


def _sample_subgraph(
    adj_list: dict[int, list[int]],
    seed_nodes: list[int],
    num_neighbors: list[int],
) -> tuple[list[int], torch.Tensor]:
    """Sample a k-hop neighborhood around seed nodes.

    Pure Python implementation -- no pyg-lib/torch-sparse needed.
    Samples K neighbors per hop proportionally to degree distribution
    (random uniform from each node's actual neighbors).

    Returns (all_nodes_list, local_edge_index).
    """
    all_nodes = set(seed_nodes)
    frontier = list(seed_nodes)

    for k_neighbors in num_neighbors:
        next_frontier = set()
        for node in frontier:
            neighbors = adj_list.get(node, [])
            if not neighbors:
                continue
            # Sample k_neighbors with replacement if needed
            if len(neighbors) <= k_neighbors:
                sampled = neighbors
            else:
                import random

                sampled = random.sample(neighbors, k_neighbors)
            for n in sampled:
                if n not in all_nodes:
                    next_frontier.add(n)
            all_nodes.update(sampled)
        frontier = list(next_frontier)

    # Build local index mapping
    node_list = list(all_nodes)
    local_idx = {n: i for i, n in enumerate(node_list)}

    # Build local edge_index from adjacency within sampled nodes
    src, dst = [], []
    for node in node_list:
        li = local_idx[node]
        for neighbor in adj_list.get(node, []):
            if neighbor in local_idx:
                src.append(li)
                dst.append(local_idx[neighbor])

    edge_index = (
        torch.tensor([src, dst], dtype=torch.long) if src else torch.zeros(2, 0, dtype=torch.long)
    )
    return node_list, edge_index


def _train_minibatch(
    model,
    data,
    edge_weight,
    optimizer,
    scheduler,
    num_nodes,
    num_edges,
    dim,
    epochs,
    neg_ratio,
    margin,
    batch_size,
    idx_to_node,
    device,
    uniformity_weight=0.1,
) -> KeyedVectors:
    """Mini-batch training with manual neighbor sampling.

    Samples K neighbors per hop (proportional to degree distribution),
    trains on subgraphs. No pyg-lib/torch-sparse dependency.
    """
    import random as rng

    # Build adjacency list (stays on CPU -- sampling is pure Python)
    edge_index = data.edge_index
    adj_list: dict[int, list[int]] = defaultdict(list)
    for i in range(edge_index.shape[1]):
        s, d = int(edge_index[0, i]), int(edge_index[1, i])
        adj_list[s].append(d)

    num_layers = model.num_layers
    # Scale neighbor sampling with graph density
    avg_degree = num_edges * 2 / max(num_nodes, 1)
    # Sample ~sqrt(avg_degree) neighbors per hop, clamped to [10, 50]
    k = max(10, min(50, int(avg_degree**0.5)))
    num_neighbors_per_hop = [k] * num_layers
    print(f"    Avg degree: {avg_degree:.0f}, sampling {k} neighbors/hop")

    all_node_ids = list(range(num_nodes))
    batches_per_epoch = max(1, num_nodes // batch_size)

    best_loss = float("inf")
    patience_counter = 0
    patience = 15

    print(f"    Neighbor sampling: batch_size={batch_size}, neighbors/hop={num_neighbors_per_hop}")
    print(f"    {batches_per_epoch} batches/epoch, {num_nodes:,} total nodes")

    # Global embedding cache for hard negative sampling (updated periodically)
    global_emb_cache = torch.zeros(num_nodes, dim, device=device)
    cache_stale = True

    model.train()
    for epoch in range(epochs):
        epoch_loss = 0.0
        num_batches = 0
        rng.shuffle(all_node_ids)

        # Refresh global embedding cache every 20 epochs for better negatives
        if cache_stale or (epoch > 0 and epoch % 20 == 0):
            model.eval()
            with torch.no_grad():
                for cs in range(0, num_nodes, batch_size):
                    chunk = list(range(cs, min(cs + batch_size, num_nodes)))
                    chunk_neighbors = [min(n, 15) for n in num_neighbors_per_hop]
                    nlist, lei = _sample_subgraph(adj_list, chunk, chunk_neighbors)
                    if lei.shape[1] > 0:
                        e = model(lei.to(device), node_ids=nlist)
                        loc = {n: i for i, n in enumerate(nlist)}
                        for s in chunk:
                            if s in loc:
                                global_emb_cache[s] = e[loc[s]]
            cache_stale = False
            model.train()

        for batch_start in range(0, num_nodes, batch_size):
            seed_nodes = all_node_ids[batch_start : batch_start + batch_size]
            node_list, local_edge_index = _sample_subgraph(
                adj_list, seed_nodes, num_neighbors_per_hop
            )

            if local_edge_index.shape[1] < 2:
                continue

            local_edge_index = local_edge_index.to(device)
            optimizer.zero_grad()

            # Forward on subgraph (pass global node IDs for embedding lookup)
            emb = model(local_edge_index, node_ids=node_list)

            # Positive pairs from subgraph edges
            pos_src = local_edge_index[0]
            pos_dst = local_edge_index[1]

            # Subsample if too many edges
            max_pos = batch_size * 4
            if pos_src.size(0) > max_pos:
                perm = torch.randperm(pos_src.size(0), device=device)[:max_pos]
                pos_src = pos_src[perm]
                pos_dst = pos_dst[perm]

            pos_scores = (emb[pos_src] * emb[pos_dst]).sum(dim=1)

            # Global negative sampling: sample from ALL nodes, not just subgraph
            n_pos = pos_src.size(0)
            n_neg = n_pos * neg_ratio
            # Get source embeddings from local computation
            neg_src_local = pos_src.repeat(neg_ratio)
            neg_src_emb = emb[neg_src_local]  # [n_neg, dim]
            # Get negative target embeddings from global cache (diverse negatives)
            neg_global_ids = torch.randint(0, num_nodes, (n_neg,), device=device)
            neg_dst_emb = global_emb_cache[neg_global_ids].detach()
            neg_scores = (neg_src_emb * neg_dst_emb).sum(dim=1)

            pos_expanded = pos_scores.repeat(neg_ratio)
            loss_margin = F.margin_ranking_loss(
                pos_expanded,
                neg_scores,
                torch.ones_like(neg_scores),
                margin=margin,
            )

            # Uniformity loss on batch embeddings (prevents collapse)
            uni_size = min(512, emb.size(0))
            uni_idx = torch.randperm(emb.size(0), device=device)[:uni_size]
            loss_uni = uniformity_loss(emb[uni_idx])
            loss = loss_margin + uniformity_weight * loss_uni

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            epoch_loss += loss.item()
            num_batches += 1

        scheduler.step()
        avg_loss = epoch_loss / max(num_batches, 1)

        if avg_loss < best_loss - 1e-4:
            best_loss = avg_loss
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"    Early stop at epoch {epoch + 1}, avg_loss={avg_loss:.4f}")
                break

        if (epoch + 1) % 10 == 0:
            lr_now = scheduler.get_last_lr()[0]
            print(f"    Epoch {epoch + 1}/{epochs}, avg_loss={avg_loss:.4f}, lr={lr_now:.6f}")

    # Extract embeddings: full pass with sampled neighborhoods
    return _extract_embeddings_minibatch(
        model, adj_list, num_nodes, dim, idx_to_node, num_neighbors_per_hop, batch_size, device
    )


def _extract_embeddings(model, edge_index, num_nodes, dim, idx_to_node, device) -> KeyedVectors:
    """Extract and L2-normalize embeddings from trained model (full-batch)."""
    model.eval()
    with torch.no_grad():
        emb = model(edge_index.to(device)).cpu().numpy()
    return _finalize_embeddings(emb, dim, idx_to_node)


def _extract_embeddings_minibatch(
    model,
    adj_list,
    num_nodes,
    dim,
    idx_to_node,
    num_neighbors_per_hop,
    batch_size,
    device,
) -> KeyedVectors:
    """Extract embeddings via manual neighbor sampling inference."""
    model.eval()
    all_emb = torch.zeros(num_nodes, dim)

    with torch.no_grad():
        for batch_start in range(0, num_nodes, batch_size):
            seed_nodes = list(range(batch_start, min(batch_start + batch_size, num_nodes)))
            # Use more neighbors for inference (better approximation)
            inference_neighbors = [min(n * 3, 50) for n in num_neighbors_per_hop]
            node_list, local_edge_index = _sample_subgraph(
                adj_list, seed_nodes, inference_neighbors
            )

            if local_edge_index.shape[1] == 0:
                continue

            emb = model(local_edge_index.to(device), node_ids=node_list).cpu()
            local_idx = {n: i for i, n in enumerate(node_list)}
            for seed in seed_nodes:
                if seed in local_idx:
                    all_emb[seed] = emb[local_idx[seed]]

    return _finalize_embeddings(all_emb.numpy(), dim, idx_to_node)


def _finalize_embeddings(emb: np.ndarray, dim: int, idx_to_node: list[str]) -> KeyedVectors:
    """L2-normalize and package into KeyedVectors."""
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    emb = emb / norms

    kv = KeyedVectors(vector_size=dim)
    kv.add_vectors(idx_to_node, emb)
    return kv


# ---------------------------------------------------------------------------
# Quality metrics
# ---------------------------------------------------------------------------


def compute_quality_metrics(
    kv: KeyedVectors, edges: list[tuple[str, str, float]], n_random: int = 10000
):
    """Compute embedding quality metrics (same as train_blended_embeddings.py)."""
    # Random-pair cosine similarity
    keys = list(kv.key_to_index.keys())
    if len(keys) < 2:
        return
    rng = np.random.default_rng(42)
    n = min(n_random, len(keys) * (len(keys) - 1) // 2)
    random_sims = []
    for _ in range(n):
        i, j = rng.choice(len(keys), size=2, replace=False)
        sim = float(kv.similarity(keys[i], keys[j]))
        random_sims.append(sim)
    random_sims = np.array(random_sims)

    print("\n--- Quality Metrics ---")
    print(f"  Vocabulary size: {len(kv)}")
    print(f"  Random-pair cosine similarity (n={n}):")
    print(f"    mean={random_sims.mean():.4f}  std={random_sims.std():.4f}")
    print(
        f"    min={random_sims.min():.4f}  p25={np.percentile(random_sims, 25):.4f}  "
        f"median={np.median(random_sims):.4f}  p75={np.percentile(random_sims, 75):.4f}  "
        f"max={random_sims.max():.4f}"
    )

    # Top-100 weighted edges similarity
    top_edges = sorted(edges, key=lambda x: x[2], reverse=True)[:100]
    top_sims = []
    for c1, c2, w in top_edges:
        if c1 in kv and c2 in kv:
            top_sims.append(float(kv.similarity(c1, c2)))
    if top_sims:
        top_sims = np.array(top_sims)
        print("  Top-100 weighted edges similarity:")
        print(
            f"    mean={top_sims.mean():.4f}  std={top_sims.std():.4f}  "
            f"min={top_sims.min():.4f}  max={top_sims.max():.4f}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Train GraphSAGE embeddings via link prediction")
    parser.add_argument("--edgelist", type=Path, required=True, help="Base edgelist (.edg)")
    parser.add_argument("--enriched", type=Path, help="Optional enriched edgelist to merge")
    parser.add_argument(
        "--enriched-weight", type=float, default=3.0, help="Weight multiplier for enriched edges"
    )
    parser.add_argument(
        "--card-attrs", type=Path, help="Optional card attributes CSV for node features"
    )
    parser.add_argument("--output", type=Path, required=True, help="Output .wv file")
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--lr", type=float, default=0.005)
    parser.add_argument("--neg-ratio", type=int, default=5, help="Negative samples per positive")
    parser.add_argument("--num-layers", type=int, default=3, help="Number of SAGEConv layers")
    parser.add_argument("--margin", type=float, default=1.0, help="Margin for ranking loss")
    parser.add_argument(
        "--max-edges", type=int, default=0, help="Subsample to top-K weighted edges (0=no limit)"
    )
    parser.add_argument("--device", type=str, default="auto", help="Device: auto, cpu, mps, cuda")
    parser.add_argument(
        "--force-fullbatch", action="store_true", help="Force full-batch mode even for large graphs"
    )
    parser.add_argument(
        "--uniformity-weight",
        type=float,
        default=0.1,
        help="Weight for uniformity loss (0=off, default: 0.1)",
    )
    args = parser.parse_args()

    # Device selection
    if args.device == "auto":
        if torch.cuda.is_available():
            device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            device = torch.device("mps")
        else:
            device = torch.device("cpu")
    else:
        device = torch.device(args.device)

    print("=" * 70)
    print(f"GraphSAGE Embedding Training  [device={device}]")
    print("=" * 70)

    # Load edges
    print("\n[1/4] Loading edgelists...")
    base_edges = load_edgelist(args.edgelist)
    print(f"  Base: {args.edgelist} ({len(base_edges):,} edges)")

    enriched_edges = None
    if args.enriched and args.enriched.exists():
        enriched_edges = load_edgelist(args.enriched)
        print(
            f"  Enriched: {args.enriched} ({len(enriched_edges):,} edges, weight={args.enriched_weight})"
        )

    edges = merge_edgelists(base_edges, enriched_edges, args.enriched_weight)

    # Edge subsampling: keep top-K by weight for large graphs
    if args.max_edges and len(edges) > args.max_edges:
        edges.sort(key=lambda x: x[2], reverse=True)
        edges = edges[: args.max_edges]
        print(f"  Subsampled to top {args.max_edges:,} edges by weight")

    node_to_idx, idx_to_node = build_index(edges)
    print(f"  Merged: {len(node_to_idx):,} nodes, {len(edges):,} edges")

    # Load features
    print("\n[2/4] Loading features...")
    features = None
    if args.card_attrs and args.card_attrs.exists():
        features = load_card_features(args.card_attrs, node_to_idx)
        if features is None:
            print("  No card features matched graph nodes, using learned embeddings")
    else:
        print("  No card attributes provided, using learned embeddings")

    # Train
    print("\n[3/4] Training GraphSAGE...")
    t0 = time.monotonic()
    kv = train_graphsage(
        edges,
        node_to_idx,
        idx_to_node,
        features=features,
        dim=args.dim,
        epochs=args.epochs,
        lr=args.lr,
        neg_ratio=args.neg_ratio,
        num_layers=args.num_layers,
        margin=args.margin,
        force_fullbatch=args.force_fullbatch,
        uniformity_weight=args.uniformity_weight,
        device=device,
    )
    elapsed = time.monotonic() - t0
    print(f"\n  Training complete in {elapsed:.1f}s")

    # Save
    args.output.parent.mkdir(parents=True, exist_ok=True)
    kv.save(str(args.output))
    print(f"  Saved embeddings to {args.output}")

    # Quality metrics
    print("\n[4/4] Computing quality metrics...")
    compute_quality_metrics(kv, edges)

    print(f"\n{'=' * 70}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
