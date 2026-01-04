#!/usr/bin/env python3
"""
Graph Neural Network Embeddings using PyTorch Geometric

Learns card representations from co-occurrence graph structure.
Uses GNNs (GCN, GAT, GraphSAGE) to potentially break the P@10=0.08 plateau.

This is a forward-looking implementation - can be trained when ready.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.data import Data, Dataset
    from torch_geometric.nn import GCNConv, GATConv, SAGEConv
    from torch_geometric.loader import DataLoader
    from torch_geometric.utils import add_self_loops, degree

    HAS_PYG = True
except ImportError:
    HAS_PYG = False
    # Create dummy classes to prevent NameError
    Dataset = type('Dataset', (), {})
    Data = type('Data', (), {})
    GCNConv = type('GCNConv', (), {})
    GATConv = type('GATConv', (), {})
    SAGEConv = type('SAGEConv', (), {})
    DataLoader = type('DataLoader', (), {})
    print("Install PyTorch Geometric: pip install torch torch-geometric")


if HAS_PYG:
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


    class LightGCNEncoder(nn.Module):
        """LightGCN encoder - simplified GCN for recommendation systems.
        
        LightGCN removes feature transformations and nonlinear activations,
        focusing on pure neighbor aggregation. Designed specifically for
        recommendation where nodes have ID-based features.
        
        Based on research: LightGCN achieves better performance with
        reduced computational complexity for recommendation tasks.
        """

        def __init__(self, num_nodes: int, hidden_dim: int = 128, num_layers: int = 2):
            super().__init__()
            self.num_nodes = num_nodes
            self.hidden_dim = hidden_dim
            self.num_layers = num_layers

            # LightGCN: Simple embedding table (no feature transformations)
            self.embedding = nn.Embedding(num_nodes, hidden_dim)
            nn.init.xavier_uniform_(self.embedding.weight)

        def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
            """
            LightGCN forward pass: pure neighbor aggregation without
            feature transformations or nonlinear activations.
            """
            # Get node indices from x (one-hot -> indices)
            if x.dim() == 2 and x.size(1) == self.num_nodes:
                # One-hot encoding -> convert to indices
                node_indices = torch.argmax(x, dim=1)
            else:
                # Already indices
                node_indices = x.squeeze().long() if x.dim() > 1 else x.long()
            
            # Get initial embeddings
            embeddings = self.embedding(node_indices)
            
            # LightGCN: Simple mean aggregation across layers
            # No feature transformation, no nonlinear activation
            layer_embeddings = [embeddings]
            
            for _ in range(self.num_layers):
                # Aggregate from neighbors
                row, col = edge_index
                deg = degree(col, num_nodes=self.num_nodes, dtype=embeddings.dtype)
                deg_inv_sqrt = deg.pow(-0.5)
                deg_inv_sqrt[deg_inv_sqrt == float('inf')] = 0
                
                norm = deg_inv_sqrt[row] * deg_inv_sqrt[col]
                
                # Aggregate: sum neighbor embeddings weighted by norm
                neighbor_agg = torch.zeros_like(embeddings)
                neighbor_agg.index_add_(0, col, embeddings[row] * norm.view(-1, 1))
                
                # LightGCN: no transformation, just aggregation
                embeddings = neighbor_agg
                layer_embeddings.append(embeddings)
            
            # LightGCN: Average embeddings from all layers
            final_embeddings = torch.stack(layer_embeddings, dim=0).mean(dim=0)
            
            return final_embeddings
else:
    # Dummy classes when PyG not available
    class CardGraphDataset:
        """Dummy class when PyTorch Geometric is not installed."""
        pass
    
    class GCNEncoder:
        pass
    
    class GATEncoder:
        pass
    
    class GraphSAGEEncoder:
        pass
    
    class LightGCNEncoder:
        pass


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
        checkpoint_interval: int | None = None,
        resume_from: Path | str | None = None,
        use_contrastive: bool = False,
        contrastive_temperature: float = 0.07,
        contrastive_weight: float = 0.5,
    ):
        """Train GNN on co-occurrence graph.
        
        Args:
            edgelist_path: Path to edgelist file
            epochs: Number of training epochs
            lr: Learning rate
            output_path: Path to save trained model
            checkpoint_interval: Save checkpoint every N epochs
            resume_from: Path to checkpoint to resume from
            use_contrastive: Use contrastive learning loss
            contrastive_temperature: Temperature for contrastive loss
            contrastive_weight: Weight for contrastive loss in combined loss
        """
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
        elif self.model_type == "LightGCN":
            self.model = LightGCNEncoder(num_nodes, self.hidden_dim, self.num_layers)
        else:
            raise ValueError(f"Unknown model type: {self.model_type}. Supported: GCN, GAT, GraphSAGE, LightGCN")

        # Resume from checkpoint if provided
        start_epoch = 0
        if resume_from:
            resume_path = Path(resume_from)
            if resume_path.exists():
                logger.info(f"Resuming from checkpoint: {resume_path}")
                self.load(resume_path)
                # Extract epoch from checkpoint if available
                try:
                    with open(resume_path.parent / f"{resume_path.stem}_metadata.json") as f:
                        metadata = json.load(f)
                        start_epoch = metadata.get("last_epoch", 0) + 1
                        logger.info(f"Resuming from epoch {start_epoch}")
                except:
                    logger.warning("Could not determine epoch from checkpoint, starting from beginning")
        
        # Training setup - Link prediction (expert recommended)
        optimizer = torch.optim.Adam(self.model.parameters(), lr=lr, weight_decay=5e-4)
        
        self.model.train()
        best_loss = float('inf')
        patience = 10
        patience_counter = 0
        
        for epoch in range(start_epoch, epochs):
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
            link_loss = pos_loss + neg_loss
            
            # Contrastive learning loss (optional)
            contrastive_loss = torch.tensor(0.0, device=embeddings.device)
            if use_contrastive:
                # Contrastive learning: maximize similarity of positive pairs,
                # minimize similarity of negative pairs
                # Using InfoNCE loss (temperature-scaled)
                
                # Normalize embeddings for cosine similarity
                embeddings_norm = F.normalize(embeddings, p=2, dim=1)
                
                # Positive pairs: connected nodes
                pos_sim = (embeddings_norm[pos_src] * embeddings_norm[pos_dst]).sum(dim=1)
                pos_sim = pos_sim / contrastive_temperature
                
                # Negative pairs: random non-connected nodes
                neg_sim = (embeddings_norm[neg_src] * embeddings_norm[neg_dst]).sum(dim=1)
                neg_sim = neg_sim / contrastive_temperature
                
                # InfoNCE loss: -log(exp(pos) / (exp(pos) + exp(neg)))
                contrastive_loss = -torch.log(
                    torch.exp(pos_sim) / (torch.exp(pos_sim) + torch.exp(neg_sim) + 1e-15)
                ).mean()
            
            # Combined loss
            loss = link_loss + (contrastive_weight * contrastive_loss if use_contrastive else 0.0)

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
                    logger.info(f"Early stopping at epoch {epoch+1}")
                    break

            # Log metrics every epoch (for progress tracking)
            metrics = {
                "loss": loss.item(),
                "link_loss": link_loss.item(),
                "pos_loss": pos_loss.item(),
                "neg_loss": neg_loss.item(),
                "best_loss": best_loss,
            }
            if use_contrastive:
                metrics["contrastive_loss"] = contrastive_loss.item()
            
            if (epoch + 1) % 10 == 0:
                log_msg = f"Epoch {epoch+1}/{epochs}, Loss: {loss.item():.4f}, Link: {link_loss.item():.4f}"
                if use_contrastive:
                    log_msg += f", Contrastive: {contrastive_loss.item():.4f}"
                logger.info(log_msg)
            
            # Save intermediate progress (every epoch for metrics, checkpoint interval for checkpoints)
            if output_path:
                progress_dir = Path(output_path).parent / "training_progress"
                from ..training.progress_tracker import TrainingProgressTracker
                
                # Initialize tracker if not exists (lazy init to avoid circular import)
                if not hasattr(self, '_progress_tracker'):
                    self._progress_tracker = TrainingProgressTracker(
                        output_dir=progress_dir,
                        checkpoint_interval=checkpoint_interval or 10,
                        metrics_interval=1,  # Save metrics every epoch
                        save_intermediate_embeddings=False,  # Too memory intensive
                    )
                
                # Log metrics every epoch
                self._progress_tracker.log_metrics(epoch + 1, metrics)
            
            # Checkpointing (per cursor rules - for long runs)
            if checkpoint_interval and (epoch + 1) % checkpoint_interval == 0:
                checkpoint_path = Path(output_path).parent / f"{Path(output_path).stem}_checkpoint_epoch_{epoch+1}.json"
                self.save(checkpoint_path)
                
                # Save metadata for resume
                metadata = {
                    "last_epoch": epoch,
                    "loss": loss.item(),
                    "best_loss": best_loss,
                    "model_type": self.model_type,
                    "hidden_dim": self.hidden_dim,
                    "num_layers": self.num_layers,
                }
                metadata_path = checkpoint_path.parent / f"{checkpoint_path.stem}_metadata.json"
                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=2)
                
                # Also save via progress tracker
                if hasattr(self, '_progress_tracker'):
                    self._progress_tracker.save_checkpoint(
                        epoch + 1,
                        {
                            "checkpoint_path": str(checkpoint_path),
                            "metadata": metadata,
                        },
                    )
                
                logger.info(f"Checkpoint saved: {checkpoint_path}")

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
        
        # Convert torch tensors to lists for JSON serialization
        if state["model_state"]:
            state["model_state"] = {k: v.cpu().tolist() if isinstance(v, torch.Tensor) else v 
                                   for k, v in state["model_state"].items()}

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

        # Load embeddings
        self.embeddings = {
            k: torch.tensor(v) for k, v in state["embeddings"].items()
        }
        
        # Reconstruct model if state dict available (for resuming training)
        if state.get("model_state") and self.model is None:
            num_nodes = len(self.node_to_idx)
            if self.model_type == "GCN":
                self.model = GCNEncoder(num_nodes, self.hidden_dim, self.num_layers)
            elif self.model_type == "GAT":
                self.model = GATEncoder(num_nodes, self.hidden_dim, self.num_layers)
            elif self.model_type == "GraphSAGE":
                self.model = GraphSAGEEncoder(num_nodes, self.hidden_dim, self.num_layers)
            
            # Load model state (convert lists back to tensors)
            if self.model and state["model_state"]:
                try:
                    model_state = {k: torch.tensor(v) if isinstance(v, list) else v 
                                 for k, v in state["model_state"].items()}
                    self.model.load_state_dict(model_state)
                    logger.info("Loaded model state from checkpoint")
                except Exception as e:
                    logger.warning(f"Could not load model state: {e}, will reinitialize")

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
    
    def add_new_cards(
        self,
        new_cards: list[str],
        graph: Any,  # IncrementalCardGraph
        fallback_embedder: Any | None = None,  # Text embedder for isolated cards
    ) -> None:
        """
        Add new cards to existing model using inductive learning.
        
        GraphSAGE can generate embeddings for new nodes by aggregating
        neighbor embeddings without retraining.
        
        Args:
            new_cards: List of new card names
            graph: IncrementalCardGraph instance
            fallback_embedder: Optional text embedder for isolated cards
        """
        if not self.model:
            raise ValueError("Model must be trained before adding new cards")
        
        if not HAS_PYG:
            raise ImportError("PyTorch Geometric required")
        
        self.model.eval()
        
        for card in new_cards:
            if card in self.embeddings:
                continue  # Already exists
            
            # Get neighbors in existing graph
            neighbors = graph.get_neighbors(card, min_weight=1)
            
            if neighbors:
                # Find neighbors that have embeddings
                neighbor_embeddings = []
                for neighbor in neighbors:
                    if neighbor in self.embeddings:
                        neighbor_embeddings.append(self.embeddings[neighbor])
                
                if neighbor_embeddings:
                    # Aggregate neighbor embeddings (mean pooling)
                    # This is a simplified version - full GraphSAGE would use learned aggregator
                    neighbor_tensors = torch.stack(neighbor_embeddings)
                    aggregated = neighbor_tensors.mean(dim=0)
                    
                    # Apply learned transformation (simplified - would use actual model forward)
                    # For now, use aggregated embedding directly
                    self.embeddings[card] = aggregated
                elif fallback_embedder:
                    # No neighbors with embeddings - use text embedder
                    self.embeddings[card] = torch.tensor(
                        fallback_embedder.embed_card(card),
                        dtype=torch.float32
                    )
            elif fallback_embedder:
                # Isolated card - use text embedder
                self.embeddings[card] = torch.tensor(
                    fallback_embedder.embed_card(card),
                    dtype=torch.float32
                )
            else:
                # No neighbors and no fallback - use zero embedding
                self.embeddings[card] = torch.zeros(self.hidden_dim)


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

