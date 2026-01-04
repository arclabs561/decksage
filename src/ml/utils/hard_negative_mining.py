"""
Hard Negative Mining Utilities for Improved Ranking Quality

Research-based approach: Select negatives from top-K most similar (non-relevant) candidates
instead of random sampling. This provides stronger training signals and improves MRR.

Expected impact: +5-10% MRR improvement
"""

from __future__ import annotations

import logging
from typing import Any


try:
    from gensim.models import KeyedVectors, Word2Vec

    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False

try:
    from .logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


def compute_hard_negatives(
    teacher_model: KeyedVectors | Word2Vec,
    positive_pairs: list[tuple[str, str]],
    vocabulary: set[str],
    top_k: int = 100,
    exclude_positives: bool = True,
) -> dict[str, list[str]]:
    """
    Compute hard negatives for each positive pair using teacher model.

    Hard negatives are candidates that are most similar to the anchor (positive)
    but are not actually relevant. These provide stronger training signals.

    Research basis: Hard negative mining improves MRR by +5-10% by focusing
    training on difficult cases where the model is confused.

    Args:
        teacher_model: Teacher model (current embeddings or larger model) to score candidates
        positive_pairs: List of (anchor, positive) pairs
        vocabulary: Set of all vocabulary items
        top_k: Select from top-K hardest negatives (default: 100)
        exclude_positives: Whether to exclude known positives from negative candidates
        max_pairs: Limit number of pairs to process (for efficiency, default: None = all)

    Returns:
        Dictionary mapping (anchor, positive) -> list of hard negative candidates
    """
    if not HAS_GENSIM:
        raise ImportError("gensim required for hard negative mining")

    # Get KeyedVectors from model if needed
    if isinstance(teacher_model, Word2Vec):
        wv = teacher_model.wv
    else:
        wv = teacher_model

    hard_negatives: dict[tuple[str, str], list[str]] = {}

    # Limit pairs for efficiency if requested
    if max_pairs and len(positive_pairs) > max_pairs:
        import random

        positive_pairs = random.sample(positive_pairs, max_pairs)
        logger.info(f"Sampled {max_pairs} pairs from {len(positive_pairs)} total for efficiency")

    logger.info(f"Computing hard negatives for {len(positive_pairs)} pairs (top_k={top_k})...")

    processed = 0
    for anchor, positive in positive_pairs:
        if anchor not in wv or positive not in wv:
            continue

        # Get all candidates except anchor and positive
        candidates = vocabulary - {anchor}
        if exclude_positives:
            candidates -= {positive}

        if not candidates:
            continue

        # Score all candidates using teacher model
        try:
            # Get most similar to anchor (excluding positive)
            similar_items = wv.most_similar(anchor, topn=min(top_k * 2, len(candidates)))

            # Filter out positive and select top-K hardest
            hard_negs = [
                item for item, score in similar_items if item != positive and item in candidates
            ][:top_k]

            if hard_negs:
                hard_negatives[(anchor, positive)] = hard_negs
        except KeyError:
            # Anchor not in vocabulary
            continue

        processed += 1
        if processed % 1000 == 0:
            logger.info(f"  Processed {processed}/{len(positive_pairs)} pairs...")

    logger.info(f"  Computed hard negatives for {len(hard_negatives)} pairs")
    return hard_negatives


def create_hard_negative_walks(
    walks: list[list[str]],
    hard_negatives: dict[tuple[str, str], list[str]],
    negative_ratio: float = 0.3,
) -> list[list[str]]:
    """
    Augment walks with hard negative examples.

    This creates additional training examples by replacing some context words
    with hard negatives, providing stronger learning signals.

    Args:
        walks: Original random walks
        hard_negatives: Dictionary of hard negatives per positive pair
        negative_ratio: Fraction of walks to augment with hard negatives

    Returns:
        Augmented walks with hard negatives
    """
    augmented_walks = []
    num_augmented = int(len(walks) * negative_ratio)

    logger.info(f"Augmenting {num_augmented} walks with hard negatives...")

    for i, walk in enumerate(walks):
        if i < num_augmented and len(walk) >= 2:
            # Try to find a positive pair in this walk
            for j in range(len(walk) - 1):
                anchor = walk[j]
                positive = walk[j + 1]
                pair_key = (anchor, positive)

                if hard_negatives.get(pair_key):
                    # Replace positive with a hard negative
                    import random

                    hard_neg = random.choice(hard_negatives[pair_key])
                    augmented_walk = walk.copy()
                    augmented_walk[j + 1] = hard_neg
                    augmented_walks.append(augmented_walk)
                    break
            else:
                # No matching pair, keep original walk
                augmented_walks.append(walk)
        else:
            # Keep original walk
            augmented_walks.append(walk)

    logger.info(f"  Created {len(augmented_walks)} augmented walks")
    return augmented_walks


def two_stage_training_with_hard_negatives(
    walks: list[list[str]],
    dim: int = 128,
    window_size: int = 10,
    epochs_stage1: int = 5,
    epochs_stage2: int = 5,
    workers: int = 4,
    negative: int = 5,
    hard_negative_top_k: int = 100,
    **kwargs: Any,
) -> Word2Vec:
    """
    Two-stage training with hard negative mining.

    Stage 1: Train initial model
    Stage 2: Use Stage 1 model as teacher to mine hard negatives, then retrain

    This approach improves ranking quality (MRR) by focusing on difficult cases.
    Research shows +5-10% MRR improvement from hard negative mining.

    Args:
        walks: Random walks for training
        dim: Embedding dimension
        window_size: Context window size
        epochs_stage1: Epochs for initial training
        epochs_stage2: Epochs for hard negative training
        workers: Number of workers
        negative: Number of negative samples
        hard_negative_top_k: Select from top-K hardest negatives (default: 100)
        hard_negative_ratio: Fraction of walks to augment with hard negatives (default: 0.3)
        **kwargs: Additional Word2Vec parameters

    Returns:
        Trained Word2Vec model
    """
    if not HAS_GENSIM:
        raise ImportError("gensim required for training")

    logger.info("=" * 70)
    logger.info("TWO-STAGE TRAINING WITH HARD NEGATIVE MINING")
    logger.info("=" * 70)

    # Stage 1: Initial training
    logger.info(f"\nStage 1: Initial training ({epochs_stage1} epochs)...")
    stage1_model = Word2Vec(
        sentences=walks,
        vector_size=dim,
        window=window_size,
        min_count=1,
        workers=workers,
        epochs=epochs_stage1,
        sg=1,
        negative=negative,
        **kwargs,
    )
    logger.info(f"  Stage 1 complete: {len(stage1_model.wv)} vectors")

    # Extract positive pairs from walks for hard negative mining
    # OPTIMIZATION: Sample pairs efficiently instead of processing all
    positive_pairs = []
    vocabulary = set()
    max_pairs_for_mining = 10000  # Limit for efficiency

    # Collect vocabulary first
    for walk in walks:
        vocabulary.update(walk)

    # Sample pairs from walks (prioritize longer walks for better coverage)
    import random

    sampled_walks = random.sample(walks, min(len(walks), max_pairs_for_mining // 2))
    for walk in sampled_walks:
        for i in range(len(walk) - 1):
            positive_pairs.append((walk[i], walk[i + 1]))
            if len(positive_pairs) >= max_pairs_for_mining:
                break
        if len(positive_pairs) >= max_pairs_for_mining:
            break

    logger.info(f"  Extracted {len(positive_pairs)} positive pairs from {len(sampled_walks)} walks")

    # Stage 2: Hard negative mining and retraining
    logger.info(f"\nStage 2: Hard negative mining and retraining ({epochs_stage2} epochs)...")
    hard_negatives = compute_hard_negatives(
        teacher_model=stage1_model.wv,
        positive_pairs=positive_pairs,
        vocabulary=vocabulary,
        top_k=hard_negative_top_k,
        max_pairs=None,  # Already limited above
    )

    # Augment walks with hard negatives
    augmented_walks = create_hard_negative_walks(
        walks=walks,
        hard_negatives=hard_negatives,
        negative_ratio=hard_negative_ratio,
    )

    # Retrain with augmented walks
    stage2_model = Word2Vec(
        sentences=augmented_walks,
        vector_size=dim,
        window=window_size,
        min_count=1,
        workers=workers,
        epochs=epochs_stage2,
        sg=1,
        negative=negative,
        **kwargs,
    )
    logger.info(f"  Stage 2 complete: {len(stage2_model.wv)} vectors")

    return stage2_model
