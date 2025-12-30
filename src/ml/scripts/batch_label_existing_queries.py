#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai>=0.0.12",
# ]
# ///
"""
Batch label existing queries using multi-judge LLM system.

Useful for:
- Re-labeling queries with low IAA
- Adding labels to queries that only have fallback labels
- Improving label quality for existing test set
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

try:
    from pydantic_ai import Agent
    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import with path handling
import sys
from pathlib import Path as P

script_dir = P(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

try:
    from generate_labels_multi_judge import generate_labels_multi_judge
    HAS_MULTI_JUDGE = True
except ImportError as e:
    HAS_MULTI_JUDGE = False
    logger.error(f"Multi-judge not available: {e}")
    generate_labels_multi_judge = None


def batch_label_queries(
    test_set_path: Path,
    output_path: Path,
    num_judges: int = 3,
    min_labels: int = 10,
    replace_fallback: bool = True,
    batch_size: int = 10,
) -> dict[str, Any]:
    """
    Batch label queries that need better labels.
    
    Args:
        test_set_path: Input test set
        output_path: Output test set
        num_judges: Number of judges per query
        min_labels: Minimum labels required (re-label if below)
        replace_fallback: Replace labels marked as fallback
        batch_size: Checkpoint interval
    """
    if not HAS_PYDANTIC_AI:
        logger.error("pydantic-ai required")
        return {}
    
    # Load test set
    with open(test_set_path) as f:
        data = json.load(f)
    
    queries = data.get("queries", data) if isinstance(data, dict) else data
    
    # Identify queries needing re-labeling
    queries_to_label = []
    
    for query_name, query_data in queries.items():
        if not isinstance(query_data, dict):
            continue
        
        # Check if needs more labels
        total_labels = sum(
            len(query_data.get(level, []))
            for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]
        )
        
        needs_more_labels = total_labels < min_labels
        
        # Check if has fallback labels (marked or inferred)
        has_fallback = query_data.get("_fallback", False) or query_data.get("_source") == "fallback"
        
        # Check if has low IAA
        iaa = query_data.get("iaa", {})
        low_iaa = iaa.get("agreement_rate", 1.0) < 0.6 if iaa else False
        
        if needs_more_labels or (replace_fallback and has_fallback) or low_iaa:
            queries_to_label.append((query_name, query_data, {
                "needs_more_labels": needs_more_labels,
                "has_fallback": has_fallback,
                "low_iaa": low_iaa,
                "current_labels": total_labels,
            }))
    
    logger.info(f"Found {len(queries_to_label)} queries needing re-labeling:")
    logger.info(f"  - Needs more labels (<{min_labels}): {sum(1 for _, _, r in queries_to_label if r['needs_more_labels'])}")
    logger.info(f"  - Has fallback labels: {sum(1 for _, _, r in queries_to_label if r['has_fallback'])}")
    logger.info(f"  - Low IAA (<0.6): {sum(1 for _, _, r in queries_to_label if r['low_iaa'])}")
    
    if not queries_to_label:
        logger.info("✅ All queries have sufficient labels!")
        return {"queries_labeled": 0, "total_queries": len(queries)}
    
    # Re-label queries
    updated = queries.copy()
    processed = 0
    successful = 0
    
    for i, (query_name, query_data, reason) in enumerate(queries_to_label, 1):
        use_case = query_data.get("use_case")
        
        logger.info(f"[{i}/{len(queries_to_label)}] Re-labeling {query_name} (reason: {', '.join(k for k, v in reason.items() if v)})...")
        
        # Generate labels with multi-judge
        result = generate_labels_multi_judge(
            query_name,
            num_judges=num_judges,
            use_case=use_case,
        )
        
        if result and any(result.get(level, []) for level in ["highly_relevant", "relevant", "somewhat_relevant"]):
            # Update query data
            updated[query_name] = {
                **query_data,
                **{k: v for k, v in result.items() if k != "iaa"},
                "iaa": result.get("iaa", {}),
                "_relabeled": True,
                "_relabel_reason": {k: v for k, v in reason.items() if v},
            }
            successful += 1
            
            iaa = result.get("iaa", {})
            agreement = iaa.get("agreement_rate", 0.0)
            num_labels = sum(len(result.get(level, [])) for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"])
            
            logger.info(f"  ✅ Generated {num_labels} labels (IAA: {agreement:.2f})")
        else:
            logger.warning(f"  ⚠️  Failed to generate labels for {query_name}")
        
        processed += 1
        
        # Checkpoint
        if i % batch_size == 0:
            logger.info(f"  💾 Checkpoint: {i}/{len(queries_to_label)} queries processed")
            checkpoint_path = output_path.parent / f"{output_path.stem}_checkpoint.json"
            with open(checkpoint_path, "w") as f:
                json.dump({"version": "relabeled", "queries": updated}, f, indent=2)
    
    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_data = {
        "version": "relabeled_multi_judge",
        "queries": updated,
    }
    
    with open(output_path, "w") as f:
        json.dump(final_data, f, indent=2)
    
    logger.info(f"✅ Re-labeled {successful}/{processed} queries")
    logger.info(f"✅ Saved to {output_path}")
    
    return {
        "queries_labeled": successful,
        "queries_attempted": processed,
        "total_queries": len(updated),
    }


def main() -> int:
    """Batch label existing queries."""
    parser = argparse.ArgumentParser(description="Batch label existing queries with multi-judge")
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Input test set JSON",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output test set JSON",
    )
    parser.add_argument(
        "--num-judges",
        type=int,
        default=3,
        help="Number of judges per query",
    )
    parser.add_argument(
        "--min-labels",
        type=int,
        default=10,
        help="Minimum labels required (re-label if below)",
    )
    parser.add_argument(
        "--replace-fallback",
        action="store_true",
        help="Replace fallback labels",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Checkpoint interval",
    )
    
    args = parser.parse_args()
    
    if not HAS_PYDANTIC_AI:
        logger.error("pydantic-ai required: pip install pydantic-ai")
        return 1
    
    if not HAS_MULTI_JUDGE or generate_labels_multi_judge is None:
        logger.error("Multi-judge labeling not available")
        return 1
    
    result = batch_label_queries(
        Path(args.input),
        Path(args.output),
        num_judges=args.num_judges,
        min_labels=args.min_labels,
        replace_fallback=args.replace_fallback,
        batch_size=args.batch_size,
    )
    
    if result:
        print("\n=== Re-labeling Summary ===")
        print(f"Queries labeled: {result['queries_labeled']}/{result['queries_attempted']}")
        print(f"Total queries: {result['total_queries']}")
        return 0
    
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

