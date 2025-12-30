#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
# ]
# ///
"""
Fallback labeling strategy for queries that failed LLM labeling.

Uses multiple approaches:
1. Co-occurrence similarity (Jaccard)
2. Embedding similarity (current embeddings)
3. Functional tag similarity
4. Manual templates for common patterns
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

try:
    from gensim.models import KeyedVectors
    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """Normalize card name for matching."""
    import re
    # Remove special characters, lowercase, strip
    normalized = re.sub(r'[^\w\s]', '', name.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def load_cooccurrence_data() -> dict[str, set[str]]:
    """Load co-occurrence data for Jaccard similarity."""
    pairs_path = Path("data/processed/pairs_large.csv")
    if not pairs_path.exists():
        logger.warning("pairs_large.csv not found, skipping co-occurrence")
        return {}
    
    import csv
    cooccurrence: dict[str, set[str]] = {}
    name_map: dict[str, str] = {}  # normalized -> original
    
    try:
        with open(pairs_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Try different column name formats
                card1 = row.get("NAME_1", row.get("card1", "")).strip()
                card2 = row.get("NAME_2", row.get("card2", "")).strip()
                
                if card1 and card2:
                    # Store both original and normalized
                    norm1 = normalize_name(card1)
                    norm2 = normalize_name(card2)
                    name_map[norm1] = card1
                    name_map[norm2] = card2
                    
                    # Use normalized names for matching
                    if norm1 not in cooccurrence:
                        cooccurrence[norm1] = set()
                    if norm2 not in cooccurrence:
                        cooccurrence[norm2] = set()
                    cooccurrence[norm1].add(norm2)
                    cooccurrence[norm2].add(norm1)
    except Exception as e:
        logger.error(f"Error loading co-occurrence: {e}")
        return {}
    
    logger.info(f"Loaded co-occurrence for {len(cooccurrence)} cards")
    return cooccurrence


def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    """Calculate Jaccard similarity."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def get_similar_by_cooccurrence(
    query: str,
    cooccurrence: dict[str, set[str]],
    top_k: int = 10
) -> list[tuple[str, float]]:
    """Get similar cards using co-occurrence (Jaccard similarity)."""
    query_norm = normalize_name(query)
    
    if query_norm not in cooccurrence:
        # Try fuzzy matching
        best_match = None
        best_score = 0.0
        for norm_name in cooccurrence.keys():
            # Simple substring match
            if query_norm in norm_name or norm_name in query_norm:
                score = len(set(query_norm.split()) & set(norm_name.split())) / len(set(query_norm.split()) | set(norm_name.split()))
                if score > best_score:
                    best_score = score
                    best_match = norm_name
        
        if best_match and best_score > 0.3:
            query_norm = best_match
            logger.debug(f"Matched '{query}' to '{best_match}' (score: {best_score:.2f})")
        else:
            return []
    
    query_neighbors = cooccurrence[query_norm]
    similarities = []
    
    for card_norm, neighbors in cooccurrence.items():
        if card_norm == query_norm:
            continue
        sim = jaccard_similarity(query_neighbors, neighbors)
        if sim > 0:
            similarities.append((card_norm, sim))
    
    similarities.sort(key=lambda x: x[1], reverse=True)
    return similarities[:top_k]


def get_similar_by_embeddings(
    query: str,
    embeddings: KeyedVectors | None,
    top_k: int = 10
) -> list[tuple[str, float]]:
    """Get similar cards using embeddings."""
    if not embeddings:
        return []
    
    # Try exact match first
    if query in embeddings:
        try:
            similar = embeddings.most_similar(query, topn=top_k)
            return [(card, float(score)) for card, score in similar]
        except Exception as e:
            logger.warning(f"Error getting embeddings for {query}: {e}")
            return []
    
    # Try normalized match
    query_norm = normalize_name(query)
    for key in embeddings.key_to_index.keys():
        if normalize_name(key) == query_norm:
            try:
                similar = embeddings.most_similar(key, topn=top_k)
                return [(card, float(score)) for card, score in similar]
            except Exception:
                pass
    
    return []


def load_embeddings() -> KeyedVectors | None:
    """Load best available embeddings."""
    if not HAS_GENSIM:
        return None
    
    embedding_paths = [
        "data/embeddings/node2vec_default.wv",
        "data/embeddings/node2vec_bfs.wv",
        "data/embeddings/node2vec_dfs.wv",
        "data/embeddings/deepwalk.wv",
    ]
    
    for path_str in embedding_paths:
        path = Path(path_str)
        if path.exists():
            try:
                logger.info(f"Loading embeddings from {path}")
                return KeyedVectors.load(str(path))
            except Exception as e:
                logger.warning(f"Failed to load {path}: {e}")
                continue
    
    return None


def categorize_similarity(score: float, method: str = "cooccurrence") -> str:
    """Categorize similarity score into relevance levels.
    
    Uses different thresholds based on method:
    - Co-occurrence: Higher thresholds (more reliable)
    - Embeddings: Lower thresholds (less reliable)
    """
    if method == "cooccurrence":
        # Co-occurrence is more reliable, use higher thresholds
        if score >= 0.2:
            return "highly_relevant"
        elif score >= 0.1:
            return "relevant"
        elif score >= 0.05:
            return "somewhat_relevant"
        elif score >= 0.02:
            return "marginally_relevant"
        else:
            return "irrelevant"
    else:
        # Embeddings are less reliable, use lower thresholds
        if score >= 0.4:
            return "highly_relevant"
        elif score >= 0.2:
            return "relevant"
        elif score >= 0.1:
            return "somewhat_relevant"
        elif score >= 0.05:
            return "marginally_relevant"
        else:
            return "irrelevant"


def generate_fallback_labels(
    query: str,
    cooccurrence: dict[str, set[str]],
    embeddings: KeyedVectors | None = None,  # DEPRECATED: Not used to avoid circular evaluation
    top_k: int = 20
) -> dict[str, list[str]]:
    """
    Generate labels using fallback strategies.
    
    NOTE: Embeddings are NOT used to avoid circular evaluation (embeddings
    evaluated on labels they generated). Only co-occurrence is used.
    """
    labels: dict[str, list[str]] = {
        "highly_relevant": [],
        "relevant": [],
        "somewhat_relevant": [],
        "marginally_relevant": [],
        "irrelevant": [],
    }
    
    # Strategy 1: Co-occurrence similarity (ONLY - no embeddings to avoid circular evaluation)
    cooccur_similar = get_similar_by_cooccurrence(query, cooccurrence, top_k=top_k)
    
    # NOTE: Embedding similarity removed to prevent circular evaluation
    # If embeddings are used to generate labels, then evaluating those same
    # embeddings on those labels creates a circular dependency.
    
    # Combine and deduplicate with method tracking
    all_similar: dict[str, tuple[float, str]] = {}  # (score, method)
    
    for card, score in cooccur_similar:
        # Weight co-occurrence (only method now)
        weighted_score = score * 1.0  # No weighting needed since it's the only method
        if card not in all_similar or weighted_score > all_similar[card][0]:
            all_similar[card] = (weighted_score, "cooccurrence")
    
    # Sort by score and categorize with method-aware thresholds
    sorted_similar = sorted(all_similar.items(), key=lambda x: x[1][0], reverse=True)
    
    for card, (score, method) in sorted_similar[:top_k]:
        category = categorize_similarity(score, method)
        labels[category].append(card)
    
    # Ensure we have some cards in each category (at least top 5)
    if not labels["highly_relevant"] and sorted_similar:
        labels["highly_relevant"] = [card for card, _ in sorted_similar[:3]]
    
    if not labels["relevant"] and len(sorted_similar) > 3:
        labels["relevant"] = [card for card, _ in sorted_similar[3:6]]
    
    return labels


def main() -> int:
    """Generate fallback labels for failed queries."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate fallback labels for failed queries")
    parser.add_argument("--input", type=str, required=True, help="Test set JSON")
    parser.add_argument("--output", type=str, required=True, help="Output test set JSON")
    parser.add_argument("--top-k", type=int, default=20, help="Top K similar cards to consider")
    
    args = parser.parse_args()
    
    # Load test set
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        return 1
    
    with open(input_path) as f:
        data = json.load(f)
    
    queries = data.get("queries", data)
    
    # Find queries that need labels
    queries_needing_labels = []
    for query_name, query_data in queries.items():
        if isinstance(query_data, dict):
            has_labels = (
                query_data.get("highly_relevant") or
                query_data.get("relevant") or
                query_data.get("somewhat_relevant")
            )
            if not has_labels:
                queries_needing_labels.append(query_name)
    
    if not queries_needing_labels:
        logger.info("✅ All queries already have labels!")
        return 0
    
    logger.info(f"Found {len(queries_needing_labels)} queries needing fallback labels")
    
    # Load similarity data
    logger.info("Loading co-occurrence data...")
    cooccurrence = load_cooccurrence_data()
    
    # NOTE: Embeddings NOT loaded to avoid circular evaluation
    # If we use embeddings to generate labels, then evaluate those same
    # embeddings on those labels, we get circular evaluation.
    # Only co-occurrence is used for fallback labeling.
    logger.info("Skipping embeddings (avoiding circular evaluation)...")
    embeddings = None
    
    # Generate fallback labels
    updated = queries.copy()
    processed = 0
    
    for query_name in queries_needing_labels:
        logger.info(f"Generating fallback labels for: {query_name}")
        labels = generate_fallback_labels(query_name, cooccurrence, embeddings, args.top_k)
        
        # Merge with existing data
        if query_name in updated:
            updated[query_name] = {**updated[query_name], **labels}
        else:
            updated[query_name] = labels
        
        processed += 1
        
        logger.info(f"  Generated: {len(labels['highly_relevant'])} highly relevant, "
                   f"{len(labels['relevant'])} relevant")
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump({
            "version": "labeled_fallback",
            "queries": updated,
            "metadata": {
                "processed": processed,
                "method": "fallback_cooccurrence_embeddings",
            },
        }, f, indent=2)
    
    logger.info(f"✅ Generated fallback labels for {processed} queries")
    logger.info(f"📁 Saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

