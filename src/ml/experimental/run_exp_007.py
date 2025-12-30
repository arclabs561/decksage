#!/usr/bin/env python3
"""
exp_007: GCN with Node Features

Hypothesis: Adding card attributes beats unattributed Node2Vec
Method: Simple GCN with [color, type, CMC] features
"""

import json

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from torch_geometric.data import Data
from torch_geometric.nn import GCNConv


# Step 1: Build feature matrix from cards in graph
def load_cards_in_graph(pairs_csv):
    """Get list of cards we need features for"""
    df = pd.read_csv(pairs_csv)
    cards = sorted(set(df["NAME_1"]) | set(df["NAME_2"]))
    return cards, df


def build_simple_features(cards):
    """
    Build simple features without Scryfall (for quick test).

    Features:
    - Degree (from graph)
    - Name length (proxy for complexity)
    - Has 'the' in name
    - Random noise (control)
    """
    features = []
    for card in cards:
        feat = [
            len(card) / 50.0,  # Name length normalized
            1.0 if "the" in card.lower() else 0.0,
            1.0 if any(c.isdigit() for c in card) else 0.0,
            np.random.random(),  # Control (should not help)
        ]
        features.append(feat)

    return torch.tensor(features, dtype=torch.float)


# Step 2: Build PyG graph
def build_pyg_graph(df, cards):
    """Build PyTorch Geometric graph"""
    card_to_idx = {c: i for i, c in enumerate(cards)}

    edges = []
    weights = []

    for _, row in df.iterrows():
        i = card_to_idx[row["NAME_1"]]
        j = card_to_idx[row["NAME_2"]]
        w = row["COUNT_MULTISET"]

        edges.append([i, j])
        edges.append([j, i])
        weights.append(w)
        weights.append(w)

    edge_index = torch.tensor(edges, dtype=torch.long).t()
    edge_weight = torch.tensor(weights, dtype=torch.float)

    # Build features
    x = build_simple_features(cards)

    return Data(
        x=x, edge_index=edge_index, edge_weight=edge_weight, num_nodes=len(cards)
    ), card_to_idx


# Step 3: Simple GCN model
class SimpleGCN(torch.nn.Module):
    def __init__(self, in_channels, hidden_channels, out_channels):
        super().__init__()
        self.conv1 = GCNConv(in_channels, hidden_channels)
        self.conv2 = GCNConv(hidden_channels, out_channels)

    def forward(self, x, edge_index, edge_weight=None):
        x = self.conv1(x, edge_index, edge_weight)
        x = F.relu(x)
        x = F.dropout(x, p=0.1, training=self.training)
        x = self.conv2(x, edge_index, edge_weight)
        return x


# Step 4: Train with link prediction
def train_gcn(data, epochs=50):
    """Train GCN with unsupervised link prediction"""
    model = SimpleGCN(in_channels=data.x.size(1), hidden_channels=64, out_channels=32)

    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

    print(f"Training GCN: {data.num_nodes} nodes, {data.edge_index.size(1) // 2} edges")

    model.train()
    for epoch in range(1, epochs + 1):
        optimizer.zero_grad()

        z = model(data.x, data.edge_index, data.edge_weight)

        # Link prediction loss (sample edges)
        num_samples = min(1000, data.edge_index.size(1) // 2)
        pos_idx = torch.randint(0, data.edge_index.size(1), (num_samples,))
        pos_edge = data.edge_index[:, pos_idx]
        pos_score = (z[pos_edge[0]] * z[pos_edge[1]]).sum(dim=1)

        # Negative samples
        neg_src = torch.randint(0, data.num_nodes, (num_samples,))
        neg_dst = torch.randint(0, data.num_nodes, (num_samples,))
        neg_score = (z[neg_src] * z[neg_dst]).sum(dim=1)

        # BCE loss
        pos_loss = -torch.log(torch.sigmoid(pos_score) + 1e-15).mean()
        neg_loss = -torch.log(1 - torch.sigmoid(neg_score) + 1e-15).mean()
        loss = pos_loss + neg_loss

        loss.backward()
        optimizer.step()

        if epoch % 10 == 0:
            print(f"  Epoch {epoch}/{epochs}, Loss: {loss.item():.4f}")

    return model


# Step 5: Evaluate
def evaluate_gcn(model, data, card_to_idx, test_queries):
    """Evaluate on test queries"""
    model.eval()

    with torch.no_grad():
        embeddings = model(data.x, data.edge_index, data.edge_weight).numpy()

    idx_to_card = {i: c for c, i in card_to_idx.items()}

    results = {}
    for query in test_queries:
        if query not in card_to_idx:
            continue

        idx = card_to_idx[query]
        query_emb = embeddings[idx]

        # Cosine similarity
        sims = (
            embeddings
            @ query_emb
            / (np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_emb) + 1e-15)
        )

        # Top-10
        top_idx = np.argsort(sims)[::-1][1:11]  # Exclude self
        results[query] = [(idx_to_card[i], float(sims[i])) for i in top_idx]

    return results


# Main experiment
def main():
    print("=" * 60)
    print("exp_007: GCN with Simple Node Features")
    print("=" * 60)

    # Load data
    pairs_csv = "../backend/pairs_500decks.csv"
    cards, df = load_cards_in_graph(pairs_csv)

    print(f"\nData: {len(cards)} cards, {len(df)} edges")

    # Build graph
    data, card_to_idx = build_pyg_graph(df, cards)
    print(f"Features: {data.x.size(1)}-dim")

    # Train
    model = train_gcn(data, epochs=50)

    # Evaluate on diverse queries
    test_queries = [
        "Lightning Bolt",
        "Brainstorm",
        "Dark Ritual",
        "Counterspell",
        "Sol Ring",
        "Tarmogoyf",
    ]

    results = evaluate_gcn(model, data, card_to_idx, test_queries)

    # Display
    print(f"\n{'=' * 60}")
    print("Results:")
    print("=" * 60)

    for query, preds in results.items():
        print(f"\n{query}:")
        for i, (card, score) in enumerate(preds[:5], 1):
            print(f"  {i}. {card:40s} {score:.4f}")

    # Compare to baseline (load previous results)
    print(f"\n{'=' * 60}")
    print("Comparison:")
    print("=" * 60)
    print("exp_007 (GCN): Visual inspection above")
    print("Baseline (Jaccard): 83% accuracy on diverse queries")
    print("\nManual evaluation needed on these 6 queries")

    # Log experiment
    with open("../../experiments/EXPERIMENT_LOG.jsonl", "a") as f:
        exp = {
            "experiment_id": "exp_007",
            "date": "2025-10-01",
            "phase": "node_attributed_gnn",
            "hypothesis": "Simple node features will improve over unattributed Node2Vec",
            "method": "GCN with 4 simple features (name length, has the, has digit, random)",
            "data": "500 MTG decks, 1,951 cards",
            "results": {"qualitative": "see manual evaluation"},
            "learnings": ["Need to visually inspect results", "Random features as control"],
            "next_steps": ["Add real Scryfall features", "Quantitative evaluation"],
        }
        f.write(json.dumps(exp) + "\n")

    print("\n✓ Logged exp_007")


if __name__ == "__main__":
    main()
