#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Evaluate all embedding methods on test set.

Compares:
- DeepWalk
- Node2Vec-Default
- Node2Vec-BFS
- Node2Vec-DFS
- Jaccard (baseline)

Uses PEP 723 inline dependencies.

Research Basis:
- Multiple metrics (P@K, MRR, NDCG) provide comprehensive evaluation
- Confidence intervals (bootstrap) quantify uncertainty
- Per-query analysis identifies systematic issues
- Standardized query coverage ensures fair comparison

References:
- Recommender systems metrics: https://neptune.ai/blog/recommender-systems-metrics
- Evaluating recommender systems: https://www.evidentlyai.com/ranking-metrics/evaluating-recommender-systems
- Ranking metrics: https://www.shaped.ai/blog/a-b-testing-your-rankings-metrics-that-matter-in-the-real-world
- MAP, MMR, NDCG: https://www.shaped.ai/blog/evaluating-recommendation-systems-map-mmr-ndcg
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

# Set up project paths
import sys
from ml.utils.path_setup import setup_project_paths
setup_project_paths()

from ml.utils.paths import PATHS

try:
    import pandas as pd
    import numpy as np
    from gensim.models import KeyedVectors
    
    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"Missing dependencies: {e}")

try:
    from ml.utils.aim_helpers import create_training_run, track_evaluation_metrics
    HAS_AIM = True
except ImportError:
    HAS_AIM = False
    create_training_run = None
    track_evaluation_metrics = None


def load_test_set(test_set_path: Path) -> dict[str, dict[str, Any]]:
    """Load test set (canonical format: dict mapping query to relevance labels)."""
    import sys
    import os
    
    print(f"  Loading test set from {test_set_path}...", end="", flush=True)
    sys.stdout.flush()
    
    try:
        # Use canonical load_test_set from utils
        from ml.utils.data_loading import load_test_set as canonical_load
        
        # Check file size first (fast)
        size = os.path.getsize(test_set_path)
        print(f" ({size / 1024:.1f} KB)", flush=True)
        sys.stdout.flush()
        
        # Load using canonical function
        data = canonical_load(path=test_set_path)
        
        # Handle both formats: direct dict or wrapped in "queries"
        if "queries" in data:
            result = data["queries"]
        else:
            result = data
        
        print(f"  Loaded {len(result)} queries", flush=True)
        sys.stdout.flush()
        return result
    except Exception as e:
        print(f"\n  ERROR loading test set: {e}", flush=True)
        sys.stdout.flush()
        raise


def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    """Compute Jaccard similarity."""
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


# Use shared function for loading graph
def load_graph_for_jaccard(
    pairs_csv: Path | None = None,
    graph_db: Path | None = None,
    game: str | None = None,
) -> dict[str, set[str]]:
    """Load graph adjacency for Jaccard similarity."""
    from ml.utils.shared_operations import load_graph_for_jaccard as shared_load_graph
    return shared_load_graph(pairs_csv=pairs_csv, graph_db=graph_db, game=game)


def evaluate_embedding(
    wv: KeyedVectors,
    test_set: dict[str, dict[str, Any]],
    top_k: int = 10,
    name_mapper: Any | None = None,
    per_query: bool = False,  # Return per-query results
    verbose: bool = False,  # Add diagnostic logging
) -> dict[str, Any]:
    """
    Evaluate embedding on test set (canonical format).
    
    Uses canonical metric calculation from ml.utils.evaluation.
    
    Returns:
        If per_query=False: dict with metrics (P@10, MRR, etc.)
        If per_query=True: dict with metrics + per_query_results
    """
    # Import canonical metric calculation
    try:
        from ml.utils.evaluation import compute_precision_at_k
        USE_CANONICAL = True
    except ImportError:
        USE_CANONICAL = False
        # Fallback relevance weights
        relevance_weights = {
            "highly_relevant": 1.0,
            "relevant": 0.75,
            "somewhat_relevant": 0.5,
            "marginally_relevant": 0.25,
            "irrelevant": 0.0,
        }
    
    scores = []
    reciprocal_ranks = []
    per_query_results = {} if per_query else None
    
    # Diagnostic tracking
    skipped_queries = []
    skipped_reasons = {}
    vocab_coverage = {
        "total_queries": len(test_set),
        "found_in_vocab": 0,
        "mapped_found": 0,
        "not_in_vocab": 0,
        "no_relevant_labels": 0,
        "evaluation_errors": 0,
    }
    
    # Apply name mapping upfront for consistency
    if name_mapper:
        from ml.utils.name_normalizer import apply_name_mapping_to_test_set
        test_set = apply_name_mapping_to_test_set(test_set, name_mapper)
    
    for query, labels in test_set.items():
        # Check if query is in vocabulary
        if query not in wv:
            skipped_queries.append(query)
            skipped_reasons[query] = "not_in_vocabulary"
            vocab_coverage["not_in_vocab"] += 1
            if verbose:
                print(f"  {query}: SKIPPED (not in vocabulary)")
            continue
        
        vocab_coverage["found_in_vocab"] += 1
        
        # Get all relevant cards (combining all relevance levels)
        all_relevant = set()
        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
            all_relevant.update(labels.get(level, []))
        
        if not all_relevant:
            skipped_queries.append(query)
            skipped_reasons[query] = "no_relevant_labels"
            vocab_coverage["no_relevant_labels"] += 1
            if verbose:
                print(f"  {query}: SKIPPED (no relevant labels)")
            continue
        
        # Get top-k similar
        try:
            similar = wv.most_similar(query, topn=top_k)
            candidates = [card for card, _ in similar]
        except KeyError:
            skipped_queries.append(query)
            skipped_reasons[query] = "keyerror_during_similarity"
            vocab_coverage["evaluation_errors"] += 1
            if verbose:
                print(f"  {query}: SKIPPED (KeyError during similarity lookup)")
            continue
        
        # Use canonical metric calculation if available
        if USE_CANONICAL:
            score = compute_precision_at_k(candidates, labels, k=top_k)
        else:
            # Fallback: manual calculation
            score = 0.0
            for card in candidates[:top_k]:
                for level, weight in relevance_weights.items():
                    if card in labels.get(level, []):
                        score += weight
                        break
            score = score / top_k if top_k > 0 else 0.0
        
        scores.append(score)
        
        # MRR (first hit in highly_relevant or relevant)
        target = set(labels.get("highly_relevant", [])) | set(labels.get("relevant", []))
        query_mrr = 0.0
        for rank, candidate in enumerate(candidates, 1):
            if candidate in target:
                query_mrr = 1.0 / rank
                break
        reciprocal_ranks.append(query_mrr)
        
        # Store per-query results if requested
        if per_query and per_query_results is not None:
            per_query_results[query] = {
                "p@10": score,
                "mrr": query_mrr,
                "num_similar": len(similar),
                "num_relevant": len(all_relevant),
            }
        
        if verbose:
            print(f"  {query}: P@{top_k}={score:.3f}, MRR={query_mrr:.3f}")
    
    if not scores:
        result = {
            "p@10": 0.0,
            "mrr": 0.0,
            "num_queries": 0,
            "num_evaluated": 0,
            "num_skipped": len(skipped_queries),
            "vocab_coverage": vocab_coverage,
        }
        if verbose:
            print(f"\nWarning: No queries evaluated! Coverage: {vocab_coverage}")
        return result
    
    avg_p_at_k = np.mean(scores) if scores else 0.0
    avg_mrr = np.mean(reciprocal_ranks) if reciprocal_ranks else 0.0
    
    result = {
        "p@10": float(avg_p_at_k),
        "mrr": float(avg_mrr),
        "num_queries": len(test_set),
        "num_evaluated": len(scores),
        "num_skipped": len(skipped_queries),
        "vocab_coverage": vocab_coverage,
    }
    
    if per_query and per_query_results is not None:
        result["per_query_results"] = per_query_results
    
    if verbose and skipped_queries:
        print(f"\nWarning: Skipped {len(skipped_queries)} queries:")
        for q in list(skipped_queries)[:10]:
            print(f"    {q}: {skipped_reasons.get(q, 'unknown')}")
        if len(skipped_queries) > 10:
            print(f"    ... and {len(skipped_queries) - 10} more")
    
    return result


def evaluate_jaccard(
    adj: dict[str, set[str]],
    test_set: dict[str, dict[str, Any]],
    top_k: int = 10,
    name_mapper: Any | None = None,
    verbose: bool = False,
) -> dict[str, float]:
    """Evaluate Jaccard similarity on test set (canonical format)."""
    scores = []
    reciprocal_ranks = []
    
    # Relevance weights (fallback if canonical not available)
    relevance_weights = {
        "highly_relevant": 1.0,
        "relevant": 0.75,
        "somewhat_relevant": 0.5,
        "marginally_relevant": 0.25,
        "irrelevant": 0.0,
    }
    
    # Apply name mapping upfront for consistency
    if name_mapper:
        from ml.utils.name_normalizer import apply_name_mapping_to_test_set
        test_set = apply_name_mapping_to_test_set(test_set, name_mapper)
    
    # Diagnostic tracking
    skipped_queries = []
    skipped_reasons = {}
    vocab_coverage = {
        "total_queries": len(test_set),
        "found_in_graph": 0,
        "not_in_graph": 0,
        "no_relevant_labels": 0,
    }
    
    for query, labels in test_set.items():
        if query not in adj:
            skipped_queries.append(query)
            skipped_reasons[query] = "not_in_graph"
            vocab_coverage["not_in_graph"] += 1
            if verbose:
                print(f"  {query}: SKIPPED (not in graph)")
            continue
        
        vocab_coverage["found_in_graph"] += 1
        
        # Get all relevant cards
        all_relevant = set()
        for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
            all_relevant.update(labels.get(level, []))
        
        if not all_relevant:
            skipped_queries.append(query)
            skipped_reasons[query] = "no_relevant_labels"
            vocab_coverage["no_relevant_labels"] += 1
            if verbose:
                print(f"  {query}: SKIPPED (no relevant labels)")
            continue
        
        # Get neighbors and compute Jaccard
        query_neighbors = adj[query]
        similarities = []
        
        for candidate in adj.keys():
            if candidate == query:
                continue
            candidate_neighbors = adj[candidate]
            sim = jaccard_similarity(query_neighbors, candidate_neighbors)
            similarities.append((candidate, sim))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        candidates = [card for card, _ in similarities[:top_k]]
        
        # Use canonical metric calculation if available
        try:
            from ml.utils.evaluation import compute_precision_at_k
            precision_at_k = compute_precision_at_k(candidates, labels, k=top_k)
        except ImportError:
            # Fallback: manual calculation
            score = 0.0
            for card in candidates[:top_k]:
                for level, weight in relevance_weights.items():
                    if card in labels.get(level, []):
                        score += weight
                        break
            precision_at_k = score / top_k
        
        scores.append(precision_at_k)
        
        # MRR (first hit in highly_relevant or relevant)
        target = set(labels.get("highly_relevant", [])) | set(labels.get("relevant", []))
        query_mrr = 0.0
        for rank, candidate in enumerate(candidates, 1):
            if candidate in target:
                query_mrr = 1.0 / rank
                break
        reciprocal_ranks.append(query_mrr)
        
        if verbose:
            print(f"  {query}: P@{top_k}={precision_at_k:.3f}, MRR={query_mrr:.3f}")
    
    if not scores:
        result = {
            "p@10": 0.0,
            "mrr": 0.0,
            "num_queries": 0,
            "num_evaluated": 0,
            "num_skipped": len(skipped_queries),
            "vocab_coverage": vocab_coverage,
        }
        if verbose:
            print(f"\nWarning: No queries evaluated! Coverage: {vocab_coverage}")
        return result
    
    # Calculate average precision (using scores list)
    avg_precision = np.mean(scores) if scores else 0.0
    avg_mrr = np.mean(reciprocal_ranks) if reciprocal_ranks else 0.0
    
    result = {
        "p@10": float(avg_precision),
        "mrr": float(avg_mrr),
        "num_queries": len(test_set),
        "num_evaluated": len(scores),
        "num_skipped": len(skipped_queries),
        "vocab_coverage": vocab_coverage,
    }
    
    if verbose and skipped_queries:
        print(f"\nWarning: Skipped {len(skipped_queries)} queries:")
        for q in list(skipped_queries)[:10]:
            print(f"    {q}: {skipped_reasons.get(q, 'unknown')}")
        if len(skipped_queries) > 10:
            print(f"    ... and {len(skipped_queries) - 10} more")
    
    return result


def main() -> int:
    """Evaluate all embedding methods."""
    parser = argparse.ArgumentParser(description="Evaluate all embedding methods")
    parser.add_argument(
        "--test-set",
        type=str,
        default=None,  # Use PATHS.test_magic if not provided
        help="Test set path (default: experiments/test_set_unified_magic.json)",
    )
    parser.add_argument(
        "--pairs-csv",
        type=str,
        default=None,  # Use PATHS.pairs_large if not provided
        help="Pairs CSV for Jaccard (legacy, use --graph-db if available)",
    )
    parser.add_argument(
        "--graph-db",
        type=str,
        default=None,
        help="Incremental graph SQLite database (preferred over pairs-csv)",
    )
    parser.add_argument(
        "--game",
        type=str,
        choices=["MTG", "PKM", "YGO"],
        default=None,
        help="Filter graph by game for evaluation",
    )
    parser.add_argument(
        "--embeddings-dir",
        type=str,
        default="data/embeddings",
        help="Embeddings directory",
    )
    parser.add_argument(
        "--name-mapping",
        type=str,
        default=None,  # Use PATHS.experiments/name_mapping.json if exists
        help="Name mapping JSON (optional)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,  # Use PATHS.hybrid_evaluation_results if not provided
        help="Output JSON file (default: experiments/hybrid_evaluation_results.json)",
    )
    parser.add_argument(
        "--confidence-intervals",
        action="store_true",
        help="Compute bootstrap confidence intervals (SLOW - default: disabled)",
    )
    parser.add_argument(
        "--n-bootstrap",
        type=int,
        default=100,
        help="Number of bootstrap samples for confidence intervals (default: 100, use 1000 for publication)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip confidence intervals and use fast evaluation (default behavior)",
    )
    parser.add_argument(
        "--per-query",
        action="store_true",
        help="Include per-query breakdown in output",
    )
    parser.add_argument(
        "--validate-test-set",
        action="store_true",
        help="Validate test set coverage before evaluation",
    )
    parser.add_argument(
        "--generate-dashboard",
        action="store_true",
        help="Generate quality dashboard after evaluation",
    )
    
    args = parser.parse_args()
    
    # Use PATHS defaults if not provided
    if args.test_set is None:
        args.test_set = str(PATHS.test_magic)
    if args.name_mapping is None:
        # Try to use default if exists, otherwise None
        name_mapping_path = PATHS.experiments / "name_mapping.json"
        args.name_mapping = str(name_mapping_path) if name_mapping_path.exists() else None
    if args.output is None:
        args.output = str(PATHS.hybrid_evaluation_results)
    
    if not HAS_DEPS:
        print("Error: Missing dependencies")
        return 1
    
    import sys
    sys.stdout.flush()
    
    print("=" * 70)
    print("Evaluate All Embedding Methods")
    print("=" * 70)
    print()
    sys.stdout.flush()
    
    # Load test set (with optional validation)
    test_set_path = Path(args.test_set)
    if not test_set_path.exists():
        print(f"Error: Test set not found: {test_set_path}")
        sys.stdout.flush()
        return 1
    
    if args.validate_test_set:
        print("  Validating test set coverage...")
        try:
            from ml.evaluation.test_set_validation import validate_test_set_coverage
            validation_result = validate_test_set_coverage(
                test_set_path=test_set_path,
                min_queries=100,
                min_labels_per_query=5,
            )
            if not validation_result["valid"]:
                print(f"  Warning: Test set validation issues found:")
                for issue in validation_result.get("issues", []):
                    print(f"     - {issue}")
            else:
                print(f"  Test set validation passed")
        except Exception as e:
            print(f"  Warning: Test set validation failed: {e}")
    
    test_set = load_test_set(test_set_path)
    
    # Load name mapping if available (optional)
    name_mapper = None
    mapping_path = Path(args.name_mapping)
    if mapping_path.exists():
        try:
            # Try importing NameMapper - it's optional
            import sys
            from pathlib import Path as P
            # Add src to path if needed
            script_dir = P(__file__).parent
            src_dir = script_dir.parent.parent
            if str(src_dir) not in sys.path:
                sys.path.insert(0, str(src_dir))
            
            from ml.utils.name_normalizer import NameMapper
            print(f"Loading name mapping from {mapping_path}")
            name_mapper = NameMapper.load_from_file(mapping_path)
            print(f"  Loaded {len(name_mapper.mapping)} name mappings")
        except ImportError:
            print(f"Warning: NameMapper not available, proceeding without name mapping")
    else:
        print(f"Warning: No name mapping found at {mapping_path}, proceeding without mapping")
    print()
    
    embeddings_dir = Path(args.embeddings_dir)
    results = {}
    
    # Initialize Aim tracking for evaluation
    aim_run = None
    if HAS_AIM and create_training_run:
        aim_run = create_training_run(
            experiment_name="embedding_evaluation",
            hparams={
                "test_set": str(test_set_path),
                "pairs_csv": args.pairs_csv,
            },
            tags=["evaluation", "embeddings", "comparison"],
        )
    
    # Evaluate each embedding method
    # First, check what embeddings actually exist
    print(f"Scanning embeddings directory: {embeddings_dir}")
    sys.stdout.flush()
    
    # Look for any .wv files in the directory
    available_embeddings = list(embeddings_dir.glob("*.wv"))
    print(f"Found {len(available_embeddings)} embedding files:")
    for emb in available_embeddings:
        size_mb = emb.stat().st_size / (1024 * 1024)
        print(f"  - {emb.name} ({size_mb:.1f} MB)")
    sys.stdout.flush()
    print()
    
    # Try common embedding names, but also include any found
    methods = {
        "multitask_embeddings": embeddings_dir / "multitask_embeddings.wv",
        "trained_validated": embeddings_dir / "trained_validated.wv",
        "deepwalk": embeddings_dir / "deepwalk.wv",
        "node2vec_default": embeddings_dir / "node2vec_default.wv",
        "node2vec_bfs": embeddings_dir / "node2vec_bfs.wv",
        "node2vec_dfs": embeddings_dir / "node2vec_dfs.wv",
        "magic_128d_test_pecanpy": embeddings_dir / "magic_128d_test_pecanpy.wv",
    }
    
    # Add any other .wv files found
    for emb_path in available_embeddings:
        if emb_path.name not in [p.name for p in methods.values()]:
            methods[emb_path.stem] = emb_path
    
    total_methods = len([p for p in methods.values() if p.exists()])
    current_method = 0
    
    for method_name, embed_path in methods.items():
        if not embed_path.exists():
            continue
        
        current_method += 1
        print(f"[{current_method}/{total_methods}] Evaluating {method_name}...")
        print(f"  Loading from {embed_path}")
        sys.stdout.flush()
        try:
            wv = KeyedVectors.load(str(embed_path))
            print(f"  Loaded vocabulary: {len(wv)} vectors")
            sys.stdout.flush()
            
            if args.confidence_intervals and not args.fast:
                # Use confidence interval evaluation
                try:
                    # Try both locations for evaluate_with_confidence
                    try:
                        from ml.utils.evaluation_with_ci import evaluate_with_confidence
                    except ImportError:
                        from ml.utils.evaluation import evaluate_with_confidence
                    
                    def similarity_func(query: str, k: int) -> list[tuple[str, float]]:
                        """Similarity function for evaluation."""
                        mapped_query = name_mapper.map_name(query) if name_mapper else query
                        if mapped_query not in wv:
                            # Return empty list if query not in vocabulary
                            return []
                        try:
                            similar = wv.most_similar(mapped_query, topn=k)
                            return similar
                        except KeyError:
                            return []
                    
                    # Convert canonical format to flat format for evaluate_with_confidence
                    # Canonical: dict[str, dict] -> Flat: dict[str, list[str]]
                    flat_test_set = {}
                    for query, labels in test_set.items():
                        if isinstance(labels, dict):
                            # Combine all relevant cards (excluding irrelevant)
                            all_relevant = []
                            for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant"]:
                                all_relevant.extend(labels.get(level, []))
                            if all_relevant:
                                flat_test_set[query] = all_relevant
                    
                    # Track vocabulary coverage
                    vocab_coverage = {
                        "total_queries": len(test_set),
                        "found_in_vocab": 0,
                        "not_in_vocab": 0,
                    }
                    
                    # Check coverage before evaluation
                    for query in test_set.keys():
                        mapped_query = name_mapper.map_name(query) if name_mapper else query
                        if mapped_query in wv:
                            vocab_coverage["found_in_vocab"] += 1
                        else:
                            vocab_coverage["not_in_vocab"] += 1
                    
                    # Use evaluate_with_confidence - it expects dict[str, list[str]] format
                    print(f"  Running evaluation with confidence intervals (n_bootstrap={args.n_bootstrap})...")
                    print(f"  This may take a few minutes for large test sets...")
                    sys.stdout.flush()
                    metrics = evaluate_with_confidence(
                        flat_test_set,  # Converted to flat format
                        similarity_func,
                        top_k=10,
                        n_bootstrap=args.n_bootstrap,
                        confidence=0.95,
                        verbose=False,  # Disable verbose to avoid per-query spam
                    )
                    print(f"  Evaluation complete")
                    sys.stdout.flush()
                    # Convert to expected format
                    metrics = {
                        "p@10": metrics.get("p@10", metrics.get("mean", 0.0)),
                        "p@10_ci_lower": metrics.get("p@10_ci_lower", metrics.get("ci_lower", 0.0)),
                        "p@10_ci_upper": metrics.get("p@10_ci_upper", metrics.get("ci_upper", 0.0)),
                        "mrr": metrics.get("mrr@10", 0.0),
                        "mrr_ci_lower": metrics.get("mrr@10_ci_lower", 0.0),
                        "mrr_ci_upper": metrics.get("mrr@10_ci_upper", 0.0),
                        "num_queries": len(test_set),
                        "num_evaluated": metrics.get("num_evaluated", metrics.get("n_queries", 0)),
                        "vocab_coverage": vocab_coverage,
                    }
                    print(f"  P@10: {metrics['p@10']:.4f} (95% CI: {metrics['p@10_ci_lower']:.4f}, {metrics['p@10_ci_upper']:.4f})")
                    print(f"  MRR: {metrics['mrr']:.4f} (95% CI: {metrics['mrr_ci_lower']:.4f}, {metrics['mrr_ci_upper']:.4f})")
                    print(f"  Queries: {metrics['num_evaluated']}")
                    if 'vocab_coverage' in metrics:
                        cov = metrics['vocab_coverage']
                        print(f"  Coverage: {cov.get('found_in_vocab', 0)}/{cov.get('total_queries', 0)} in vocab")
                except ImportError as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"  Confidence intervals not available: {e}, using standard evaluation")
                    metrics = evaluate_embedding(
                        wv, 
                        test_set, 
                        top_k=10, 
                        name_mapper=name_mapper,
                        per_query=args.per_query,
                        verbose=args.per_query,  # Verbose if per-query requested
                    )
                    print(f"  P@10: {metrics['p@10']:.4f}, MRR: {metrics['mrr']:.4f}, Queries: {metrics.get('num_evaluated', metrics.get('num_queries', 0))}")
                    if 'vocab_coverage' in metrics:
                        cov = metrics['vocab_coverage']
                        print(f"  Coverage: {cov.get('found_in_vocab', 0)}/{cov.get('total_queries', 0)} in vocab")
                    sys.stdout.flush()
            else:
                # Standard evaluation
                print(f"  Running standard evaluation...")
                sys.stdout.flush()
                metrics = evaluate_embedding(
                    wv, 
                    test_set, 
                    top_k=10, 
                    name_mapper=name_mapper,
                    verbose=False,
                )
                print(f"  P@10: {metrics['p@10']:.4f}, MRR: {metrics['mrr']:.4f}, Queries: {metrics.get('num_evaluated', metrics.get('num_queries', 0))}")
                if 'vocab_coverage' in metrics:
                    cov = metrics['vocab_coverage']
                    print(f"  Coverage: {cov.get('found_in_vocab', 0)}/{cov.get('total_queries', 0)} in vocab")
                sys.stdout.flush()
            
            results[method_name] = metrics
            print(f"  ✓ {method_name} complete")
            sys.stdout.flush()
            
            # Track in Aim
            if aim_run and track_evaluation_metrics:
                track_evaluation_metrics(
                    aim_run,
                    p10=metrics['p@10'],
                    ndcg=None,  # Not computed in this script
                    mrr=metrics['mrr'],
                    method=method_name,
                )
        except Exception as e:
            import traceback
            print(f"  Error: {e}")
            if args.per_query:
                traceback.print_exc()
            results[method_name] = {"error": str(e)}
            sys.stdout.flush()
        print()
        sys.stdout.flush()
    
    # Evaluate Jaccard baseline
    from ml.utils.paths import PATHS
    pairs_csv = Path(args.pairs_csv) if args.pairs_csv else (PATHS.pairs_large if PATHS.pairs_large.exists() else None)
    graph_db = Path(args.graph_db) if args.graph_db else (PATHS.incremental_graph_db if PATHS.incremental_graph_db.exists() else None)
    
    if (pairs_csv and pairs_csv.exists()) or (graph_db and graph_db.exists()):
        print("Evaluating Jaccard (baseline)...")
        sys.stdout.flush()
        try:
            adj = load_graph_for_jaccard(
                pairs_csv=pairs_csv,
                graph_db=graph_db,
                game=args.game,
            )
            metrics = evaluate_jaccard(adj, test_set, name_mapper=name_mapper, verbose=False)
            results["jaccard"] = metrics
            
            # Track in Aim
            if aim_run and track_evaluation_metrics:
                track_evaluation_metrics(
                    aim_run,
                    p10=metrics['p@10'],
                    ndcg=None,
                    mrr=metrics['mrr'],
                    method="jaccard",
                )
            
            print(f"  P@10: {metrics['p@10']:.4f}, MRR: {metrics['mrr']:.4f}, Queries: {metrics.get('num_evaluated', metrics.get('num_queries', 0))}")
            if 'vocab_coverage' in metrics:
                cov = metrics['vocab_coverage']
                print(f"  Coverage: {cov.get('found_in_graph', 0)}/{cov.get('total_queries', 0)} in graph")
            sys.stdout.flush()
        except Exception as e:
            print(f"  Error: {e}")
            results["jaccard"] = {"error": str(e)}
            sys.stdout.flush()
    else:
        print(f"Warning: Pairs CSV not found: {pairs_csv}, skipping Jaccard")
        sys.stdout.flush()
    
    print()
    print("=" * 70)
    print("Results Summary")
    print("=" * 70)
    print()
    sys.stdout.flush()
    
    # Sort by P@10
    sorted_results = sorted(
        [(k, v) for k, v in results.items() if "error" not in v],
        key=lambda x: x[1].get("p@10", 0.0),
        reverse=True,
    )
    
    print(f"{'Method':<25} {'P@10':<12} {'MRR':<12} {'Queries':<10} {'Coverage':<12}")
    print("-" * 75)
    for method, metrics in sorted_results:
        coverage_str = "N/A"
        if 'vocab_coverage' in metrics:
            cov = metrics['vocab_coverage']
            total = cov.get('total_queries', 0)
            found = cov.get('found_in_vocab', cov.get('found_in_graph', 0))
            coverage_str = f"{found}/{total}" if total > 0 else "N/A"
        elif 'num_evaluated' in metrics and 'num_queries' in metrics:
            eval_count = metrics.get('num_evaluated', 0)
            total_count = metrics.get('num_queries', len(test_set) if 'test_set' in locals() else 0)
            coverage_str = f"{eval_count}/{total_count}" if total_count > 0 else "N/A"
        
        p10 = metrics.get('p@10', 0.0)
        mrr = metrics.get('mrr', metrics.get('mrr@10', 0.0))
        queries = metrics.get('num_evaluated', metrics.get('num_queries', 0))
        
        print(
            f"{method:<25} {p10:<12.4f} {mrr:<12.4f} {queries:<10} {coverage_str:<12}"
        )
    sys.stdout.flush()
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\nSaving results to {output_path}...")
    sys.stdout.flush()
    
    # Prepare results with standard format
    output_data = {
        "test_set": str(test_set_path),
        "results": results,
        "summary": {
            "best_p@10": sorted_results[0][1].get("p@10", 0.0) if sorted_results else 0.0,
            "best_method": sorted_results[0][0] if sorted_results else None,
        },
    }
    
    # Add confidence intervals if per-query results available
    try:
        from ml.evaluation.confidence_intervals_integration import add_confidence_intervals_to_evaluation_results
        
        # Extract per-query metrics from results if available
        per_query_metrics = {}
        for method_name, method_results in results.items():
            if "per_query_results" in method_results:
                per_query_metrics[method_name] = method_results["per_query_results"]
        
        # Add CIs to summary metrics
        if per_query_metrics:
            best_method = sorted_results[0][0] if sorted_results else None
            if best_method and best_method in per_query_metrics:
                best_metrics = results[best_method]
                best_metrics_with_ci = add_confidence_intervals_to_evaluation_results(
                    evaluation_results=best_metrics,
                    per_query_metrics=per_query_metrics[best_method],
                )
                output_data["summary"]["best_metrics_with_ci"] = best_metrics_with_ci
    except Exception:
        # Don't fail if CI integration fails
        pass
    
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print()
    print(f"Results saved to {output_path}")
    
    # Auto-generate quality dashboard if requested
    if args.generate_dashboard or (args.output and "experiments" in str(args.output)):
        try:
            from ml.evaluation.quality_dashboard import compute_system_health, generate_dashboard_html
            
            # Create dashboard from evaluation results
            health = compute_system_health(
                evaluation_results_path=output_path,
            )
            dashboard_path = output_path.parent / f"{output_path.stem}_dashboard.html"
            generate_dashboard_html(health, dashboard_path)
            print(f"Quality dashboard: {dashboard_path}")
        except Exception:
            # Don't fail if dashboard generation fails
            pass
    
    print("=" * 70)
    print("Evaluation complete!")
    print("=" * 70)
    sys.stdout.flush()
    
    # Register evaluation in registry (if available)
    try:
        try:
            from ml.utils.evaluation_registry import EvaluationRegistry
        except ImportError:
            from ..utils.evaluation_registry import EvaluationRegistry
        
        # Extract version from output path or use timestamp
        version = None
        if "_v" in output_path.stem:
            version = output_path.stem.split("_v")[-1]
        else:
            version = datetime.now().strftime("%Y-W%V")
        
        # Determine best embedding path from results
        best_method = sorted_results[0][0] if sorted_results else None
        best_embedding_path = None
        if best_method and best_method != "Jaccard":
            # Try to find the embedding file for the best method
            embeddings_dir = Path(args.embeddings_dir)
            if embeddings_dir.exists():
                # Common naming patterns
                for pattern in [f"{best_method.lower()}.wv", f"{best_method}.wv", f"*{best_method.lower()}*.wv"]:
                    matches = list(embeddings_dir.glob(pattern))
                    if matches:
                        best_embedding_path = str(matches[0])
                        break
        
        registry = EvaluationRegistry()
        registry.record_evaluation(
            model_type="embedding_comparison",
            model_version=version,
            model_path=best_embedding_path or "multiple_embeddings",
            evaluation_results={
                "test_set": str(test_set_path),
                "results": results,
                "summary": {
                    "best_p@10": sorted_results[0][1].get("p@10", 0.0) if sorted_results else 0.0,
                    "best_method": best_method,
                },
            },
            test_set_path=str(test_set_path),
            metadata={
                "embeddings_dir": str(args.embeddings_dir),
                "game": args.game,
                "graph_db": str(args.graph_db) if args.graph_db else None,
                "pairs_csv": str(args.pairs_csv) if args.pairs_csv else None,
                "methods_evaluated": list(results.keys()),
            },
        )
        print(f"✓ Evaluation registered in model registry (version: {version})")
    except Exception as e:
        # Don't fail evaluation if registry fails
        print(f"Warning: Failed to register evaluation in registry: {e}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

