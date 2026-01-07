"""Game knowledge base with RAG retrieval for dynamic prompt injection."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .models import GameKnowledge, KnowledgeChunk

logger = logging.getLogger(__name__)

# Set up logging if not configured
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.WARNING)  # Only show warnings/errors by default
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)


def _get_default_knowledge_dir() -> Path:
    """Get default knowledge directory without importing PATHS."""
    # Try to find project root
    env_root = os.getenv("DECKSAGE_ROOT")
    if env_root:
        return Path(env_root) / "data" / "game_knowledge"
    
    # Try relative to this file
    current = Path(__file__).parent.parent.parent.parent
    markers = ["pyproject.toml", "runctl.toml", ".git"]
    if any((current / m).exists() for m in markers):
        return current / "data" / "game_knowledge"
    
    # Fallback
    return current / "data" / "game_knowledge"


class GameKnowledgeBase:
    """Manages game-specific knowledge for prompt injection."""

    def __init__(self, knowledge_dir: Path | None = None):
        """
        Initialize knowledge base.

        Args:
            knowledge_dir: Directory containing game knowledge JSON files
        """
        self.knowledge_dir = knowledge_dir or _get_default_knowledge_dir()
        self.knowledge_dir.mkdir(exist_ok=True, parents=True)
        self._knowledge_cache: dict[str, GameKnowledge] = {}
        self._chunks_cache: dict[str, list[KnowledgeChunk]] = {}

    def load_game_knowledge(self, game: str) -> GameKnowledge | None:
        """
        Load knowledge for a specific game.

        Args:
            game: Game name (magic, pokemon, yugioh)

        Returns:
            GameKnowledge or None if not found
        """
        if game in self._knowledge_cache:
            return self._knowledge_cache[game]

        knowledge_file = self.knowledge_dir / f"{game}.json"
        if not knowledge_file.exists():
            logger.warning(f"Knowledge file not found: {knowledge_file}")
            return None

        try:
            with open(knowledge_file, encoding="utf-8") as f:
                data = json.load(f)
            knowledge = GameKnowledge(**data)
            self._knowledge_cache[game] = knowledge
            logger.debug(f"Loaded knowledge for {game}: {len(knowledge.archetypes)} archetypes, {len(knowledge.formats)} formats")
            return knowledge
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {knowledge_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load knowledge for {game}: {e}", exc_info=True)
            return None

    def _chunk_knowledge(self, knowledge: GameKnowledge) -> list[KnowledgeChunk]:
        """Convert knowledge into searchable chunks."""
        chunks: list[KnowledgeChunk] = []

        # Mechanics chunk
        card_types_str = ', '.join(knowledge.mechanics.card_types) if knowledge.mechanics.card_types else 'None'
        keywords_str = ', '.join(knowledge.mechanics.keywords) if knowledge.mechanics.keywords else 'None'
        
        mechanics_text = f"""
Game: {knowledge.game}
Mechanics:
- Resource System: {knowledge.mechanics.mana_system or 'N/A'}
- Color/Attribute System: {knowledge.mechanics.color_system or 'N/A'}
- Card Types: {card_types_str}
- Keywords: {keywords_str}
- Special Rules: {knowledge.mechanics.special_rules or 'N/A'}
"""
        chunks.append(
            KnowledgeChunk(
                id=f"{knowledge.game}_mechanics",
                game=knowledge.game,
                category="mechanics",
                content=mechanics_text.strip(),
                tags=["mechanics", "rules"],
            )
        )

        # Archetype chunks
        for arch in knowledge.archetypes:
            # Safely format lists
            core_cards_str = ', '.join(arch.core_cards[:10]) if arch.core_cards else 'None'
            flex_slots_str = ', '.join(arch.flex_slots[:5]) if arch.flex_slots else 'None'
            key_features_str = ', '.join(arch.key_features) if arch.key_features else 'None'
            
            arch_text = f"""
Archetype: {arch.name}
Description: {arch.description}
Strategy: {arch.strategy}
Core Cards: {core_cards_str}
Flex Slots: {flex_slots_str}
Key Features: {key_features_str}
"""
            # Sanitize ID (remove special chars)
            arch_id = arch.name.lower().replace(' ', '_').replace('/', '_').replace('-', '_')
            chunks.append(
                KnowledgeChunk(
                    id=f"{knowledge.game}_archetype_{arch_id}",
                    game=knowledge.game,
                    category="archetype",
                    content=arch_text.strip(),
                    metadata={"archetype_name": arch.name},
                    tags=["archetype", arch.name.lower()],
                )
            )

        # Format chunks
        for fmt in knowledge.formats:
            # Safely format lists
            legal_sets_str = ', '.join(fmt.legal_sets[:10]) if fmt.legal_sets else 'N/A'
            ban_list_str = ', '.join(fmt.ban_list[:10]) if fmt.ban_list else 'None'
            
            fmt_text = f"""
Format: {fmt.name}
Legal Sets: {legal_sets_str}
Rotation: {fmt.rotation_schedule or 'N/A'}
Banned Cards: {ban_list_str}
Meta Context: {fmt.meta_context or 'N/A'}
"""
            chunks.append(
                KnowledgeChunk(
                    id=f"{knowledge.game}_format_{fmt.name.lower().replace(' ', '_').replace('/', '_')}",
                    game=knowledge.game,
                    category="format",
                    content=fmt_text.strip(),
                    metadata={"format_name": fmt.name},
                    tags=["format", fmt.name.lower()],
                )
            )

        return chunks

    def retrieve_relevant_knowledge(
        self,
        game: str,
        query: str,
        format: str | None = None,
        archetype: str | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """
        Retrieve relevant knowledge chunks for prompt injection.

        Args:
            game: Game name
            query: Query text (card names, etc.)
            format: Format name (optional filter)
            archetype: Archetype name (optional filter)
            top_k: Number of chunks to return

        Returns:
            Dictionary with retrieved knowledge sections
        """
        if not game or not isinstance(game, str):
            logger.warning(f"Invalid game parameter: {game}")
            return {"mechanics": "", "archetypes": "", "formats": "", "examples": []}
        
        if not query or not isinstance(query, str):
            query = "general"
        
        knowledge = self.load_game_knowledge(game)
        if not knowledge:
            logger.debug(f"No knowledge loaded for {game}")
            return {"mechanics": "", "archetypes": "", "formats": "", "examples": []}

        # Get chunks (cache them)
        if game not in self._chunks_cache:
            self._chunks_cache[game] = self._chunk_knowledge(knowledge)

        chunks = self._chunks_cache[game]

        # Simple keyword-based filtering (can be enhanced with embeddings)
        query_lower = query.lower().strip()
        if not query_lower:
            query_lower = "general"
        
        scored_chunks: list[tuple[KnowledgeChunk, float]] = []

        for chunk in chunks:
            score = 0.0

            # Category priority
            if chunk.category == "mechanics":
                score += 1.0  # Always include mechanics
            elif chunk.category == "archetype" and archetype:
                arch_name = chunk.metadata.get("archetype_name", "").lower()
                if archetype.lower() in arch_name or arch_name in archetype.lower():
                    score += 10.0
                # Also boost if query mentions archetype
                if archetype.lower() in query_lower:
                    score += 5.0
            elif chunk.category == "format" and format:
                fmt_name = chunk.metadata.get("format_name", "").lower()
                if format.lower() in fmt_name or fmt_name in format.lower():
                    score += 10.0
                # Also boost if query mentions format
                if format.lower() in query_lower:
                    score += 5.0

            # Keyword matching (more sophisticated)
            content_lower = chunk.content.lower()
            query_words = [w for w in query_lower.split() if len(w) > 2]  # Skip short words
            for word in query_words:
                if word in content_lower:
                    score += 1.0
                # Boost for exact matches
                if f" {word} " in f" {content_lower} ":
                    score += 0.5

            scored_chunks.append((chunk, score))

        # Sort by score and take top_k
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        selected_chunks = [chunk for chunk, _ in scored_chunks[:top_k]]

        # Organize by category (ensure mechanics always included)
        result: dict[str, Any] = {
            "mechanics": "",
            "archetypes": [],
            "formats": [],
            "examples": knowledge.examples[:3] if knowledge.examples else [],  # Top 3 examples
        }

        # Always include mechanics if available
        mechanics_chunk = next((c for c in chunks if c.category == "mechanics"), None)
        if mechanics_chunk:
            result["mechanics"] = mechanics_chunk.content

        # Add selected chunks by category
        for chunk in selected_chunks:
            if chunk.category == "archetype":
                result["archetypes"].append(chunk.content)
            elif chunk.category == "format":
                result["formats"].append(chunk.content)

        # Format as strings (remove duplicates)
        seen_archetypes = set()
        unique_archetypes = []
        for arch in result["archetypes"]:
            if arch not in seen_archetypes:
                seen_archetypes.add(arch)
                unique_archetypes.append(arch)
        result["archetypes"] = "\n\n".join(unique_archetypes)

        seen_formats = set()
        unique_formats = []
        for fmt in result["formats"]:
            if fmt not in seen_formats:
                seen_formats.add(fmt)
                unique_formats.append(fmt)
        result["formats"] = "\n\n".join(unique_formats)

        return result


def retrieve_game_knowledge(
    game: str,
    query: str,
    format: str | None = None,
    archetype: str | None = None,
) -> dict[str, Any]:
    """
    Convenience function to retrieve game knowledge.

    Args:
        game: Game name
        query: Query text
        format: Format name (optional)
        archetype: Archetype name (optional)

    Returns:
        Dictionary with knowledge sections (mechanics, archetypes, formats, examples)
        
    Example:
        >>> knowledge = retrieve_game_knowledge("magic", "Lightning Bolt", format="Modern")
        >>> print(knowledge["mechanics"][:100])
    """
    if not game:
        logger.warning("Empty game parameter provided")
        return {"mechanics": "", "archetypes": "", "formats": "", "examples": []}
    
    kb = GameKnowledgeBase()
    return kb.retrieve_relevant_knowledge(game, query, format, archetype)

