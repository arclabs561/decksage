"""
Instruction-Tuned Embedding Improvements

Research-based improvements for instruction-tuned embeddings:
1. Dynamic hard negative mining
2. Synthetic data generation (LLM-based)
3. Multi-task learning
4. Large batch training optimization
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    from sentence_transformers import InputExample, SentenceTransformer
    from sentence_transformers.losses import MultipleNegativesRankingLoss
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

try:
    from .logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


def mine_dynamic_hard_negatives(
    model: SentenceTransformer,
    queries: list[str],
    corpus: list[str],
    positive_pairs: list[tuple[int, int]],
    top_k: int = 100,
    re_mine_threshold: float = 0.8,
) -> dict[int, list[int]]:
    """
    Dynamically mine hard negatives during training.
    
    Based on CONAN-Embedding approach: Re-mine hard negatives as model improves.
    
    Args:
        model: Current embedding model
        queries: List of query texts
        corpus: List of corpus texts
        positive_pairs: List of (query_idx, positive_idx) pairs
        top_k: Select from top-K hardest negatives
        re_mine_threshold: Re-mine when negative scores drop below this
    
    Returns:
        Dictionary mapping query_idx -> list of hard negative corpus indices
    """
    if not HAS_SENTENCE_TRANSFORMERS:
        raise ImportError("sentence-transformers required")
    
    logger.info(f"Mining dynamic hard negatives for {len(queries)} queries...")
    
    # Encode queries and corpus
    query_embeddings = model.encode(queries, show_progress_bar=True, convert_to_numpy=True)
    corpus_embeddings = model.encode(corpus, show_progress_bar=True, convert_to_numpy=True, batch_size=32)
    
    hard_negatives: dict[int, list[int]] = {}
    
    for query_idx, positive_idx in positive_pairs:
        if query_idx >= len(query_embeddings) or positive_idx >= len(corpus_embeddings):
            continue
        
        # Compute similarities to all corpus items
        query_emb = query_embeddings[query_idx]
        similarities = corpus_embeddings @ query_emb
        
        # Get positive score
        positive_score = similarities[positive_idx]
        
        # Select hard negatives: high similarity but not the positive
        candidates = []
        for corpus_idx, score in enumerate(similarities):
            if corpus_idx == positive_idx:
                continue
            
            # Hard negative: similar but not too similar (avoid false negatives)
            if score < positive_score * 0.95:  # TopK-PercPos approach
                candidates.append((corpus_idx, float(score)))
        
        # Sort by similarity (hardest = most similar)
        candidates.sort(key=lambda x: x[1], reverse=True)
        hard_negs = [idx for idx, _ in candidates[:top_k]]
        
        if hard_negs:
            hard_negatives[query_idx] = hard_negs
    
    logger.info(f"  Mined hard negatives for {len(hard_negatives)} queries")
    return hard_negatives


def generate_synthetic_training_data(
    base_queries: list[str],
    llm_prompt_template: str | None = None,
    num_augmentations: int = 3,
) -> list[tuple[str, str]]:
    """
    Generate synthetic training data using LLM.
    
    Based on E5-mistral and SPEED approaches: Use LLMs to generate diverse training examples.
    
    Args:
        base_queries: Base query texts
        llm_prompt_template: Template for LLM generation (optional)
        num_augmentations: Number of synthetic examples per query
    
    Returns:
        List of (query, passage) pairs
    """
    # TODO: Implement LLM-based synthetic data generation
    # For now, return empty list (placeholder)
    logger.warning("Synthetic data generation not yet implemented")
    return []


def create_multi_task_training_data(
    retrieval_pairs: list[tuple[str, str]],
    similarity_pairs: list[tuple[str, str]],
    clustering_groups: list[list[str]],
) -> list[InputExample]:
    """
    Create multi-task training data for instruction-tuned embeddings.
    
    Based on SFR-Embedding-Mistral approach: Combine diverse task types.
    
    Args:
        retrieval_pairs: (query, relevant_passage) pairs
        similarity_pairs: (text1, text2) similarity pairs
        clustering_groups: Groups of similar texts
    
    Returns:
        List of InputExample objects
    """
    if not HAS_SENTENCE_TRANSFORMERS:
        raise ImportError("sentence-transformers required")
    
    examples = []
    
    # Retrieval task examples
    for query, passage in retrieval_pairs:
        examples.append(InputExample(texts=[f"query: {query}", f"passage: {passage}"], label=1.0))
    
    # Similarity task examples
    for text1, text2 in similarity_pairs:
        examples.append(InputExample(texts=[f"Find similar texts to: {text1}", text2], label=1.0))
    
    # Clustering task examples (same cluster = positive)
    for group in clustering_groups:
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                examples.append(InputExample(texts=[group[i], group[j]], label=1.0))
    
    logger.info(f"Created {len(examples)} multi-task training examples")
    return examples

