#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["gensim", "pecanpy", "torch", "torch-geometric", "numpy"]
# ///
"""
Compare PecanPy node2vec+ vs PyG GraphSAGE embeddings.

Trains both methods on the same edgelist, evaluates against the test set,
and reports side-by-side metrics (nDCG@10, P@10, MRR@10).

Usage:
  uv run scripts/experiments/compare_pecanpy_vs_gnn.py \
    --edgelist data/graphs/pairs_large.edg \
    --test-set data/test_set_minimal.json \
    --output-dir data/embeddings

  # Quick run on Pokemon (small graph):
  uv run scripts/experiments/compare_pecanpy_vs_gnn.py \
    --edgelist data/graphs/pokemon.edg \
    --test-set data/test_set_minimal.json \
    --output-dir data/embeddings --prefix pokemon
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from gensim.models import KeyedVectors, Word2Vec
from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv


# ---------------------------------------------------------------------------
# Edgelist I/O (tab-separated: card1 \t card2 \t weight)
# ---------------------------------------------------------------------------

def load_edgelist(path: Path) -> list[tuple[str, str, float]]:
    """Load tab-separated edgelist. Handles card names with spaces."""
    edges = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            card1, card2 = parts[0], parts[1]
            weight = float(parts[2]) if len(parts) > 2 else 1.0
            edges.append((card1, card2, weight))
    return edges


def build_index(edges: list[tuple[str, str, float]]) -> tuple[dict[str, int], dict[int, str]]:
    """Build node-to-index mapping from edges."""
    node_to_idx: dict[str, int] = {}
    for c1, c2, _ in edges:
        if c1 not in node_to_idx:
            node_to_idx[c1] = len(node_to_idx)
        if c2 not in node_to_idx:
            node_to_idx[c2] = len(node_to_idx)
    idx_to_node = {v: k for k, v in node_to_idx.items()}
    return node_to_idx, idx_to_node


# ---------------------------------------------------------------------------
# Method 1: PecanPy node2vec+
# ---------------------------------------------------------------------------

def train_pecanpy(
    edgelist_path: Path,
    dim: int = 128,
    walk_length: int = 80,
    num_walks: int = 10,
    window: int = 10,
    p: float = 1.0,
    q: float = 1.0,
    workers: int = 4,
    epochs: int = 5,
) -> KeyedVectors:
    """Train PecanPy node2vec+ and return mean-centered KeyedVectors."""
    from pecanpy.pecanpy import SparseOTF

    g = SparseOTF(p=p, q=q, workers=workers, verbose=False, extend=True)
    g.read_edg(str(edgelist_path), weighted=True, directed=False)

    walks = g.simulate_walks(num_walks=num_walks, walk_length=walk_length)

    model = Word2Vec(
        walks,
        vector_size=dim,
        window=window,
        min_count=0,
        sg=1,
        workers=workers,
        epochs=epochs,
        negative=20,
    )

    # Mean-center to prevent positive-bias collapse
    model.wv.vectors -= model.wv.vectors.mean(axis=0)
    return model.wv


# ---------------------------------------------------------------------------
# Method 2: PyG GraphSAGE (link prediction)
# ---------------------------------------------------------------------------

class GraphSAGENet(nn.Module):
    """2-layer GraphSAGE with learned embeddings (not one-hot)."""

    def __init__(self, num_nodes: int, hidden_dim: int = 128):
        super().__init__()
        self.embedding = nn.Embedding(num_nodes, hidden_dim)
        nn.init.xavier_uniform_(self.embedding.weight)
        self.conv1 = SAGEConv(hidden_dim, hidden_dim)
        self.conv2 = SAGEConv(hidden_dim, hidden_dim)

    def forward(self, edge_index: torch.Tensor) -> torch.Tensor:
        x = self.embedding.weight
        x = F.relu(self.conv1(x, edge_index))
        x = F.dropout(x, p=0.3, training=self.training)
        x = self.conv2(x, edge_index)
        return x


def train_graphsage(
    edges: list[tuple[str, str, float]],
    node_to_idx: dict[str, int],
    idx_to_node: dict[int, str],
    dim: int = 128,
    epochs: int = 200,
    lr: float = 0.01,
) -> KeyedVectors:
    """Train GraphSAGE via link prediction and return KeyedVectors."""
    num_nodes = len(node_to_idx)

    # Build edge_index (undirected: add both directions)
    src, dst, weights = [], [], []
    for c1, c2, w in edges:
        i, j = node_to_idx[c1], node_to_idx[c2]
        src.extend([i, j])
        dst.extend([j, i])
        weights.extend([w, w])

    edge_index = torch.tensor([src, dst], dtype=torch.long)
    edge_weight = torch.tensor(weights, dtype=torch.float)

    model = GraphSAGENet(num_nodes, dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)

    best_loss = float("inf")
    patience_counter = 0
    patience = 20

    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        emb = model(edge_index)

        # Positive edges
        pos_src, pos_dst = edge_index[0], edge_index[1]
        pos_scores = (emb[pos_src] * emb[pos_dst]).sum(dim=1)

        # Negative edges (random)
        num_neg = pos_src.size(0)
        neg_src = torch.randint(0, num_nodes, (num_neg,))
        neg_dst = torch.randint(0, num_nodes, (num_neg,))
        neg_scores = (emb[neg_src] * emb[neg_dst]).sum(dim=1)

        # BCE loss
        pos_loss = -torch.log(torch.sigmoid(pos_scores) + 1e-15).mean()
        neg_loss = -torch.log(1 - torch.sigmoid(neg_scores) + 1e-15).mean()
        loss = pos_loss + neg_loss

        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        if loss.item() < best_loss - 1e-4:
            best_loss = loss.item()
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"    Early stop at epoch {epoch + 1}, loss={loss.item():.4f}")
                break

        if (epoch + 1) % 50 == 0:
            print(f"    Epoch {epoch + 1}/{epochs}, loss={loss.item():.4f}")

    # Extract embeddings into KeyedVectors
    model.eval()
    with torch.no_grad():
        emb = model(edge_index).cpu().numpy()

    # Mean-center for fair comparison
    emb -= emb.mean(axis=0)

    kv = KeyedVectors(vector_size=dim)
    keys = [idx_to_node[i] for i in range(num_nodes)]
    kv.add_vectors(keys, emb)
    return kv


# ---------------------------------------------------------------------------
# Evaluation (nDCG@k, P@k, MRR@k)
# ---------------------------------------------------------------------------

RELEVANCE_WEIGHTS = {
    "highly_relevant": 1.0,
    "relevant": 0.75,
    "somewhat_relevant": 0.5,
    "marginally_relevant": 0.25,
}


def _get_relevance(query_labels: dict, card: str) -> float:
    """Get graded relevance for a card given query labels."""
    for level, weight in RELEVANCE_WEIGHTS.items():
        if card in query_labels.get(level, []):
            return weight
    return 0.0


def compute_ndcg(predictions: list[str], query_labels: dict, k: int = 10) -> float:
    """Compute nDCG@k with graded relevance."""
    # DCG
    dcg = 0.0
    for i, card in enumerate(predictions[:k]):
        rel = _get_relevance(query_labels, card)
        dcg += rel / np.log2(i + 2)  # log2(rank+1), rank is 1-indexed

    # Ideal DCG: sort all relevant items by weight descending
    all_rels = []
    for level, weight in RELEVANCE_WEIGHTS.items():
        all_rels.extend([weight] * len(query_labels.get(level, [])))
    all_rels.sort(reverse=True)

    idcg = 0.0
    for i, rel in enumerate(all_rels[:k]):
        idcg += rel / np.log2(i + 2)

    return dcg / idcg if idcg > 0 else 0.0


def compute_precision(predictions: list[str], query_labels: dict, k: int = 10) -> float:
    """Weighted P@k."""
    total = 0.0
    for card in predictions[:k]:
        total += _get_relevance(query_labels, card)
    return total / k


def compute_mrr(predictions: list[str], query_labels: dict, k: int = 10) -> float:
    """MRR@k: reciprocal rank of first relevant hit."""
    relevant = set()
    for level in RELEVANCE_WEIGHTS:
        relevant.update(query_labels.get(level, []))
    for i, card in enumerate(predictions[:k]):
        if card in relevant:
            return 1.0 / (i + 1)
    return 0.0


def evaluate_embeddings(
    kv: KeyedVectors,
    test_set: dict,
    k: int = 10,
) -> dict[str, float]:
    """Evaluate embeddings against test set, return aggregated metrics."""
    ndcgs, precs, mrrs = [], [], []
    evaluated = 0
    skipped = 0

    for query, labels in test_set.items():
        if query not in kv:
            skipped += 1
            continue

        try:
            sims = kv.most_similar(query, topn=k)
            preds = [card for card, _ in sims]
        except KeyError:
            skipped += 1
            continue

        ndcgs.append(compute_ndcg(preds, labels, k))
        precs.append(compute_precision(preds, labels, k))
        mrrs.append(compute_mrr(preds, labels, k))
        evaluated += 1

    if not evaluated:
        return {"ndcg@10": 0.0, "p@10": 0.0, "mrr@10": 0.0, "evaluated": 0, "skipped": skipped}

    return {
        "ndcg@10": float(np.mean(ndcgs)),
        "p@10": float(np.mean(precs)),
        "mrr@10": float(np.mean(mrrs)),
        "evaluated": evaluated,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Compare PecanPy vs PyG GraphSAGE embeddings")
    parser.add_argument("--edgelist", type=Path, required=True, help="Input edgelist (.edg)")
    parser.add_argument("--test-set", type=Path, required=True, help="Test set JSON")
    parser.add_argument("--output-dir", type=Path, default=Path("data/embeddings"))
    parser.add_argument("--prefix", type=str, default="comparison")
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--pecanpy-walks", type=int, default=10)
    parser.add_argument("--pecanpy-walk-length", type=int, default=80)
    parser.add_argument("--pecanpy-epochs", type=int, default=5)
    parser.add_argument("--gnn-epochs", type=int, default=200)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    if not args.edgelist.exists():
        print(f"Error: edgelist not found: {args.edgelist}", file=sys.stderr)
        return 1

    # Load test set (handle unified format with "queries" wrapper)
    with open(args.test_set) as f:
        raw = json.load(f)
    test_set = raw.get("queries", raw)
    # Filter out metadata keys
    test_set = {k: v for k, v in test_set.items() if isinstance(v, dict)}
    print(f"Test set: {len(test_set)} queries from {args.test_set.name}")

    # Load edges (shared between both methods)
    print(f"\nLoading edgelist: {args.edgelist}")
    edges = load_edgelist(args.edgelist)
    node_to_idx, idx_to_node = build_index(edges)
    print(f"  {len(node_to_idx):,} nodes, {len(edges):,} edges")

    # Check test set coverage
    in_graph = sum(1 for q in test_set if q in node_to_idx)
    print(f"  Test queries in graph: {in_graph}/{len(test_set)}")

    if in_graph == 0:
        print("Error: no test queries found in graph. Wrong edgelist for this test set?", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    # --- Method 1: PecanPy node2vec+ ---
    print(f"\n{'='*60}")
    print("Method 1: PecanPy node2vec+")
    print(f"  walks={args.pecanpy_walks}, walk_length={args.pecanpy_walk_length}, "
          f"epochs={args.pecanpy_epochs}, dim={args.dim}")
    print(f"{'='*60}")

    t0 = time.monotonic()
    pecan_kv = train_pecanpy(
        args.edgelist,
        dim=args.dim,
        walk_length=args.pecanpy_walk_length,
        num_walks=args.pecanpy_walks,
        epochs=args.pecanpy_epochs,
        workers=args.workers,
    )
    pecan_time = time.monotonic() - t0
    print(f"  Trained in {pecan_time:.1f}s, {len(pecan_kv):,} vectors")

    pecan_path = args.output_dir / f"{args.prefix}_pecanpy.wv"
    pecan_kv.save(str(pecan_path))
    print(f"  Saved: {pecan_path}")

    pecan_metrics = evaluate_embeddings(pecan_kv, test_set)
    results["pecanpy_node2vec+"] = {**pecan_metrics, "train_time_s": round(pecan_time, 1)}
    print(f"  nDCG@10={pecan_metrics['ndcg@10']:.4f}  P@10={pecan_metrics['p@10']:.4f}  "
          f"MRR@10={pecan_metrics['mrr@10']:.4f}  (eval={pecan_metrics['evaluated']}, skip={pecan_metrics['skipped']})")

    # --- Method 2: PyG GraphSAGE ---
    print(f"\n{'='*60}")
    print("Method 2: PyG GraphSAGE (link prediction)")
    print(f"  epochs={args.gnn_epochs}, dim={args.dim}")
    print(f"{'='*60}")

    t0 = time.monotonic()
    sage_kv = train_graphsage(
        edges,
        node_to_idx,
        idx_to_node,
        dim=args.dim,
        epochs=args.gnn_epochs,
    )
    sage_time = time.monotonic() - t0
    print(f"  Trained in {sage_time:.1f}s, {len(sage_kv):,} vectors")

    sage_path = args.output_dir / f"{args.prefix}_graphsage.wv"
    sage_kv.save(str(sage_path))
    print(f"  Saved: {sage_path}")

    sage_metrics = evaluate_embeddings(sage_kv, test_set)
    results["pyg_graphsage"] = {**sage_metrics, "train_time_s": round(sage_time, 1)}
    print(f"  nDCG@10={sage_metrics['ndcg@10']:.4f}  P@10={sage_metrics['p@10']:.4f}  "
          f"MRR@10={sage_metrics['mrr@10']:.4f}  (eval={sage_metrics['evaluated']}, skip={sage_metrics['skipped']})")

    # --- Summary ---
    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"{'Method':<25} {'nDCG@10':>8} {'P@10':>8} {'MRR@10':>8} {'Time':>8}")
    print("-" * 60)
    for name, m in results.items():
        print(f"{name:<25} {m['ndcg@10']:>8.4f} {m['p@10']:>8.4f} {m['mrr@10']:>8.4f} {m['train_time_s']:>7.1f}s")
    print("-" * 60)

    # Winner
    pecan_ndcg = results["pecanpy_node2vec+"]["ndcg@10"]
    sage_ndcg = results["pyg_graphsage"]["ndcg@10"]
    delta = sage_ndcg - pecan_ndcg
    if abs(delta) < 0.01:
        print("Result: Effectively tied (delta < 0.01)")
    elif delta > 0:
        print(f"Result: GraphSAGE wins by {delta:+.4f} nDCG")
    else:
        print(f"Result: PecanPy wins by {-delta:+.4f} nDCG")

    # Save results
    results_path = args.output_dir / f"{args.prefix}_comparison.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved: {results_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
