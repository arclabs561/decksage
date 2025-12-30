#!/usr/bin/env python3
"""
Attributed Graph Embeddings using PyTorch Geometric

Key improvement: Use card attributes (color, type, CMC) and edge attributes (format, partition)
instead of just co-occurrence counts.

Hypothesis: Adding attributes should beat unattributed Node2Vec and Jaccard.
"""

import argparse

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

try:
    from gensim.models import KeyedVectors

    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False

try:
    from torch_geometric.data import Data
    from torch_geometric.nn import GATConv

    HAS_PYGE = True
except ImportError:
    HAS_PYGE = False
    print("Install: pip install torch torch-geometric")


def load_graph_with_attributes(pairs_csv: str):
    """
    Load co-occurrence graph.
    For now, just counts. Later: fetch Scryfall attributes.
    """
    df = pd.read_csv(pairs_csv)

    # Build card index
    all_cards = sorted(set(df["NAME_1"]) | set(df["NAME_2"]))
    card_to_idx = {c: i for i, c in enumerate(all_cards)}

    # Build edge list
    edges = []
    edge_weights = []

    for _, row in df.iterrows():
        i = card_to_idx[row["NAME_1"]]
        j = card_to_idx[row["NAME_2"]]
        w = row["COUNT_MULTISET"]

        edges.append([i, j])
        edges.append([j, i])
        edge_weights.append(w)
        edge_weights.append(w)

    edge_index = torch.tensor(edges, dtype=torch.long).t()
    edge_attr = torch.tensor(edge_weights, dtype=torch.float).unsqueeze(1)

    # Node features: For now, just degree (simple baseline)
    # TODO: Add color, type, CMC from Scryfall
    degree = torch.zeros(len(all_cards), 1)
    for i, j in edges:
        degree[i] += 1

    x = degree / degree.max()  # Normalize

    return (
        Data(x=x, edge_index=edge_index, edge_attr=edge_attr, num_nodes=len(all_cards)),
        card_to_idx,
        all_cards,
    )


class AttributedGAT(torch.nn.Module):
    """
    Simple GAT model with edge attributes.
    Learns to use both node features and edge weights.
    """

    def __init__(self, in_channels, hidden_channels, out_channels, edge_dim):
        super().__init__()
        self.conv1 = GATConv(in_channels, hidden_channels, edge_dim=edge_dim)
        self.conv2 = GATConv(hidden_channels, out_channels, edge_dim=edge_dim)

    def forward(self, x, edge_index, edge_attr):
        x = self.conv1(x, edge_index, edge_attr)
        x = F.relu(x)
        x = F.dropout(x, p=0.1, training=self.training)
        x = self.conv2(x, edge_index, edge_attr)
        return x


def train_attributed_model(data, epochs=100, dim=64):
    """Train GAT model"""
    model = AttributedGAT(
        in_channels=data.x.size(1),
        hidden_channels=128,
        out_channels=dim,
        edge_dim=data.edge_attr.size(1),
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=0.005)

    model.train()
    for epoch in range(1, epochs + 1):
        optimizer.zero_grad()

        # Get embeddings
        z = model(data.x, data.edge_index, data.edge_attr)

        # Self-supervised loss: Predict edge existence
        # Sample positive edges
        pos_edge_index = data.edge_index[:, :1000]
        pos_scores = (z[pos_edge_index[0]] * z[pos_edge_index[1]]).sum(dim=1)

        # Sample negative edges (non-existent)
        neg_src = torch.randint(0, data.num_nodes, (1000,))
        neg_dst = torch.randint(0, data.num_nodes, (1000,))
        neg_scores = (z[neg_src] * z[neg_dst]).sum(dim=1)

        # Binary cross-entropy loss
        pos_loss = -torch.log(torch.sigmoid(pos_scores) + 1e-15).mean()
        neg_loss = -torch.log(1 - torch.sigmoid(neg_scores) + 1e-15).mean()
        loss = pos_loss + neg_loss

        loss.backward()
        optimizer.step()

        if epoch % 20 == 0:
            print(f"Epoch {epoch}/{epochs}, Loss: {loss.item():.4f}")

    return model


def get_embeddings(model, data):
    """Get trained embeddings"""
    model.eval()
    with torch.no_grad():
        embeddings = model(data.x, data.edge_index, data.edge_attr)
    return embeddings.numpy()


def find_similar_attributed(model, data, card_idx, top_k=10):
    """Find similar cards using trained GAT"""
    embeddings = get_embeddings(model, data)

    query_emb = embeddings[card_idx]

    # Cosine similarity
    similarities = (
        embeddings
        @ query_emb
        / (np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_emb) + 1e-15)
    )

    # Top-k (excluding self)
    top_indices = np.argsort(similarities)[::-1][1 : top_k + 1]

    return [(idx, float(similarities[idx])) for idx in top_indices]


def main():
    parser = argparse.ArgumentParser(description="Attributed graph embeddings")
    parser.add_argument("--pairs", type=str, required=True)
    parser.add_argument("--dim", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--query", type=str, nargs="+", default=["Lightning Bolt"])
    parser.add_argument("--output", type=str, default="attributed_embeddings.wv")

    args = parser.parse_args()

    if not HAS_PYGE:
        print("PyTorch Geometric not installed")
        print("Install: pip install torch torch-geometric")
        return 1

    # Load graph
    print("Loading attributed graph...")
    data, card_to_idx, idx_to_card = load_graph_with_attributes(args.pairs)
    print(f"  Nodes: {data.num_nodes:,}")
    print(f"  Edges: {data.edge_index.size(1):,}")
    print(f"  Node features: {data.x.size(1)}")
    print(f"  Edge features: {data.edge_attr.size(1)}")

    # Train
    print(f"\nTraining GAT model ({args.epochs} epochs)...")
    model = train_attributed_model(data, epochs=args.epochs, dim=args.dim)

    # Get embeddings
    embeddings = get_embeddings(model, data)

    # Save in Gensim format for compatibility
    if HAS_GENSIM:
        wv = KeyedVectors(vector_size=args.dim)
        wv.add_vectors(idx_to_card, embeddings)
        wv.save(args.output)
        print(f"✓ Saved: {args.output}")

    # Demo
    print(f"\n{'=' * 60}")
    print("DEMO: Attributed GAT Similarity")
    print("=" * 60)

    for query in args.query:
        if query not in card_to_idx:
            print(f"Card '{query}' not found")
            continue

        idx = card_to_idx[query]
        similar = find_similar_attributed(model, data, idx, top_k=10)

        print(f"\nSimilar to '{query}':")
        for rank, (sim_idx, score) in enumerate(similar, 1):
            card = idx_to_card[sim_idx]
            print(f"  {rank:2d}. {card:40s} {score:.4f}")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
