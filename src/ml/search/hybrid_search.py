#!/usr/bin/env python3
"""
Hybrid card search combining Meilisearch (text) and Qdrant (vector).

Meilisearch provides fast text/keyword search.
Qdrant provides semantic vector search using embeddings.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

import numpy as np


logger = logging.getLogger("decksage.search")

try:
    from meilisearch import Client as MeilisearchClient  # type: ignore[import-not-found]
    from meilisearch.errors import MeilisearchApiError  # type: ignore[import-not-found]
except ImportError:
    MeilisearchClient = None
    MeilisearchApiError = Exception
    logger.warning("meilisearch not installed. Install with: uv add meilisearch")

try:
    from qdrant_client import QdrantClient  # type: ignore[import-not-found]
    from qdrant_client.http import models  # type: ignore[import-not-found]
    from qdrant_client.http.exceptions import (  # type: ignore[import-not-found]
        UnexpectedResponse,
    )
except ImportError:
    QdrantClient = None
    models = None
    UnexpectedResponse = Exception
    logger.warning("qdrant-client not installed. Install with: uv add qdrant-client")

try:
    from gensim.models import KeyedVectors  # type: ignore[import-not-found]
except ImportError:
    KeyedVectors = None


# ---------------------------------------------------------------------------
# MeiliSearch index configuration
# ---------------------------------------------------------------------------

# Synonyms keyed by game. Each maps a short/colloquial term to the canonical
# card name(s) so MeiliSearch treats them as equivalent during text search.
_SYNONYMS_BY_GAME: dict[str, dict[str, list[str]]] = {
    "magic": {
        "bolt": ["Lightning Bolt"],
        "wrath": ["Wrath of God"],
        "counterspell": ["Counter Spell"],
        "path": ["Path to Exile"],
        "snap": ["Snapcaster Mage"],
        "bob": ["Dark Confidant"],
        "lili": ["Liliana of the Veil"],
        "jace": ["Jace, the Mind Sculptor"],
        "sol ring": ["Sol Ring"],
        "stp": ["Swords to Plowshares"],
    },
    "pokemon": {
        "research": ["Professor's Research"],
        "boss": ["Boss's Orders"],
        "ultra ball": ["Ultra Ball"],
        "nest ball": ["Nest Ball"],
        "rare candy": ["Rare Candy"],
        "switch": ["Switch"],
    },
    "yugioh": {
        "ash": ["Ash Blossom & Joyous Spring"],
        "maxx c": ['Maxx "C"'],
        "nib": ["Nibiru, the Primal Being"],
        "imperm": ["Infinite Impermanence"],
        "called by": ["Called by the Grave"],
        "droplet": ["Forbidden Droplet"],
        "raigeki": ["Raigeki"],
        "hfd": ["Harpie's Feather Duster"],
    },
}


def build_meilisearch_settings(game: str | None = None) -> dict[str, Any]:
    """Build the MeiliSearch settings dict for a card index.

    Args:
        game: Optional game name. When provided, game-specific synonyms are
              included. Pass None for a generic configuration.

    Returns:
        A dict suitable for ``index.update_settings()``.
    """
    settings: dict[str, Any] = {
        # Ranking rules -- MeiliSearch defaults but explicit for clarity.
        # "words": presence of query terms
        # "typo": fewer typos ranked higher
        # "proximity": closer query terms ranked higher
        # "attribute": matches in higher-priority attributes ranked higher
        # "sort": user-requested sort order
        # "exactness": exact matches ranked higher
        "rankingRules": [
            "words",
            "typo",
            "proximity",
            "attribute",
            "sort",
            "exactness",
        ],
        # Attribute search priority (name > oracle_text > type_line > keywords).
        # Order matters: matches in earlier attributes score higher.
        "searchableAttributes": [
            "name",
            "text",
            "type_line",
            "keywords",
        ],
        # Attributes returned in search results.
        "displayedAttributes": ["*"],
        # Attributes available for filtering (e.g. ``filter="game = magic"``).
        "filterableAttributes": [
            "game",
            "colors",
            "type_line",
            "cmc",
            "rarity",
            "set_name",
        ],
        # Attributes available for sorting.
        "sortableAttributes": [
            "name",
            "cmc",
        ],
        # Typo tolerance: allow 1 typo for 5+ char words, 2 for 8+ chars.
        "typoTolerance": {
            "enabled": True,
            "minWordSizeForTypos": {
                "oneTypo": 4,
                "twoTypos": 8,
            },
        },
    }

    # Merge game-specific synonyms.
    synonyms: dict[str, list[str]] = {}
    if game and game in _SYNONYMS_BY_GAME:
        synonyms.update(_SYNONYMS_BY_GAME[game])
    settings["synonyms"] = synonyms

    return settings


@dataclass
class SearchResult:
    """Single search result with metadata."""

    card_name: str
    score: float
    source: str  # "meilisearch" or "qdrant" or "hybrid"
    metadata: dict[str, Any] | None = None


class HybridSearch:
    """
    Hybrid search combining Meilisearch (text) and Qdrant (vector).

    Meilisearch: Fast text/keyword search on card names and text.
    Qdrant: Semantic vector search using card embeddings.
    """

    def __init__(
        self,
        meilisearch_url: str | None = None,
        meilisearch_key: str | None = None,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
        embeddings: KeyedVectors | None = None,
        collection_name: str = "cards",
        index_name: str = "cards",
    ):
        """
        Initialize hybrid search.

        Args:
            meilisearch_url: Meilisearch server URL (default: http://localhost:7700)
            meilisearch_key: Meilisearch API key (optional)
            qdrant_url: Qdrant server URL (default: http://localhost:6333)
            qdrant_api_key: Qdrant API key (optional)
            embeddings: Gensim KeyedVectors for generating query embeddings
            collection_name: Qdrant collection name
            index_name: Meilisearch index name
        """
        self.collection_name = collection_name
        self.index_name = index_name
        self.embeddings = embeddings

        # Initialize Meilisearch
        if MeilisearchClient is None:
            logger.warning("Meilisearch not available")
            self.meilisearch = None
        else:
            meilisearch_url = meilisearch_url or os.getenv(
                "MEILISEARCH_URL", "http://localhost:7700"
            )
            # Normalize empty string to None so MeiliSearch skips auth
            resolved_key = meilisearch_key or os.getenv("MEILISEARCH_KEY") or None
            self.meilisearch = MeilisearchClient(
                url=meilisearch_url,
                api_key=resolved_key,
            )

        # Initialize Qdrant
        if QdrantClient is None:
            logger.warning("Qdrant not available")
            self.qdrant = None
        else:
            qdrant_url = qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
            self.qdrant = QdrantClient(
                url=qdrant_url,
                api_key=qdrant_api_key or os.getenv("QDRANT_API_KEY"),
            )

        # Initialize indices if needed
        if self.meilisearch:
            self._init_meilisearch()
        if self.qdrant:
            self._init_qdrant()

    def _init_meilisearch(self) -> None:
        """Initialize Meilisearch index."""
        if self.meilisearch is None:
            return

        try:
            index = self.meilisearch.index(self.index_name)
            index.fetch_info()
            logger.info(f"Meilisearch index '{self.index_name}' already exists")
        except MeilisearchApiError as e:
            if "index_not_found" in str(e).lower():
                # Create index
                self.meilisearch.create_index(
                    uid=self.index_name,
                    options={"primaryKey": "id"},
                )
                logger.info(f"Created Meilisearch index '{self.index_name}'")
            else:
                logger.error(f"Failed to initialize Meilisearch: {e}")
        except Exception as e:
            # Catches MeilisearchCommunicationError and other connection failures.
            # Degrade gracefully: disable Meilisearch so search falls back to vector-only.
            logger.warning(f"Meilisearch unavailable, disabling text search: {e}")
            self.meilisearch = None

    def _init_qdrant(self) -> None:
        """Initialize Qdrant collection."""
        if self.qdrant is None or models is None:
            return

        try:
            collections = self.qdrant.get_collections()
            collection_names = [c.name for c in collections.collections]
            if self.collection_name in collection_names:
                logger.info(f"Qdrant collection '{self.collection_name}' already exists")
                return
        except Exception as e:
            logger.warning(f"Qdrant unavailable, disabling vector search: {e}")
            self.qdrant = None
            return

        # We cannot safely create a collection without knowing the embedding dimensionality.
        # If embeddings are not provided, vector search is disabled anyway.
        if self.embeddings is None:
            logger.info(
                "Skipping Qdrant init for '%s' (no embeddings provided)",
                self.collection_name,
            )
            return
        vector_size = self.embeddings.vector_size

        try:
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info(
                f"Created Qdrant collection '{self.collection_name}' with size {vector_size}"
            )
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.error(f"Failed to create Qdrant collection: {e}")

    def configure_settings(self, game: str | None = None) -> bool:
        """Apply ranking rules, searchable/filterable/sortable attributes,
        synonyms, and typo tolerance to the Meilisearch index.

        Idempotent: compares current settings and skips if already configured.

        Returns True if settings were applied (or already matched), False on error.
        """
        if self.meilisearch is None:
            return False

        try:
            index = self.meilisearch.index(self.index_name)
            settings = build_meilisearch_settings(game)

            current = index.get_settings()
            # Compare the keys we care about
            needs_update = False
            for key in settings:
                if current.get(key) != settings[key]:
                    needs_update = True
                    break

            if not needs_update:
                logger.info("Meilisearch index '%s' settings already configured", self.index_name)
                return True

            index.update_settings(settings)
            logger.info(
                "Applied Meilisearch settings to index '%s' (game=%s)",
                self.index_name,
                game or "generic",
            )
            return True
        except Exception as e:
            logger.error(f"Failed to configure Meilisearch settings: {e}")
            return False

    def _card_id(self, card_name: str) -> str:
        """Generate consistent card ID from name."""
        return f"card-{hashlib.sha256(card_name.encode()).hexdigest()}"

    def index_card(
        self,
        card_name: str,
        card_text: str | None = None,
        type_line: str | None = None,
        image_url: str | None = None,
        ref_url: str | None = None,
        embedding: np.ndarray | None = None,
        visual_embedding: np.ndarray | None = None,
    ) -> None:
        """
        Index a card in both Meilisearch and Qdrant.

        Args:
            card_name: Card name
            card_text: Card text/oracle text
            type_line: Card type line
            image_url: Card image URL
            ref_url: Reference URL
            embedding: Pre-computed embedding vector (if None, will generate from embeddings)
            visual_embedding: Pre-computed visual embedding vector (optional)
        """
        card_id = self._card_id(card_name)

        # Index in Meilisearch
        if self.meilisearch:
            try:
                index = self.meilisearch.index(self.index_name)
                doc = {
                    "id": card_id,
                    "name": card_name,
                    "text": card_text or "",
                    "type_line": type_line or "",
                    "image_url": image_url or "",
                    "ref_url": ref_url or "",
                }
                index.add_documents([doc])
            except Exception as e:
                logger.error(f"Failed to index card in Meilisearch: {e}")

        # Index in Qdrant
        if self.qdrant and models is not None:
            try:
                # Get or generate embedding
                vector = embedding
                if vector is None and self.embeddings is not None:
                    if card_name in self.embeddings:
                        vector = self.embeddings[card_name]
                    else:
                        logger.warning(
                            f"Card '{card_name}' not in embeddings, skipping Qdrant index"
                        )
                        return

                if vector is not None:
                    # Convert to list if numpy array
                    if isinstance(vector, np.ndarray):
                        vector = vector.tolist()

                    payload = {
                        "name": card_name,
                        "text": card_text or "",
                        "type_line": type_line or "",
                        "image_url": image_url or "",
                        "ref_url": ref_url or "",
                    }

                    # Store visual embedding in payload if provided
                    # Note: Qdrant payload has size limits, so we store as list
                    if visual_embedding is not None:
                        if isinstance(visual_embedding, np.ndarray):
                            payload["visual_embedding"] = visual_embedding.tolist()
                        else:
                            payload["visual_embedding"] = visual_embedding

                    self.qdrant.upsert(
                        collection_name=self.collection_name,
                        points=[
                            models.PointStruct(
                                id=self._point_id(card_name),
                                vector=vector,
                                payload=payload,
                            )
                        ],
                    )
            except Exception as e:
                logger.error(f"Failed to index card in Qdrant: {e}")

    def _point_id(self, card_name: str) -> int:
        """Generate consistent integer point ID from card name."""
        # Use first 8 bytes of hash as integer
        hash_bytes = hashlib.sha256(card_name.encode()).digest()[:8]
        return int.from_bytes(hash_bytes, byteorder="big", signed=False)

    def batch_index_qdrant(
        self,
        card_metadata: dict[str, dict[str, Any]] | None = None,
        batch_size: int = 500,
    ) -> int:
        """Batch-upsert all embeddings into Qdrant. Idempotent: skips if
        the collection already has the expected number of points.

        Args:
            card_metadata: Optional {card_name: {oracle_text, type_line, ...}} for payloads.
            batch_size: Points per upsert call.

        Returns:
            Number of points indexed (0 if skipped).
        """
        if self.qdrant is None or models is None or self.embeddings is None:
            return 0

        try:
            info = self.qdrant.get_collection(self.collection_name)
            if info.points_count and info.points_count >= len(self.embeddings):
                logger.info(
                    "Qdrant collection '%s' already has %d points, skipping batch index",
                    self.collection_name,
                    info.points_count,
                )
                return 0
        except Exception:
            pass  # collection may not exist yet -- _init_qdrant handles creation

        points: list[models.PointStruct] = []
        for card_name in self.embeddings.index_to_key:
            vec = self.embeddings[card_name].tolist()
            payload: dict[str, Any] = {"name": card_name}
            if card_metadata and card_name in card_metadata:
                meta = card_metadata[card_name]
                payload["text"] = str(meta.get("oracle_text") or meta.get("text") or "")[:2000]
                payload["type_line"] = str(meta.get("type_line") or meta.get("type") or "")
                payload["image_url"] = str(meta.get("image_url") or "")
            points.append(
                models.PointStruct(
                    id=self._point_id(card_name),
                    vector=vec,
                    payload=payload,
                )
            )

            if len(points) >= batch_size:
                self.qdrant.upsert(collection_name=self.collection_name, points=points)
                points = []

        if points:
            self.qdrant.upsert(collection_name=self.collection_name, points=points)

        total = len(self.embeddings)
        logger.info(
            "Batch-indexed %d points into Qdrant collection '%s'", total, self.collection_name
        )
        return total

    def search(
        self,
        query: str,
        limit: int = 10,
        text_weight: float = 0.5,
        vector_weight: float = 0.5,
        filters: str | None = None,
    ) -> list[SearchResult]:
        """
        Hybrid search combining text and vector results.

        Args:
            query: Search query (text)
            limit: Maximum number of results
            text_weight: Weight for Meilisearch results (0-1)
            vector_weight: Weight for Qdrant results (0-1)
            filters: Optional MeiliSearch filter expression, e.g.
                     ``"game = magic AND colors = W"`` or ``"cmc <= 3"``.
                     Only applies to the MeiliSearch text search leg.

        Returns:
            List of SearchResult sorted by combined score
        """
        results: dict[str, SearchResult] = {}

        # Text search via Meilisearch
        if self.meilisearch and text_weight > 0:
            try:
                index = self.meilisearch.index(self.index_name)
                search_params: dict[str, Any] = {
                    "limit": limit * 2,
                    "showRankingScore": True,
                    "showRankingScoreDetails": True,
                }
                if filters:
                    search_params["filter"] = filters
                meilisearch_results = index.search(query, search_params)
                hits = meilisearch_results.get("hits", [])
                for hit in hits:
                    card_name = hit.get("name", "")
                    if not card_name:
                        continue
                    # Meilisearch returns _rankingScore or _score
                    raw_score = hit.get("_rankingScore") or hit.get("_score") or 0.0
                    score = float(raw_score) * text_weight
                    if card_name not in results:
                        results[card_name] = SearchResult(
                            card_name=card_name,
                            score=score,
                            source="meilisearch",
                            metadata={
                                "image_url": hit.get("image_url"),
                                "ref_url": hit.get("ref_url"),
                            },
                        )
                    else:
                        # Combine scores
                        results[card_name].score += score
                        results[card_name].source = "hybrid"
            except Exception as e:
                logger.error(f"Meilisearch query failed: {e}")

        # Vector search via Qdrant
        if self.qdrant and vector_weight > 0 and self.embeddings is not None:
            try:
                # Generate query embedding
                if query in self.embeddings:
                    query_vector = self.embeddings[query].tolist()
                else:
                    # Try to find similar card name
                    similar = self.embeddings.most_similar(query, topn=1)
                    if similar:
                        query_vector = self.embeddings[similar[0][0]].tolist()
                    else:
                        logger.warning(f"Could not generate embedding for query: {query}")
                        query_vector = None

                if query_vector:
                    qdrant_results = self.qdrant.search(
                        collection_name=self.collection_name,
                        query_vector=query_vector,
                        limit=limit * 2,
                    )

                    for result in qdrant_results:
                        payload = result.payload or {}
                        card_name = payload.get("name", "")
                        if not card_name:
                            continue
                        # Qdrant with Distance.COSINE returns similarity (higher = more similar, [0,1])
                        score = float(result.score) * vector_weight
                        if card_name not in results:
                            results[card_name] = SearchResult(
                                card_name=card_name,
                                score=score,
                                source="qdrant",
                                metadata={
                                    "image_url": payload.get("image_url"),
                                    "ref_url": payload.get("ref_url"),
                                },
                            )
                        else:
                            # Combine scores
                            results[card_name].score += score
                            results[card_name].source = "hybrid"
            except Exception as e:
                logger.error(f"Qdrant query failed: {e}")

        # Sort by combined score and return top results
        sorted_results = sorted(results.values(), key=lambda x: x.score, reverse=True)
        return sorted_results[:limit]

    def search_text_only(
        self, query: str, limit: int = 10, filters: str | None = None
    ) -> list[SearchResult]:
        """Text-only search using Meilisearch."""
        return self.search(query, limit=limit, text_weight=1.0, vector_weight=0.0, filters=filters)

    def search_vector_only(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Vector-only search using Qdrant."""
        return self.search(query, limit=limit, text_weight=0.0, vector_weight=1.0)
