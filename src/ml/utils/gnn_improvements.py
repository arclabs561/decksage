"""
GNN Training Improvements

Research-based improvements for GNN embeddings:
1. Hard negative mining (structure-aware)
2. Contrastive learning enhancements
3. LightGCN optimizations
4. Interactive GNN (IA-GCN) for ranking
"""

from __future__ import annotations

import logging
from typing import Any

try:
    import torch
    import torch.nn as nn
    from torch_geometric.data import Data
    HAS_PYG = True
except ImportError:
    HAS_PYG = False

try:
    from .logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


def compute_structure_aware_hard_negatives(
    data: Data,
    embeddings: torch.Tensor,
    positive_pairs: list[tuple[int, int]],
    top_k: int = 100,
    exclude_positives: bool = True,
) -> dict[tuple[int, int], list[int]]:
    """
    Compute structure-aware hard negatives for GNN training.
    
    Based on ProGCL approach: Estimates probability that negative is true negative,
    combining similarity with structural characteristics.
    
    Args:
        data: PyTorch Geometric data object
        embeddings: Node embeddings (num_nodes, dim)
        positive_pairs: List of (anchor_idx, positive_idx) pairs
        top_k: Select from top-K hardest negatives
        exclude_positives: Whether to exclude known positives
    
    Returns:
        Dictionary mapping (anchor, positive) -> list of hard negative node indices
    """
    if not HAS_PYG:
        raise ImportError("PyTorch Geometric required for hard negative mining")
    
    hard_negatives: dict[tuple[int, int], list[int]] = {}
    
    logger.info(f"Computing structure-aware hard negatives for {len(positive_pairs)} pairs...")
    
    # Build adjacency for structure analysis
    adj_dict: dict[int, set[int]] = {}
    edge_index = data.edge_index.cpu().numpy()
    for i in range(edge_index.shape[1]):
        src, dst = int(edge_index[0, i]), int(edge_index[1, i])
        if src not in adj_dict:
            adj_dict[src] = set()
        if dst not in adj_dict:
            adj_dict[dst] = set()
        adj_dict[src].add(dst)
        adj_dict[dst].add(src)
    
    processed = 0
    for anchor_idx, positive_idx in positive_pairs:
        if anchor_idx >= embeddings.shape[0] or positive_idx >= embeddings.shape[0]:
            continue
        
        try:
            # Get anchor embedding
            anchor_emb = embeddings[anchor_idx]
            
            # Compute similarity to all nodes
            similarities = torch.mm(embeddings, anchor_emb.unsqueeze(1)).squeeze(1)
            
            # Get anchor's neighbors (structural context)
            anchor_neighbors = adj_dict.get(anchor_idx, set())
            
            # Score candidates: combine similarity with structural distance
            candidates = []
            for candidate_idx in range(embeddings.shape[0]):
                if candidate_idx == anchor_idx:
                    continue
                if exclude_positives and candidate_idx == positive_idx:
                    continue
                
                # Similarity score
                sim_score = float(similarities[candidate_idx])
                
                # Structural distance: nodes with shared neighbors are more likely false negatives
                candidate_neighbors = adj_dict.get(candidate_idx, set())
                shared_neighbors = len(anchor_neighbors & candidate_neighbors)
                structural_penalty = shared_neighbors * 0.1  # Penalize shared neighbors
                
                # Combined score: high similarity but low structural overlap = good hard negative
                hardness_score = sim_score - structural_penalty
                
                candidates.append((candidate_idx, hardness_score))
            
            # Sort by hardness and select top-K
            candidates.sort(key=lambda x: x[1], reverse=True)
            hard_negs = [idx for idx, _ in candidates[:top_k]]
            
            if hard_negs:
                hard_negatives[(anchor_idx, positive_idx)] = hard_negs
        except Exception as e:
            logger.warning(f"Error computing hard negatives for pair ({anchor_idx}, {positive_idx}): {e}")
            continue
        
        processed += 1
        if processed % 1000 == 0:
            logger.info(f"  Processed {processed}/{len(positive_pairs)} pairs...")
    
    logger.info(f"  Computed hard negatives for {len(hard_negatives)} pairs")
    return hard_negatives


def create_contrastive_loss_with_hard_negatives(
    anchor_emb: torch.Tensor,
    positive_emb: torch.Tensor,
    negative_embs: torch.Tensor,
    temperature: float = 0.07,
) -> torch.Tensor:
    """
    Compute contrastive loss with hard negatives.
    
    Args:
        anchor_emb: Anchor embedding (dim,)
        positive_emb: Positive embedding (dim,)
        negative_embs: Hard negative embeddings (num_negatives, dim)
        temperature: Temperature for contrastive loss
    
    Returns:
        Contrastive loss scalar
    """
    # Normalize embeddings
    anchor_emb = anchor_emb / (anchor_emb.norm(dim=-1, keepdim=True) + 1e-8)
    positive_emb = positive_emb / (positive_emb.norm(dim=-1, keepdim=True) + 1e-8)
    negative_embs = negative_embs / (negative_embs.norm(dim=-1, keepdim=True) + 1e-8)
    
    # Positive similarity
    pos_sim = torch.dot(anchor_emb, positive_emb) / temperature
    
    # Negative similarities
    neg_sims = torch.mm(negative_embs, anchor_emb.unsqueeze(1)).squeeze(1) / temperature
    
    # InfoNCE loss
    logits = torch.cat([pos_sim.unsqueeze(0), neg_sims])
    labels = torch.zeros(1, dtype=torch.long, device=anchor_emb.device)
    
    loss = nn.functional.cross_entropy(logits.unsqueeze(0), labels)
    return loss


def apply_graph_augmentation(
    data: Data,
    edge_dropout: float = 0.2,
) -> Data:
    """
    Apply graph augmentation for contrastive learning.
    
    Based on SGL approach: Edge dropout creates augmented views.
    
    Args:
        data: Original graph data
        edge_dropout: Probability of dropping edges
    
    Returns:
        Augmented graph data
    """
    if not HAS_PYG:
        raise ImportError("PyTorch Geometric required")
    
    # Sample edges to keep
    num_edges = data.edge_index.shape[1]
    keep_mask = torch.rand(num_edges, device=data.edge_index.device) > edge_dropout
    
    # Create augmented edge index
    aug_edge_index = data.edge_index[:, keep_mask]
    
    # Create augmented data
    aug_data = Data(
        x=data.x,
        edge_index=aug_edge_index,
        edge_attr=data.edge_attr[keep_mask] if data.edge_attr is not None else None,
    )
    
    return aug_data

