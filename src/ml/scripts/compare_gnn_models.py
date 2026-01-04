#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "torch",
#     "torch-geometric",
# ]
# ///
"""
Compare GNN models (GraphSAGE vs LightGCN) in ablation study.

Tests both models on the same data and compares performance metrics.
"""

from __future__ import annotations

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from ..similarity.gnn_embeddings import CardGNNEmbedder
from ..utils.paths import PATHS
from ..utils.logging_config import setup_script_logging, log_exception

logger = setup_script_logging()


def compare_gnn_models(
    edgelist_path: Path,
    test_set_path: Path | None = None,
    output_path: Path | None = None,
    models: list[str] | None = None,
    epochs: int = 50,
    lr: float = 0.01,
    hidden_dim: int = 128,
    num_layers: int = 2,
    use_contrastive: bool = False,
) -> dict[str, Any]:
    """
    Compare multiple GNN models on the same data.
    
    Args:
        edgelist_path: Path to edgelist for training
        test_set_path: Optional test set for evaluation
        output_path: Path to save comparison results
        models: List of model types to compare (default: ["GraphSAGE", "LightGCN"])
        epochs: Training epochs
        lr: Learning rate
        hidden_dim: Hidden dimension
        num_layers: Number of layers
        use_contrastive: Use contrastive learning
        
    Returns:
        Dictionary with comparison results
    """
    if models is None:
        models = ["GraphSAGE", "LightGCN"]
    
    logger.info("="*70)
    logger.info("GNN MODEL COMPARISON")
    logger.info("="*70)
    logger.info(f"Models to compare: {models}")
    logger.info(f"Training epochs: {epochs}")
    logger.info(f"Use contrastive: {use_contrastive}")
    logger.info("")
    
    results = {
        "models": models,
        "config": {
            "epochs": epochs,
            "lr": lr,
            "hidden_dim": hidden_dim,
            "num_layers": num_layers,
            "use_contrastive": use_contrastive,
        },
        "results": {},
    }
    
    for model_type in models:
        logger.info(f"\n{'='*70}")
        logger.info(f"Training {model_type}")
        logger.info(f"{'='*70}")
        
        try:
            # Train model
            embedder = CardGNNEmbedder(
                model_type=model_type,
                hidden_dim=hidden_dim,
                num_layers=num_layers,
            )
            
            output_file = output_path.parent / f"gnn_{model_type.lower()}_comparison.json" if output_path else None
            
            embedder.train(
                edgelist_path,
                epochs=epochs,
                lr=lr,
                output_path=output_file,
                use_contrastive=use_contrastive,
            )
            
            # Extract metrics (would need to track during training)
            model_results = {
                "model_type": model_type,
                "trained": True,
                "num_nodes": len(embedder.node_to_idx),
                "num_edges": len(embedder.embeddings),
            }
            
            # Evaluate on test set if provided
            if test_set_path and test_set_path.exists():
                logger.info(f"Evaluating {model_type} on test set...")
                try:
                    # Load test set
                    with open(test_set_path) as f:
                        test_data = json.load(f)
                    
                    test_set = test_data.get("queries", test_data)
                    logger.info(f"  Loaded {len(test_set)} test queries")
                    
                    # Convert GNN embedder to KeyedVectors-like interface for evaluation
                    from gensim.models import KeyedVectors
                    from ml.scripts.evaluate_all_embeddings import evaluate_embedding
                    
                    # Create KeyedVectors wrapper for GNN embeddings
                    class GNNKeyedVectors:
                        def __init__(self, embedder: CardGNNEmbedder):
                            self.embedder = embedder
                            self.key_to_index = {name: idx for idx, name in enumerate(embedder.node_to_idx.keys())}
                            self.index_to_key = list(embedder.node_to_idx.keys())
                        
                        def __contains__(self, key: str) -> bool:
                            return key in self.embedder.embeddings
                        
                        def similarity(self, word1: str, word2: str) -> float:
                            if word1 not in self.embedder.embeddings or word2 not in self.embedder.embeddings:
                                return 0.0
                            return self.embedder.similarity(word1, word2)
                        
                        def most_similar(self, word: str, topn: int = 10) -> list[tuple[str, float]]:
                            if word not in self.embedder.embeddings:
                                return []
                            return self.embedder.most_similar(word, topn=topn)
                    
                    gnn_wv = GNNKeyedVectors(embedder)
                    
                    # Evaluate
                    eval_results = evaluate_embedding(
                        gnn_wv,
                        test_set,
                        top_k=10,
                        per_query=False,
                    )
                    
                    model_results["evaluation"] = {
                        "p@10": eval_results.get("p@10", 0.0),
                        "mrr": eval_results.get("mrr", 0.0),
                        "num_queries": eval_results.get("num_queries", 0),
                        "vocab_coverage": eval_results.get("vocab_coverage", {}),
                    }
                    logger.info(f"  P@10: {model_results['evaluation']['p@10']:.4f}, MRR: {model_results['evaluation']['mrr']:.4f}")
                    
                except Exception as e:
                    log_exception(logger, "Evaluation failed", e, level="warning", include_context=True)
                    model_results["evaluation"] = {"error": str(e)}
            
            results["results"][model_type] = model_results
            logger.info(f"✓ {model_type} training complete")
            
        except Exception as e:
            log_exception(logger, f"{model_type} training failed", e, include_context=True)
            results["results"][model_type] = {
                "model_type": model_type,
                "trained": False,
                "error": str(e),
            }
    
    # Save results
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"\n✓ Comparison results saved to {output_path}")
    
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare GNN models (GraphSAGE vs LightGCN)")
    parser.add_argument(
        "--edgelist",
        type=Path,
        default=PATHS.graphs / "train_val_edgelist.edg",
        help="Path to edgelist for training",
    )
    parser.add_argument(
        "--test-set",
        type=Path,
        help="Optional test set for evaluation",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PATHS.experiments / "gnn_model_comparison.json",
        help="Path to save comparison results",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["GraphSAGE", "LightGCN"],
        help="Models to compare",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=50,
        help="Training epochs",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=0.01,
        help="Learning rate",
    )
    parser.add_argument(
        "--hidden-dim",
        type=int,
        default=128,
        help="Hidden dimension",
    )
    parser.add_argument(
        "--num-layers",
        type=int,
        default=2,
        help="Number of layers",
    )
    parser.add_argument(
        "--use-contrastive",
        action="store_true",
        help="Use contrastive learning",
    )
    args = parser.parse_args()
    
    try:
        results = compare_gnn_models(
            args.edgelist,
            args.test_set,
            args.output,
            args.models,
            args.epochs,
            args.lr,
            args.hidden_dim,
            args.num_layers,
            args.use_contrastive,
        )
        
        logger.info("\n" + "="*70)
        logger.info("COMPARISON SUMMARY")
        logger.info("="*70)
        for model_type, model_results in results["results"].items():
            status = "✓" if model_results.get("trained") else "✗"
            logger.info(f"{status} {model_type}: {model_results.get('num_nodes', 'N/A')} nodes")
        
        return 0
        
    except Exception as e:
        log_exception(logger, "Comparison failed", e, include_context=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

