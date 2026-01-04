#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# ]
# ///
"""
Fix labeling issue - complete labels for remaining queries.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    """Fix incomplete labeling."""
    expanded_path = Path("experiments/test_set_expanded_magic.json")
    labeled_path = Path("experiments/test_set_labeled_magic.json")

    # Load both files
    with open(expanded_path) as f:
        expanded = json.load(f)

    with open(labeled_path) as f:
        labeled = json.load(f)

    expanded_queries = expanded.get("queries", expanded)
    labeled_queries = labeled.get("queries", labeled)

    logger.info(f"Expanded: {len(expanded_queries)} queries")
    logger.info(f"Labeled: {len(labeled_queries)} queries")

    # Find queries missing labels
    missing = []
    for query_name, query_data in expanded_queries.items():
        if query_name not in labeled_queries:
            missing.append((query_name, query_data))
            continue

        labeled_data = labeled_queries[query_name]
        has_labels = (
            labeled_data.get("highly_relevant") or
            labeled_data.get("relevant") or
            labeled_data.get("somewhat_relevant")
        )

        if not has_labels:
            missing.append((query_name, query_data))

    logger.info(f"Found {len(missing)} queries missing labels")

    if not missing:
        logger.info("✅ All queries have labels!")
        return 0

    # Show sample missing
    logger.info(f"Sample missing: {[q[0] for q in missing[:5]]}")

    # Re-run labeling for missing queries
    logger.info("Re-running labeling for missing queries...")
    logger.info("Run: uv run --script src/ml/scripts/generate_labels_for_new_queries_optimized.py \\")
    logger.info("    --input experiments/test_set_expanded_magic.json \\")
    logger.info("    --output experiments/test_set_labeled_magic.json \\")
    logger.info("    --batch-size 5 --checkpoint-interval 5")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
