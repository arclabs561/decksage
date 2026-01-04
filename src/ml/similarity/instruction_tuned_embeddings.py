#!/usr/bin/env python3
"""
Instruction-Tuned Embeddings for Card Similarity

Uses E5-base-instruct for zero-shot card embeddings with task-specific instructions.
Handles new cards immediately without retraining.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    SentenceTransformer = None

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


class InstructionTunedCardEmbedder:
    """
    Instruction-tuned card embedder using E5-base-instruct.
    
    Supports task-specific instructions for different similarity tasks:
    - Functional substitution
    - Budget alternatives
    - Format-specific substitutes
    - Archetype-specific recommendations
    """
    
    DEFAULT_INSTRUCTIONS = {
        "substitution": "query: Find functional substitute for",
        "budget": "query: Find budget alternative to",
        "format": "query: Find substitute legal in format for",
        "archetype": "query: Find substitute for archetype",
        "similar": "query: Find similar cards to",
        # Downstream task instructions
        "completion": "query: Find cards to add to deck containing",
        "refinement": "query: Find cards to improve deck containing",
        "synergy": "query: Find cards that synergize with",
        "upgrade": "query: Find better versions of",
        "downgrade": "query: Find budget alternatives to",
        "quality": "query: Find cards that improve deck quality for",
    }
    
    def __init__(
        self,
        model_name: str = "intfloat/e5-base-v2",  # Options: e5-base-v2, intfloat/e5-mistral-7b-instruct, BAAI/bge-m3
        cache_dir: Path | str | None = None,
        default_instruction: str = "substitution",
    ):
        """
        Initialize instruction-tuned embedder.
        
        Args:
            model_name: HuggingFace model name (default: E5-base-instruct)
            cache_dir: Cache directory for model
            default_instruction: Default instruction type
        """
        if not HAS_SENTENCE_TRANSFORMERS:
            raise ImportError(
                "sentence-transformers required: pip install sentence-transformers"
            )
        
        self.model_name = model_name
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.default_instruction = default_instruction
        
        logger.info(f"Loading instruction-tuned model: {model_name}")
        self.model = SentenceTransformer(model_name, cache_folder=str(self.cache_dir) if self.cache_dir else None)
        logger.info("✓ Model loaded")
        
        # Memory cache for embeddings
        self._memory_cache: dict[str, np.ndarray] = {}
    
    def _card_to_text(self, card: dict[str, Any] | str) -> str:
        """
        Convert card dict to text string for embedding.
        
        Args:
            card: Card dict with 'name', 'type_line', 'oracle_text' or card name string
        
        Returns:
            Formatted text string
        """
        if isinstance(card, str):
            return card
        
        name = card.get("name", "")
        card_type = card.get("type_line", "") or card.get("type", "")
        oracle_text = card.get("oracle_text", "") or card.get("text", "")
        
        parts = [name]
        if card_type:
            parts.append(card_type)
        if oracle_text:
            parts.append(oracle_text)
        
        return ". ".join(parts)
    
    def embed_card(
        self,
        card: dict[str, Any] | str,
        instruction: str | None = None,
        instruction_type: str | None = None,
    ) -> np.ndarray:
        """
        Embed a card with optional instruction.
        
        Args:
            card: Card dict or name string
            instruction: Custom instruction text (overrides instruction_type)
            instruction_type: Predefined instruction type (e.g., "substitution", "budget")
        
        Returns:
            Embedding vector
        """
        # Get instruction
        if instruction is None:
            if instruction_type:
                instruction = self.DEFAULT_INSTRUCTIONS.get(
                    instruction_type,
                    self.DEFAULT_INSTRUCTIONS[self.default_instruction]
                )
            else:
                instruction = self.DEFAULT_INSTRUCTIONS[self.default_instruction]
        
        # Format card text
        card_text = self._card_to_text(card)
        
        # Format with instruction (E5 format)
        # E5 uses "query:" prefix for queries, "passage:" for documents
        formatted = f"{instruction} {card_text}"
        
        # Check cache
        cache_key = f"{instruction}:{card_text}"
        if cache_key in self._memory_cache:
            return self._memory_cache[cache_key]
        
        # Generate embedding
        embedding = self.model.encode(formatted, convert_to_numpy=True)
        
        # Cache it
        self._memory_cache[cache_key] = embedding
        
        return embedding
    
    def similarity(
        self,
        card1: dict[str, Any] | str,
        card2: dict[str, Any] | str,
        instruction: str | None = None,
        instruction_type: str | None = None,
    ) -> float:
        """
        Compute similarity between two cards.
        
        Args:
            card1: First card
            card2: Second card
            instruction: Custom instruction
            instruction_type: Predefined instruction type
        
        Returns:
            Cosine similarity score [0, 1]
        """
        emb1 = self.embed_card(card1, instruction=instruction, instruction_type=instruction_type)
        emb2 = self.embed_card(card2, instruction=instruction, instruction_type=instruction_type)
        
        # Cosine similarity
        dot_product = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        
        # Map from [-1, 1] to [0, 1]
        return float((similarity + 1.0) / 2.0)
    
    def most_similar(
        self,
        query_card: dict[str, Any] | str,
        candidate_cards: list[dict[str, Any] | str],
        topn: int = 10,
        instruction: str | None = None,
        instruction_type: str | None = None,
    ) -> list[tuple[str | dict[str, Any], float]]:
        """
        Find most similar cards from candidate list.
        
        Args:
            query_card: Query card
            candidate_cards: List of candidate cards
            topn: Number of results
            instruction: Custom instruction
            instruction_type: Predefined instruction type
        
        Returns:
            List of (card, similarity_score) tuples
        """
        query_emb = self.embed_card(query_card, instruction=instruction, instruction_type=instruction_type)
        
        similarities = []
        for candidate in candidate_cards:
            candidate_emb = self.embed_card(candidate, instruction=instruction, instruction_type=instruction_type)
            
            # Cosine similarity
            dot_product = np.dot(query_emb, candidate_emb)
            norm1 = np.linalg.norm(query_emb)
            norm2 = np.linalg.norm(candidate_emb)
            
            if norm1 > 0 and norm2 > 0:
                sim = dot_product / (norm1 * norm2)
                sim_normalized = (sim + 1.0) / 2.0  # Map to [0, 1]
                similarities.append((candidate, float(sim_normalized)))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:topn]

