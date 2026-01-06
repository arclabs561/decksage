#!/usr/bin/env python3
"""
Index cards into Meilisearch and Qdrant on API startup.

This script should be run as part of the Docker container startup
to ensure search indices are populated before serving requests.

Usage:
    python scripts/docker/index_cards_on_startup.py \
        --embeddings /app/data/embeddings/model.wv \
        --meilisearch-url http://meilisearch:7700 \
        --qdrant-url http://qdrant:6333
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

try:
    from gensim.models import KeyedVectors
    from ml.search.index_cards import index_from_embeddings
except ImportError as e:
    print(f"Error: Missing dependencies: {e}")
    print("Install with: uv sync --extra api")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    """Index cards on startup."""
    parser = argparse.ArgumentParser(description="Index cards into search services")
    parser.add_argument(
        "--embeddings",
        type=str,
        required=True,
        help="Path to embeddings file (.wv)",
    )
    parser.add_argument(
        "--meilisearch-url",
        type=str,
        default=os.getenv("MEILISEARCH_URL", "http://localhost:7700"),
        help="Meilisearch server URL",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=os.getenv("QDRANT_URL", "http://localhost:6333"),
        help="Qdrant server URL",
    )
    parser.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="Skip indexing if index already has documents",
    )

    args = parser.parse_args()

    embeddings_path = Path(args.embeddings)
    if not embeddings_path.exists():
        logger.error(f"Embeddings file not found: {embeddings_path}")
        return 1

    # Check if indexing should be skipped
    if args.skip_if_exists:
        try:
            from meilisearch import Client as MeilisearchClient

            client = MeilisearchClient(url=args.meilisearch_url)
            index = client.index("cards")
            stats = index.get_stats()
            if stats.get("numberOfDocuments", 0) > 0:
                logger.info(
                    f"Index already has {stats['numberOfDocuments']} documents. Skipping."
                )
                return 0
        except Exception as e:
            logger.warning(f"Could not check index status: {e}")

    logger.info(f"Indexing cards from {embeddings_path}")
    logger.info(f"Meilisearch: {args.meilisearch_url}")
    logger.info(f"Qdrant: {args.qdrant_url}")

    try:
        index_from_embeddings(
            embeddings_path=str(embeddings_path),
            meilisearch_url=args.meilisearch_url,
            qdrant_url=args.qdrant_url,
            batch_size=100,
        )
        logger.info("Indexing complete!")
        return 0
    except Exception as e:
        logger.error(f"Indexing failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

