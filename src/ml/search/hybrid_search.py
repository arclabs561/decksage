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
from pydantic import BaseModel

logger = logging.getLogger("decksage.search")

try:
    from meilisearch import Client as MeilisearchClient
    from meilisearch.errors import MeilisearchApiError
except ImportError:
    MeilisearchClient = None
    MeilisearchApiError = Exception
    logger.warning("meilisearch not installed. Install with: uv add meilisearch")

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
    from qdrant_client.http.exceptions import UnexpectedResponse
except ImportError:
    QdrantClient = None
    models = None
    UnexpectedResponse = Exception
    logger.warning("qdrant-client not installed. Install with: uv add qdrant-client")

try:
    from gensim.models import KeyedVectors
except ImportError:
    KeyedVectors = None


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
            meilisearch_url = meilisearch_url or os.getenv("MEILISEARCH_URL", "http://localhost:7700")
            self.meilisearch = MeilisearchClient(
                url=meilisearch_url,
                api_key=meilisearch_key or os.getenv("MEILISEARCH_KEY"),
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

                # Configure searchable attributes
                index = self.meilisearch.index(self.index_name)
                index.update_searchable_attributes(["name", "text", "type_line"])
                index.update_displayed_attributes(["id", "name", "image_url", "ref_url"])
            else:
                logger.error(f"Failed to initialize Meilisearch: {e}")

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
            logger.warning(f"Failed to check Qdrant collections: {e}")

        # Determine vector size from embeddings if available
        vector_size = 128  # default
        if self.embeddings is not None:
            vector_size = self.embeddings.vector_size

        try:
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info(f"Created Qdrant collection '{self.collection_name}' with size {vector_size}")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.error(f"Failed to create Qdrant collection: {e}")

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
                        logger.warning(f"Card '{card_name}' not in embeddings, skipping Qdrant index")
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

    def search(
        self,
        query: str,
        limit: int = 10,
        text_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> list[SearchResult]:
        """
        Hybrid search combining text and vector results.

        Args:
            query: Search query (text)
            limit: Maximum number of results
            text_weight: Weight for Meilisearch results (0-1)
            vector_weight: Weight for Qdrant results (0-1)

        Returns:
            List of SearchResult sorted by combined score
        """
        results: dict[str, SearchResult] = {}

        # Text search via Meilisearch
        if self.meilisearch and text_weight > 0:
            try:
                index = self.meilisearch.index(self.index_name)
                meilisearch_results = index.search(query, {"limit": limit * 2})
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
                        # Qdrant returns distance (lower is better), convert to similarity
                        # For cosine distance: similarity = 1 - distance
                        distance = float(result.score)
                        score = (1.0 - distance) * vector_weight
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

    def search_text_only(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Text-only search using Meilisearch."""
        return self.search(query, limit=limit, text_weight=1.0, vector_weight=0.0)

    def search_vector_only(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Vector-only search using Qdrant."""
        return self.search(query, limit=limit, text_weight=0.0, vector_weight=1.0)

