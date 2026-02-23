#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai>=0.0.12",
# ]
# ///
"""
Generate labels using multiple independent LLM judges.

This is a scripts-layer wrapper around `ml.scripts.parallel_multi_judge`:
- Runs N independent judges
- Aggregates via majority vote
- Includes basic agreement metrics under `iaa`

This module is imported by other scripts (e.g. `batch_label_existing_queries.py`),
so keep the public `generate_labels_multi_judge(...)` function stable.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Make `ml` importable when running as a script.
_script_file = Path(__file__).resolve()
_src_dir = _script_file.parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from ml.scripts.parallel_multi_judge import (
    HAS_LABELING,
    HAS_PYDANTIC_AI,
    generate_labels_parallel,
)


def generate_labels_multi_judge(
    query: str,
    num_judges: int = 3,
    use_case: str | None = None,
    game: str | None = None,
    *,
    max_workers: int | None = None,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """
    Generate labels using multiple judges and compute agreement.

    Returns a label dict with an `iaa` block.
    """
    if not HAS_PYDANTIC_AI or not HAS_LABELING:
        logger.error("Required dependencies not available")
        return {}

    workers = max_workers if max_workers is not None else min(num_judges, 8)
    return generate_labels_parallel(
        query=query,
        num_judges=num_judges,
        use_case=use_case,
        game=game,
        max_workers=workers,
        timeout=timeout_s,
    )


def _has_any_labels(query_data: Any) -> bool:
    if not isinstance(query_data, dict):
        return False
    return any(
        query_data.get(level)
        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]
    )


def main() -> int:
    """Generate multi-judge labels for queries lacking labels."""
    parser = argparse.ArgumentParser(description="Generate labels with multi-judge IAA")
    parser.add_argument("--input", type=Path, required=True, help="Input test set JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output test set JSON")
    parser.add_argument("--num-judges", type=int, default=3, help="Judges per query")
    parser.add_argument("--batch-size", type=int, default=10, help="Checkpoint batch size")
    parser.add_argument(
        "--game",
        choices=["magic", "pokemon", "yugioh", "riftbound", "MTG", "PKM", "YGO"],
        default=None,
        help="Optional game override",
    )
    args = parser.parse_args()

    if not HAS_PYDANTIC_AI or not HAS_LABELING:
        logger.error("pydantic-ai / labeling scripts required")
        return 1

    input_path = args.input
    if not input_path.exists():
        logger.error(f"Input not found: {input_path}")
        return 1

    with open(input_path) as f:
        data = json.load(f)

    queries = data.get("queries", data) if isinstance(data, dict) else data
    if not isinstance(queries, dict):
        logger.error("Expected a mapping of query -> data in test set JSON")
        return 1

    to_label = [(q, d) for q, d in queries.items() if not _has_any_labels(d)]
    logger.info(f"Found {len(to_label)} queries needing labels")
    if not to_label:
        logger.info("All queries already have labels")
        return 0

    updated: dict[str, Any] = dict(queries)
    processed = 0

    for i, (query_name, query_data) in enumerate(to_label, 1):
        use_case = query_data.get("use_case") if isinstance(query_data, dict) else None
        result = generate_labels_multi_judge(
            query=query_name,
            num_judges=args.num_judges,
            use_case=use_case,
            game=args.game,
        )
        if result:
            updated[query_name] = {
                **(query_data if isinstance(query_data, dict) else {"data": query_data}),
                **{k: v for k, v in result.items() if k != "iaa"},
                "iaa": result.get("iaa", {}),
            }
        processed += 1

        if args.batch_size and i % args.batch_size == 0:
            checkpoint = args.output.parent / f"{args.output.stem}_checkpoint.json"
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with open(checkpoint, "w") as f:
                json.dump({"version": "multi_judge", "queries": updated}, f, indent=2)
            logger.info(f"Checkpoint saved: {checkpoint} ({i}/{len(to_label)})")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump({"version": "multi_judge", "queries": updated}, f, indent=2)
    logger.info(f"Generated labels for {processed} queries")
    logger.info(f"Saved to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
