#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "sentence-transformers",
# "torch>=2.0.0",
# "torch-geometric>=2.4.0",
# ]
# ///
"""
Evaluate hybrid embedding system using runctl.

Tests all three embedding types:
1. Co-occurrence embeddings (Node2Vec)
2. Instruction-tuned embeddings (E5-base-instruct)
3. GNN embeddings (GraphSAGE)

Measures P@10 improvement over baseline.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ..utils.evaluation import compute_precision_at_k
from ..evaluation.cv_ablation import TemporalSplitter, SplitConfig
from ..data.incremental_graph import IncrementalCardGraph
from ..scripts.integrate_hybrid_embeddings import (
 create_fusion_with_hybrid_embeddings,
 load_hybrid_embeddings,
)
from ..utils.paths import PATHS

from ..utils.logging_config import setup_script_logging

logger = setup_script_logging()


def evaluate_hybrid(
 test_set_path: Path | str,
 graph_path: Path | str | None = None,
 gnn_model_path: Path | str | None = None,
 cooccurrence_embeddings_path: Path | str | None = None,
 instruction_model_name: str = "intfloat/e5-base-v2",
 output_path: Path | str | None = None,
    use_temporal_split: bool = True,
    quick: bool = False,
    limit: int | None = None,
) -> int:
    """
    Evaluate hybrid embedding system.
    
    Args:
    test_set_path: Path to test set JSON
    graph_path: Path to incremental graph JSON (for Jaccard similarity)
    gnn_model_path: Path to GNN model
    cooccurrence_embeddings_path: Path to co-occurrence embeddings
    instruction_model_name: Instruction-tuned model name
    output_path: Path to save results
    use_temporal_split: Use temporal split to prevent data leakage
    
    Returns:
    Exit code
    """
    test_set_path = Path(test_set_path)
    
    # Load test set
    logger.info(f"Loading test set: {test_set_path}")
    with open(test_set_path) as f:
        test_data = json.load(f)
    
    queries = test_data.get("queries", test_data) if isinstance(test_data, dict) else test_data
    original_query_count = len(queries) if isinstance(queries, dict) else len(queries)
    
    # Quick evaluation mode: limit queries
    if quick or limit:
        limit_count = limit if limit else 20

        if isinstance(queries, dict):
            # Take first N queries
            limited_queries = dict(list(queries.items())[:limit_count])
            test_data = {"queries": limited_queries, "version": test_data.get("version", "quick")}
            queries = limited_queries
            logger.info(f"Quick evaluation: Limited to {len(limited_queries)} queries (from {original_query_count})")
        elif isinstance(queries, list):
            limited_queries = queries[:limit_count]
            test_data = {"queries": limited_queries, "version": test_data.get("version", "quick")}
            queries = limited_queries
            logger.info(f"Quick evaluation: Limited to {len(limited_queries)} queries (from {original_query_count})")
    
    logger.info(f" {len(queries) if isinstance(queries, dict) else len(queries)} test queries")
    
    # Load graph and split temporally to prevent leakage
    adj = {}
    if graph_path:
        graph_path = Path(graph_path)
        if graph_path.exists():
            logger.info(f"Loading graph: {graph_path}")
            # Auto-detect SQLite from extension
            use_sqlite = graph_path.suffix == ".db" if graph_path.suffix else False
            full_graph = IncrementalCardGraph(graph_path, use_sqlite=use_sqlite)
            logger.info(f" Full graph: {len(full_graph.nodes)} nodes, {len(full_graph.edges)} edges")
            
            if use_temporal_split:
                logger.info("Applying temporal split to prevent data leakage...")
                splitter = TemporalSplitter(SplitConfig(train_frac=0.7, val_frac=0.15, test_frac=0.15))
                train_graph, val_graph, test_graph = splitter.split_graph_edges(full_graph)
                logger.info(f" Train graph: {len(train_graph.edges)} edges (for Jaccard)")
                logger.info(f" Val graph: {len(val_graph.edges)} edges")
                logger.info(f" Test graph: {len(test_graph.edges)} edges [EXCLUDED from evaluation]")
                
                # Use train-only graph for Jaccard to prevent leakage
                adj = train_graph.edges_to_adj_dict(min_weight=1)
                logger.info(f"✓ Using train-only graph for Jaccard similarity ({len(adj)} cards)")
            else:
                logger.warning("Warning: WARNING: Using full graph for Jaccard - potential data leakage")
                adj = full_graph.edges_to_adj_dict(min_weight=1)
        else:
            logger.warning(f"Graph not found: {graph_path}, Jaccard similarity will be disabled")
    
    # Load hybrid embeddings
    logger.info("Loading hybrid embeddings...")
    embeddings_data = load_hybrid_embeddings(
        gnn_model_path=Path(gnn_model_path) if gnn_model_path else None,
        cooccurrence_embeddings_path=Path(cooccurrence_embeddings_path) if cooccurrence_embeddings_path else None,
        instruction_model_name=instruction_model_name,
    )
    
    # Print what's loaded
    logger.info("Loaded embeddings:")
    for name, loaded in embeddings_data["loaded"].items():
        status = "✓" if loaded else "✗"
        logger.info(f" {status} {name}")
    
    # Create fusion system with train-only graph for Jaccard
    logger.info("Creating fusion system...")
    fusion = create_fusion_with_hybrid_embeddings(embeddings_data, adj=adj)
    
    # Evaluate
    logger.info("Evaluating on test set...")
    results = {
        "queries": {},
        "summary": {},
    }
    
    total_p_at_10 = 0.0
    evaluated = 0
    
    for query, labels in queries.items():
        try:
            # Get top 10 similar cards
            similar = fusion.find_similar(query, topn=10)
            candidates = [card for card, _ in similar]
            
            # Compute P@10
            p_at_10 = compute_precision_at_k(candidates, labels, k=10)
            
            results["queries"][query] = {
                "p_at_10": p_at_10,
                "top_10": candidates,
            }
            
            total_p_at_10 += p_at_10
            evaluated += 1
            
        except Exception as e:
            logger.warning(f"Failed to evaluate {query}: {e}")
            results["queries"][query] = {"error": str(e)}
    
    # Summary
    avg_p_at_10 = total_p_at_10 / evaluated if evaluated > 0 else 0.0
    results["summary"] = {
        "total_queries": len(queries),
        "evaluated": evaluated,
        "avg_p_at_10": avg_p_at_10,
        "embeddings_loaded": embeddings_data["loaded"],
    }
    
    logger.info("\n" + "="*60)
    logger.info("Evaluation Results")
    logger.info("="*60)
    logger.info(f" Total queries: {len(queries)}")
    logger.info(f" Evaluated: {evaluated}")
    logger.info(f" Average P@10: {avg_p_at_10:.4f}")
    logger.info("="*60)
    
    # Save results
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"\n✓ Results saved: {output_path}")
    
    # Register evaluation in registry (if available)
    try:
        from ..utils.evaluation_registry import EvaluationRegistry
        from ..utils.path_resolution import version_path
        
        # Extract version from output path or use timestamp
        if output_path:
            version = output_path.stem.split("_v")[-1] if "_v" in output_path.stem else datetime.now().strftime("%Y-W%V")
        
        registry = EvaluationRegistry()
        registry.record_evaluation(
            model_type="hybrid",
            model_version=version,
            model_path=gnn_model_path or cooccurrence_embeddings_path or "hybrid_system",
            evaluation_results=results,
            test_set_path=test_set_path,
            metadata={
                "instruction_model": instruction_model_name,
                "use_temporal_split": use_temporal_split,
                "quick_mode": quick or limit is not None,
            },
        )
        logger.info(f"✓ Evaluation registered in model registry (version: {version})")
    except Exception as e:
        logger.warning(f"Failed to register evaluation in registry: {e}")
    
    return 0


def main() -> int:
 """Main entry point."""
 parser = argparse.ArgumentParser(description="Evaluate hybrid embeddings with runctl")
 parser.add_argument(
 "--test-set",
 type=Path,
 required=True,
 help="Path to test set JSON",
 )
 parser.add_argument(
 "--gnn-model",
 type=Path,
 help="Path to GNN model (default: data/embeddings/gnn_graphsage.json)",
 )
 parser.add_argument(
 "--cooccurrence-embeddings",
 type=Path,
 help="Path to co-occurrence embeddings",
 )
 parser.add_argument(
 "--instruction-model",
 type=str,
 default="intfloat/e5-base-v2",
 help="Instruction-tuned model name",
 )
 parser.add_argument(
 "--graph",
 type=Path,
 default=PATHS.graphs / "incremental_graph.db",
 help="Path to incremental graph (SQLite .db or JSON .json) for Jaccard similarity",
 )
 parser.add_argument(
 "--use-sqlite",
 action="store_true",
 default=None, # Auto-detect from extension
 help="Use SQLite storage (auto-detected from .db extension)",
 )
 parser.add_argument(
 "--game",
 type=str,
 choices=["MTG", "PKM", "YGO"],
 default=None,
 help="Filter graph by game for evaluation",
 )
 parser.add_argument(
 "--output",
 type=Path,
 help="Path to save results JSON",
 )
 parser.add_argument(
 "--use-temporal-split",
 action="store_true",
 default=True,
 help="Use temporal split to prevent data leakage (default: True)",
 )
 parser.add_argument(
 "--no-temporal-split",
 dest="use_temporal_split",
 action="store_false",
 help="Disable temporal split (WARNING: may cause data leakage)",
 )
 parser.add_argument(
 "--output-version",
 type=str,
 help="Version tag for output files (e.g., 'v2024-W52' or 'v2024-12-31'). If provided, outputs will be versioned (hybrid_evaluation_results_v{version}.json). If not provided, uses default unversioned paths.",
 )
 parser.add_argument(
 "--quick",
 action="store_true",
 help="Quick evaluation mode (subset of test set, faster)",
 )
 parser.add_argument(
 "--limit",
 type=int,
 help="Limit number of queries for quick evaluation",
 )
 
 args = parser.parse_args()
 
 # Default paths
 if not args.gnn_model:
     args.gnn_model = PATHS.embeddings / "gnn_graphsage.json"
 if not args.cooccurrence_embeddings:
     args.cooccurrence_embeddings = PATHS.embeddings / "production.wv"
 if not args.output:
     base_name = "hybrid_evaluation_results"
     if args.output_version:
         from ..utils.path_resolution import version_path
         args.output = version_path(PATHS.experiments / f"{base_name}.json", args.output_version)
     else:
         args.output = PATHS.experiments / f"{base_name}.json"
 elif args.output_version:
     # Version the output path if version provided but output path was explicitly set
     from ..utils.path_resolution import version_path
 args.output = version_path(args.output, args.output_version)
 
 return evaluate_hybrid(
 test_set_path=args.test_set,
 graph_path=args.graph,
 gnn_model_path=args.gnn_model,
 cooccurrence_embeddings_path=args.cooccurrence_embeddings,
 instruction_model_name=args.instruction_model,
 output_path=args.output,
 use_temporal_split=args.use_temporal_split,
 quick=args.quick,
 limit=args.limit,
 )


if __name__ == "__main__":
 sys.exit(main())

