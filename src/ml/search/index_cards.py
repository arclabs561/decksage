#!/usr/bin/env python3
"""
Index cards into Meilisearch and Qdrant for search.

Usage:
    python -m ml.search.index_cards --embeddings data/embeddings/model.wv
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from gensim.models import KeyedVectors

from .hybrid_search import HybridSearch

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger("decksage.search.index")


def index_from_embeddings(
    embeddings_path: str,
    meilisearch_url: str | None = None,
    qdrant_url: str | None = None,
    batch_size: int = 100,
) -> None:
    """
    Index all cards from embeddings file into Meilisearch and Qdrant.

    Args:
        embeddings_path: Path to gensim KeyedVectors file
        meilisearch_url: Meilisearch server URL
        qdrant_url: Qdrant server URL
        batch_size: Number of cards to index per batch
    """
    logger.info(f"Loading embeddings from {embeddings_path}")
    embeddings = KeyedVectors.load(embeddings_path)
    logger.info(f"Loaded {len(embeddings)} cards with {embeddings.vector_size} dimensions")

    # Initialize search client
    search = HybridSearch(
        meilisearch_url=meilisearch_url,
        qdrant_url=qdrant_url,
        embeddings=embeddings,
    )

    # Index all cards
    total = len(embeddings)
    indexed = 0

    logger.info("Starting indexing...")
    for i, card_name in enumerate(embeddings.index_to_key):
        try:
            embedding = embeddings[card_name]
            search.index_card(
                card_name=card_name,
                embedding=embedding,
            )
            indexed += 1

            if (i + 1) % batch_size == 0:
                logger.info(f"Indexed {indexed}/{total} cards ({100 * indexed / total:.1f}%)")
        except Exception as e:
            logger.error(f"Failed to index card '{card_name}': {e}")

    logger.info(f"Indexing complete: {indexed}/{total} cards indexed")


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Index cards for search")
    parser.add_argument(
        "--embeddings",
        required=True,
        help="Path to gensim KeyedVectors embeddings file",
    )
    parser.add_argument(
        "--meilisearch-url",
        default=None,
        help="Meilisearch server URL (default: http://localhost:7700)",
    )
    parser.add_argument(
        "--qdrant-url",
        default=None,
        help="Qdrant server URL (default: http://localhost:6333)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of cards to index per batch (default: 100)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging (already done via get_logger above, but set level if verbose)
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # Validate embeddings path
    emb_path = Path(args.embeddings)
    if not emb_path.exists():
        logger.error(f"Embeddings file not found: {emb_path}")
        return 1

    try:
        index_from_embeddings(
            embeddings_path=str(emb_path),
            meilisearch_url=args.meilisearch_url,
            qdrant_url=args.qdrant_url,
            batch_size=args.batch_size,
        )
        return 0
    except Exception as e:
        from ..utils.logging_config import log_exception
        log_exception(logger, "Indexing failed", e, include_context=True)
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())

