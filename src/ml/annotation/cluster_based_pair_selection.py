"""Cluster-based pair selection using EVōC for embedding clustering.

Uses EVōC to cluster card embeddings, then selects diverse pairs
from different clusters or high-similarity pairs from same clusters.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    import evoc
    HAS_EVOC = True
except ImportError:
    HAS_EVOC = False
    logger.warning("EVōC not available. Install with: pip install evoc")


def cluster_cards_with_evoc(
    card_names: list[str],
    embeddings: dict[str, np.ndarray] | np.ndarray,
    min_cluster_size: int = 5,
) -> dict[str, int] | None:
    """
    Cluster cards using EVōC based on their embeddings.
    
    Args:
        card_names: List of card names
        embeddings: Either dict mapping card names to embeddings, or array of embeddings
        min_cluster_size: Minimum size for clusters (EVōC parameter)
    
    Returns:
        Dict mapping card names to cluster labels, or None if EVōC unavailable
    """
    if not HAS_EVOC:
        logger.warning("EVōC not available - cannot cluster cards")
        return None
    
    # Convert embeddings to array format
    if isinstance(embeddings, dict):
        # Ensure all cards have embeddings
        valid_cards = [c for c in card_names if c in embeddings]
        if len(valid_cards) < len(card_names):
            logger.warning(f"Only {len(valid_cards)}/{len(card_names)} cards have embeddings")
        
        embedding_array = np.array([embeddings[c] for c in valid_cards])
        card_names = valid_cards
    else:
        embedding_array = embeddings
        if len(card_names) != len(embedding_array):
            raise ValueError(f"Card names ({len(card_names)}) and embeddings ({len(embedding_array)}) length mismatch")
    
    if len(embedding_array) == 0:
        logger.warning("No embeddings available for clustering")
        return None
    
    logger.info(f"Clustering {len(embedding_array)} cards with EVōC...")
    
    # Create EVōC clusterer (no parameters needed - EVōC handles this automatically)
    clusterer = evoc.EVoC()
    
    # Fit and predict
    cluster_labels = clusterer.fit_predict(embedding_array)
    
    # Map card names to cluster labels
    card_to_cluster = {card: int(label) for card, label in zip(card_names, cluster_labels)}
    
    # Log cluster statistics
    cluster_counts = defaultdict(int)
    for label in cluster_labels:
        cluster_counts[int(label)] += 1
    
    logger.info(f"Found {len(cluster_counts)} clusters:")
    for cluster_id, count in sorted(cluster_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        logger.info(f"  Cluster {cluster_id}: {count} cards")
    
    return card_to_cluster


def select_diverse_pairs_from_clusters(
    card_to_cluster: dict[str, int],
    n: int,
    cards: list[str] | None = None,
) -> list[tuple[str, str]]:
    """
    Select diverse pairs by sampling from different clusters.
    
    This ensures we get pairs that represent different types of card relationships.
    
    Args:
        card_to_cluster: Mapping of card names to cluster IDs
        n: Number of pairs to select
        cards: Optional list of cards to consider (if None, uses all cards in card_to_cluster)
    
    Returns:
        List of (card1, card2) tuples
    """
    if cards is None:
        cards = list(card_to_cluster.keys())
    
    # Group cards by cluster
    cluster_to_cards = defaultdict(list)
    for card in cards:
        if card in card_to_cluster:
            cluster_id = card_to_cluster[card]
            cluster_to_cards[cluster_id].append(card)
    
    # Select pairs from different clusters
    pairs = []
    clusters = list(cluster_to_cards.keys())
    
    if len(clusters) < 2:
        # Not enough clusters - fall back to random selection
        import random
        for _ in range(n):
            card1 = random.choice(cards)
            card2 = random.choice(cards)
            if card1 != card2:
                pairs.append((card1, card2))
        return pairs
    
    # Try to select pairs from different clusters
    import random
    attempts = 0
    max_attempts = n * 10
    
    while len(pairs) < n and attempts < max_attempts:
        attempts += 1
        
        # Select two different clusters
        cluster1, cluster2 = random.sample(clusters, 2)
        
        # Select one card from each cluster
        if cluster_to_cards[cluster1] and cluster_to_cards[cluster2]:
            card1 = random.choice(cluster_to_cards[cluster1])
            card2 = random.choice(cluster_to_cards[cluster2])
            
            if card1 != card2:
                pairs.append((card1, card2))
    
    # If we didn't get enough pairs, fill with random
    while len(pairs) < n:
        card1 = random.choice(cards)
        card2 = random.choice(cards)
        if card1 != card2 and (card1, card2) not in pairs:
            pairs.append((card1, card2))
    
    return pairs[:n]


def select_high_similarity_pairs_from_clusters(
    card_to_cluster: dict[str, int],
    n: int,
    cards: list[str] | None = None,
) -> list[tuple[str, str]]:
    """
    Select high-similarity pairs by sampling from the same cluster.
    
    Cards in the same cluster should have high embedding similarity,
    which should translate to high similarity scores.
    
    Args:
        card_to_cluster: Mapping of card names to cluster IDs
        n: Number of pairs to select
        cards: Optional list of cards to consider
    
    Returns:
        List of (card1, card2) tuples from same clusters
    """
    if cards is None:
        cards = list(card_to_cluster.keys())
    
    # Group cards by cluster
    cluster_to_cards = defaultdict(list)
    for card in cards:
        if card in card_to_cluster:
            cluster_id = card_to_cluster[card]
            cluster_to_cards[cluster_id].append(card)
    
    # Select pairs from same clusters
    pairs = []
    import random
    
    # Get clusters with at least 2 cards
    valid_clusters = [cid for cid, card_list in cluster_to_cards.items() if len(card_list) >= 2]
    
    if not valid_clusters:
        # No clusters with multiple cards - fall back to random
        for _ in range(n):
            card1 = random.choice(cards)
            card2 = random.choice(cards)
            if card1 != card2:
                pairs.append((card1, card2))
        return pairs
    
    # Sample pairs from same clusters
    attempts = 0
    max_attempts = n * 10
    
    while len(pairs) < n and attempts < max_attempts:
        attempts += 1
        
        # Select a cluster with multiple cards
        cluster_id = random.choice(valid_clusters)
        cluster_cards = cluster_to_cards[cluster_id]
        
        # Select two different cards from this cluster
        if len(cluster_cards) >= 2:
            card1, card2 = random.sample(cluster_cards, 2)
            if (card1, card2) not in pairs and (card2, card1) not in pairs:
                pairs.append((card1, card2))
    
    # If we didn't get enough pairs, fill with random
    while len(pairs) < n:
        card1 = random.choice(cards)
        card2 = random.choice(cards)
        if card1 != card2 and (card1, card2) not in pairs:
            pairs.append((card1, card2))
    
    return pairs[:n]


def select_mixed_pairs_from_clusters(
    card_to_cluster: dict[str, int],
    n: int,
    high_similarity_ratio: float = 0.33,
    cards: list[str] | None = None,
) -> list[tuple[str, str]]:
    """
    Select a mix of pairs: some from same clusters (high similarity),
    some from different clusters (diverse).
    
    Args:
        card_to_cluster: Mapping of card names to cluster IDs
        n: Total number of pairs to select
        high_similarity_ratio: Fraction of pairs to select from same clusters
        cards: Optional list of cards to consider
    
    Returns:
        List of (card1, card2) tuples
    """
    n_high = int(n * high_similarity_ratio)
    n_diverse = n - n_high
    
    high_pairs = select_high_similarity_pairs_from_clusters(card_to_cluster, n_high, cards)
    diverse_pairs = select_diverse_pairs_from_clusters(card_to_cluster, n_diverse, cards)
    
    return high_pairs + diverse_pairs

