#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy",
# ]
# ///
"""
Run full hybrid system evaluation on 940-query test set.

Implements recommendation: "Run full hybrid system evaluation on 940-query test set"
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from ml.utils.paths import PATHS
from ml.scripts.evaluate_hybrid_with_runctl import evaluate_hybrid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    """Run full hybrid evaluation."""
    parser = argparse.ArgumentParser(
        description="Run full hybrid system evaluation on 940-query test set"
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        default=PATHS.test_magic,
        help="Path to test set JSON (default: unified Magic test set)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PATHS.experiments / "hybrid_evaluation_full_940.json",
        help="Path to save results",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to incremental graph",
    )
    parser.add_argument(
        "--gnn-model",
        type=Path,
        help="Path to GNN model (auto-detected if not provided)",
    )
    parser.add_argument(
        "--cooccurrence-embeddings",
        type=Path,
        help="Path to co-occurrence embeddings (auto-detected if not provided)",
    )
    parser.add_argument(
        "--instruction-model",
        type=str,
        default="intfloat/e5-base-v2",
        help="Instruction-tuned model name",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick evaluation mode (limit to 100 queries)",
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Full Hybrid System Evaluation")
    logger.info("=" * 60)
    logger.info(f"Test set: {args.test_set}")
    logger.info(f"Output: {args.output}")
    
    # Auto-detect embeddings if not provided
    if not args.gnn_model:
        gnn_candidates = [
            PATHS.embeddings / "gnn_graphsage.json",
            PATHS.embeddings / "gnn_graphsage_v2025-W52.json",
        ]
        for candidate in gnn_candidates:
            if candidate.exists():
                args.gnn_model = candidate
                logger.info(f"Auto-detected GNN model: {args.gnn_model}")
                break
    
    if not args.cooccurrence_embeddings:
        cooc_candidates = [
            PATHS.embeddings / "node2vec_default.wv",
            PATHS.embeddings / "production.wv",
        ]
        for candidate in cooc_candidates:
            if candidate.exists():
                args.cooccurrence_embeddings = candidate
                logger.info(f"Auto-detected co-occurrence embeddings: {args.cooccurrence_embeddings}")
                break
    
    # Run evaluation
    return evaluate_hybrid(
        test_set_path=args.test_set,
        graph_path=args.graph,
        gnn_model_path=args.gnn_model,
        cooccurrence_embeddings_path=args.cooccurrence_embeddings,
        instruction_model_name=args.instruction_model,
        output_path=args.output,
        use_temporal_split=True,
        quick=args.quick,
    )


if __name__ == "__main__":
    import sys
    sys.exit(main())

