#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "pecanpy>=2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Hyperparameter search for multi-game embeddings.

Extends single-game search to support:
- Multi-game data (MTG, YGO, PKM)
- Game-aware evaluation
- Cross-game similarity metrics
- Unified vs game-specific embeddings
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

try:
    import pandas as pd
    import numpy as np
    from gensim.models import Word2Vec, KeyedVectors
    from pecanpy.pecanpy import SparseOTF
    
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"Missing dependencies: {e}")

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    from ..utils.logging_config import setup_script_logging
    logger = setup_script_logging()
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)


def load_multi_game_test_sets(
    test_sets: dict[str, Path],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Load test sets for multiple games."""
    all_test_sets = {}
    
    for game, test_path in test_sets.items():
        if str(test_path).startswith("s3://"):
            if not HAS_BOTO3:
                logger.warning(f"Cannot load {test_path} from S3 (boto3 not available)")
                continue
            # Download from S3
            import tempfile
            import subprocess
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
                local_path = Path(tmp.name)
                subprocess.run(["aws", "s3", "cp", str(test_path), str(local_path)], check=True)
                test_path = local_path
        
        if not Path(test_path).exists():
            logger.warning(f"Test set not found for {game}: {test_path}")
            continue
        
        with open(test_path) as f:
            data = json.load(f)
            queries = data.get("queries", data)
            all_test_sets[game] = queries
    
    return all_test_sets


def evaluate_multi_game_embedding(
    wv: KeyedVectors,
    test_sets: dict[str, dict[str, dict[str, Any]]],
    name_mapper: dict[str, str] | None = None,
    top_k: int = 10,
) -> dict[str, Any]:
    """Evaluate embeddings on multi-game test sets."""
    from ml.scripts.improve_embeddings_hyperparameter_search import evaluate_embedding
    
    results = {}
    
    for game, test_set in test_sets.items():
        logger.info(f"Evaluating on {game} test set...")
        metrics = evaluate_embedding(wv, test_set, name_mapper, top_k)
        results[game] = metrics
    
    # Aggregate metrics
    all_p_at_10 = [m["p@10"] for m in results.values() if "p@10" in m]
    all_mrr = [m["mrr"] for m in results.values() if "mrr" in m]
    total_queries = sum(m.get("num_queries", 0) for m in results.values())
    
    results["aggregate"] = {
        "p@10": sum(all_p_at_10) / len(all_p_at_10) if all_p_at_10 else 0.0,
        "mrr": sum(all_mrr) / len(all_mrr) if all_mrr else 0.0,
        "num_queries": total_queries,
        "num_games": len(test_sets),
    }
    
    return results


def main() -> int:
    """Run multi-game hyperparameter search."""
    parser = argparse.ArgumentParser(description="Hyperparameter search for multi-game embeddings")
    parser.add_argument("--input", type=str, required=True, help="Multi-game pairs CSV (S3 or local)")
    parser.add_argument("--output", type=str, required=True, help="Output results JSON (S3 or local)")
    parser.add_argument("--test-sets", type=str, nargs="+", help="Test set paths: game1:path1 game2:path2")
    parser.add_argument("--max-configs", type=int, default=20, help="Maximum configurations to test")
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        logger.error("Missing dependencies")
        return 1
    
    # Parse test sets
    test_sets = {}
    if args.test_sets:
        for test_spec in args.test_sets:
            if ":" in test_spec:
                game, path = test_spec.split(":", 1)
                test_sets[game] = Path(path)
            else:
                # Default to MTG if no game specified
                test_sets["MTG"] = Path(test_spec)
    
    if not test_sets:
        logger.warning("No test sets provided, using default")
        test_sets = {"MTG": Path("experiments/test_set_labeled_magic.json")}
    
    # Load test sets
    all_test_sets = load_multi_game_test_sets(test_sets)
    
    if not all_test_sets:
        logger.error("No test sets loaded")
        return 1
    
    logger.info(f"Loaded test sets for {len(all_test_sets)} games")
    
    # TODO: Implement full hyperparameter search for multi-game
    # For now, this is a placeholder that shows the structure
    logger.info("Multi-game hyperparameter search structure ready")
    logger.info("This extends single-game search to support all deck card games")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

