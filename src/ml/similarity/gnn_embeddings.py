#!/usr/bin/env python3
"""
Graph Neural Network Embeddings using PyTorch Geometric

Learns card representations from co-occurrence graph structure.
Uses GNNs (GCN, GAT, GraphSAGE) to potentially break the P@10=0.08 plateau.

This is a forward-looking implementation - can be trained when ready.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.data import Data, Dataset
    from torch_geometric.nn import GCNConv, GATConv, SAGEConv
    from torch_geometric.loader import DataLoader

    HAS_PYG = True
except ImportError:
    HAS_PYG = False
    print("Install PyTorch Geometric: pip install torch torch-geometric")


class CardGraphDataset(Dataset):
    """PyG Dataset for card co-occurrence graph."""

    def __init__(
        self,
        edgelist_path: Path | str,
        root: Path | str | None = None,
        transform: Any = None,
        pre_transform: Any = None,
    ):
        self.edgelist_path = Path(edgelist_path)
        super().__init__(root, transform, pre_transform)

    @property
    def raw_file_names(self) -> list[str]:
        return [str(self.edgelist_path)]

    @property
    def processed_file_names(self) -> list[str]:
        return ["data.pt"]

    def download(self):
        # No download needed, we have the edgelist
        pass

    def process(self):
        """Load edgelist and create PyG Data object."""
        if not HAS_PYG:
            raise ImportError("PyTorch Geometric required")

        # Load edgelist
        edges = []
        node_to_idx: dict[str, int] = {}
        idx_to_node: dict[int, str] = {}

        with open(self.edgelist_path) as f:
            for line in f:
                if line.strip().startswith("#") or not line.strip():
                    continue
                parts = line.strip().split()
                if len(parts) < 2:
                    continue

                card1, card2 = parts[0], parts[1]
                weight = float(parts[2]) if len(parts) > 2 else 1.0

                # Map nodes to indices
                if card1 not in node_to_idx:
                    idx = len(node_to_idx)
                    node_to_idx[card1] = idx
                    idx_to_node[idx] = card1

                if card2 not in node_to_idx:
                    idx = len(node_to_idx)
                    node_to_idx[card2] = idx
                    idx_to_node[idx] = card2

                edges.append((node_to_idx[card1], node_to_idx[card2], weight))

        # Create edge index and edge attributes
        edge_index = torch.tensor(
            [[e[0] for e in edges], [e[1] for e in edges]], dtype=torch.long
        )
        edge_attr = torch.tensor([e[2] for e in edges], dtype=torch.float)

        # Create node features (one-hot or learned)
        num_nodes = len(node_to_idx)
        x = torch.eye(num_nodes)  # Identity matrix (can be replaced with learned features)

        # Create PyG Data object
        data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr)

        # Save node mappings
        data.node_to_idx = node_to_idx
        data.idx_to_node = idx_to_node

        torch.save(data, self.processed_paths[0])

    def len(self) -> int:
        return 1  # Single graph

    def get(self, idx: int) -> Data:
        return torch.load(self.processed_paths[0])


class GCNEncoder(nn.Module):
    """Graph Convolutional Network encoder."""

    def __init__(self, num_nodes: int, hidden_dim: int = 128, num_layers: int = 2):
        super().__init__()
        self.num_nodes = num_nodes
        self.hidden_dim = hidden_dim

        self.convs = nn.ModuleList()
        self.convs.append(GCNConv(num_nodes, hidden_dim))
        for _ in range(num_layers - 2):
            self.convs.append(GCNConv(hidden_dim, hidden_dim))
        if num_layers > 1:
            self.convs.append(GCNConv(hidden_dim, hidden_dim))

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        for i, conv in enumerate(self.convs):
            x = conv(x, edge_index)
            if i < len(self.convs) - 1:
                x = F.relu(x)
                x = F.dropout(x, p=0.5, training=self.training)
        return x


class GATEncoder(nn.Module):
    """Graph Attention Network encoder."""

    def __init__(
        self,
        num_nodes: int,
        hidden_dim: int = 128,
        num_layers: int = 2,
        heads: int = 4,
    ):
        super().__init__()
        self.num_nodes = num_nodes
        self.hidden_dim = hidden_dim

        self.convs = nn.ModuleList()
        self.convs.append(GATConv(num_nodes, hidden_dim, heads=heads, concat=True))
        for _ in range(num_layers - 2):
            self.convs.append(
                GATConv(hidden_dim * heads, hidden_dim, heads=heads, concat=True)
            )
        if num_layers > 1:
            self.convs.append(
                GATConv(hidden_dim * heads, hidden_dim, heads=1, concat=False)
            )

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        for i, conv in enumerate(self.convs):
            x = conv(x, edge_index)
            if i < len(self.convs) - 1:
                x = F.relu(x)
                x = F.dropout(x, p=0.5, training=self.training)
        return x


class GraphSAGEEncoder(nn.Module):
    """GraphSAGE encoder."""

    def __init__(self, num_nodes: int, hidden_dim: int = 128, num_layers: int = 2):
        super().__init__()
        self.num_nodes = num_nodes
        self.hidden_dim = hidden_dim

        self.convs = nn.ModuleList()
        self.convs.append(SAGEConv(num_nodes, hidden_dim))
        for _ in range(num_layers - 2):
            self.convs.append(SAGEConv(hidden_dim, hidden_dim))
        if num_layers > 1:
            self.convs.append(SAGEConv(hidden_dim, hidden_dim))

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        for i, conv in enumerate(self.convs):
            x = conv(x, edge_index)
            if i < len(self.convs) - 1:
                x = F.relu(x)
                x = F.dropout(x, p=0.5, training=self.training)
        return x


class CardGNNEmbedder:
    """GNN-based card embedder using PyTorch Geometric.
    
    Based on expert guidance:
    - GraphSAGE is best for co-occurrence graphs (low-homophily)
    - Keep models shallow (2 layers)
    - Use link prediction for training
    - Use NeighborLoader for scalability
    """

    def __init__(
        self,
        model_path: Path | str | None = None,
        model_type: str = "GraphSAGE",  # Changed default to GraphSAGE
        hidden_dim: int = 128,
        num_layers: int = 2,  # Keep shallow per expert guidance
    ):
        if not HAS_PYG:
            raise ImportError("PyTorch Geometric required: pip install torch torch-geometric")

        self.model_type = model_type
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.model: nn.Module | None = None
        self.node_to_idx: dict[str, int] = {}
        self.idx_to_node: dict[int, str] = {}
        self.embeddings: dict[str, torch.Tensor] = {}

        if model_path:
            self.load(model_path)

    def train(
        self,
        edgelist_path: Path | str,
        epochs: int = 100,
        lr: float = 0.01,
        output_path: Path | str | None = None,
    ):
        """Train GNN on co-occurrence graph."""
        if not HAS_PYG:
            raise ImportError("PyTorch Geometric required")

        # Load dataset
        dataset = CardGraphDataset(edgelist_path)
        data = dataset[0]

        self.node_to_idx = data.node_to_idx
        self.idx_to_node = data.idx_to_node

        # Create model
        num_nodes = len(self.node_to_idx)
        if self.model_type == "GCN":
            self.model = GCNEncoder(num_nodes, self.hidden_dim, self.num_layers)
        elif self.model_type == "GAT":
            self.model = GATEncoder(num_nodes, self.hidden_dim, self.num_layers)
        elif self.model_type == "GraphSAGE":
            self.model = GraphSAGEEncoder(num_nodes, self.hidden_dim, self.num_layers)
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

        # Training setup - Link prediction (expert recommended)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr, weight_decay=5e-4)
        
        self.model.train()
        best_loss = float('inf')
        patience = 10
        patience_counter = 0
        
        for epoch in range(epochs):
            optimizer.zero_grad()

            # Forward pass
            embeddings = self.model(data.x, data.edge_index)

            # Link prediction: sample positive and negative edges
            # Positive edges: existing edges (use edge_index)
            pos_edge_index = data.edge_index
            pos_src, pos_dst = pos_edge_index[0], pos_edge_index[1]
            pos_scores = (embeddings[pos_src] * embeddings[pos_dst]).sum(dim=1)
            
            # Negative edges: sample random non-edges
            num_neg = pos_edge_index.size(1)
            neg_src = torch.randint(0, data.num_nodes, (num_neg,), device=data.x.device)
            neg_dst = torch.randint(0, data.num_nodes, (num_neg,), device=data.x.device)
            neg_scores = (embeddings[neg_src] * embeddings[neg_dst]).sum(dim=1)
            
            # Binary cross-entropy loss (expert recommended)
            pos_loss = -torch.log(torch.sigmoid(pos_scores) + 1e-15).mean()
            neg_loss = -torch.log(1 - torch.sigmoid(neg_scores) + 1e-15).mean()
            loss = pos_loss + neg_loss

            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            optimizer.step()

            # Early stopping
            if loss.item() < best_loss:
                best_loss = loss.item()
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    print(f"Early stopping at epoch {epoch+1}")
                    break

            if (epoch + 1) % 10 == 0:
                print(f"Epoch {epoch+1}/{epochs}, Loss: {loss.item():.4f}, Pos: {pos_loss.item():.4f}, Neg: {neg_loss.item():.4f}")

        # Extract embeddings
        self.model.eval()
        with torch.no_grad():
            embeddings = self.model(data.x, data.edge_index)
            for idx, node in self.idx_to_node.items():
                self.embeddings[node] = embeddings[idx].cpu()

        # Save model
        if output_path:
            self.save(output_path)

    def save(self, path: Path | str):
        """Save model and embeddings."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "model_type": self.model_type,
            "hidden_dim": self.hidden_dim,
            "num_layers": self.num_layers,
            "node_to_idx": self.node_to_idx,
            "idx_to_node": self.idx_to_node,
            "model_state": self.model.state_dict() if self.model else None,
            "embeddings": {k: v.tolist() for k, v in self.embeddings.items()},
        }

        with open(path, "w") as f:
            json.dump(state, f)

    def load(self, path: Path | str):
        """Load model and embeddings."""
        path = Path(path)
        with open(path) as f:
            state = json.load(f)

        self.model_type = state["model_type"]
        self.hidden_dim = state["hidden_dim"]
        self.num_layers = state["num_layers"]
        self.node_to_idx = {k: int(v) for k, v in state["node_to_idx"].items()}
        self.idx_to_node = {int(k): v for k, v in state["idx_to_node"].items()}

        # Reconstruct model (would need to load state dict if training)
        # For now, just load embeddings
        self.embeddings = {
            k: torch.tensor(v) for k, v in state["embeddings"].items()
        }

    def similarity(self, card1: str, card2: str) -> float:
        """Compute cosine similarity between two cards."""
        if card1 not in self.embeddings or card2 not in self.embeddings:
            return 0.0

        emb1 = self.embeddings[card1]
        emb2 = self.embeddings[card2]

        return float(F.cosine_similarity(emb1.unsqueeze(0), emb2.unsqueeze(0))[0])

    def most_similar(self, card: str, topn: int = 10) -> list[tuple[str, float]]:
        """Find most similar cards."""
        if card not in self.embeddings:
            return []

        card_emb = self.embeddings[card]
        similarities = []

        for other_card, other_emb in self.embeddings.items():
            if other_card == card:
                continue
            sim = float(F.cosine_similarity(card_emb.unsqueeze(0), other_emb.unsqueeze(0))[0])
            similarities.append((other_card, sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:topn]


if __name__ == "__main__":
    from ..utils.paths import PATHS

    # Example usage
    edgelist = PATHS.graph("magic_39k_decks")
    if edgelist.exists():
        print("Training GCN on card co-occurrence graph...")
        embedder = CardGNNEmbedder(model_type="GCN", hidden_dim=128, num_layers=2)
        embedder.train(edgelist, epochs=50, output_path=PATHS.embeddings / "gnn_gcn.json")
        print("✓ Training complete")
    else:
        print(f"Graph file not found: {edgelist}")

