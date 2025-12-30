#!/usr/bin/env python3
"""
Card text embeddings using sentence transformers.

Provides semantic similarity based on card Oracle text, names, and types.
This is a primary signal for card similarity (expected 30-40% weight in fusion).
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("decksage.text_embeddings")

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None
    logger.warning(
        "sentence-transformers not installed. Install with: uv add sentence-transformers"
    )


class CardTextEmbedder:
    """
    Embed cards using their text content (name, type, Oracle text).
    
    Uses sentence-transformers for efficient semantic embeddings.
    Caches embeddings to disk for performance.
    """
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache_dir: Path | str | None = None,
    ):
        """
        Initialize text embedder.
        
        Args:
            model_name: Sentence transformer model name
            cache_dir: Directory to cache embeddings (default: .cache/text_embeddings/)
        """
        if SentenceTransformer is None:
            raise ImportError(
                "sentence-transformers required. Install with: uv add sentence-transformers"
            )
        
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self._memory_cache: dict[str, np.ndarray] = {}
        
        # Setup cache directory
        if cache_dir is None:
            cache_dir = Path(".cache") / "text_embeddings"
        else:
            cache_dir = Path(cache_dir)
        
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / f"{model_name.replace('/', '_')}.pkl"
        
        # Load existing cache
        self._load_cache()
    
    def _load_cache(self) -> None:
        """Load embeddings from disk cache."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "rb") as f:
                    self._memory_cache = pickle.load(f)
                logger.info(f"Loaded {len(self._memory_cache)} cached embeddings")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                self._memory_cache = {}
    
    def _save_cache(self) -> None:
        """Save embeddings to disk cache."""
        try:
            with open(self.cache_file, "wb") as f:
                pickle.dump(self._memory_cache, f)
            logger.debug(f"Saved {len(self._memory_cache)} embeddings to cache")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def _card_to_text(self, card: dict[str, Any]) -> str:
        """
        Convert card dict to text string for embedding.
        
        Combines: name, type_line, oracle_text
        """
        name = card.get("name", "")
        card_type = card.get("type_line", "") or card.get("type", "")
        oracle_text = card.get("oracle_text", "") or card.get("text", "")
        
        # Combine into single text
        parts = [name]
        if card_type:
            parts.append(card_type)
        if oracle_text:
            parts.append(oracle_text)
        
        return ". ".join(parts)
    
    def embed_card(self, card: dict[str, Any] | str) -> np.ndarray:
        """
        Embed a card using its text content.
        
        Args:
            card: Card dict with 'name', 'type_line', 'oracle_text' keys,
                  or card name string (will need card resolver)
        
        Returns:
            Embedding vector (numpy array)
        """
        # Handle string input (card name)
        if isinstance(card, str):
            # For now, just use the name
            # TODO: Resolve to full card dict if needed
            text = card
        else:
            text = self._card_to_text(card)
        
        # Check cache first
        if text in self._memory_cache:
            return self._memory_cache[text]
        
        # Generate embedding
        embedding = self.model.encode(text, convert_to_numpy=True)
        
        # Cache it
        self._memory_cache[text] = embedding
        
        return embedding
    
    def similarity(
        self,
        card1: dict[str, Any] | str,
        card2: dict[str, Any] | str,
    ) -> float:
        """
        Compute cosine similarity between two card embeddings.
        
        Args:
            card1: First card (dict or name string)
            card2: Second card (dict or name string)
        
        Returns:
            Cosine similarity score in [0, 1]
        """
        emb1 = self.embed_card(card1)
        emb2 = self.embed_card(card2)
        
        # Cosine similarity
        dot_product = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        
        # Ensure in [0, 1] (should be, but clamp for safety)
        return max(0.0, min(1.0, similarity))
    
    def embed_batch(self, cards: list[dict[str, Any] | str]) -> np.ndarray:
        """
        Embed multiple cards efficiently (batch processing).
        
        Args:
            cards: List of card dicts or names
        
        Returns:
            Array of embeddings (n_samples, embedding_dim)
        """
        texts = []
        for card in cards:
            if isinstance(card, str):
                texts.append(card)
            else:
                texts.append(self._card_to_text(card))
        
        # Batch encode (more efficient)
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        
        # Update cache
        for text, emb in zip(texts, embeddings):
            self._memory_cache[text] = emb
        
        return embeddings
    
    def save_cache(self) -> None:
        """Explicitly save cache to disk."""
        self._save_cache()
    
    def __del__(self):
        """Save cache on destruction."""
        try:
            self._save_cache()
        except Exception:
            pass


# Global instance (lazy initialization)
_global_embedder: CardTextEmbedder | None = None


def get_text_embedder(
    model_name: str = "all-MiniLM-L6-v2",
    cache_dir: Path | str | None = None,
) -> CardTextEmbedder:
    """
    Get or create global text embedder instance.
    
    Args:
        model_name: Model to use
        cache_dir: Cache directory
    
    Returns:
        CardTextEmbedder instance
    """
    global _global_embedder
    
    if _global_embedder is None:
        _global_embedder = CardTextEmbedder(model_name=model_name, cache_dir=cache_dir)
    
    return _global_embedder


__all__ = ["CardTextEmbedder", "get_text_embedder"]







