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
from pathlib import Path
from typing import Any

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
    with open(test_set_path) as f:
        data = json.load(f)
        # Handle both formats: direct dict or wrapped in "queries"
        if "queries" in data:
            return data["queries"]
        return data


def jaccard_similarity(set1: set[str], set2: set[str]) -> float:
    """Compute Jaccard similarity."""
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def load_graph_for_jaccard(pairs_csv: Path) -> dict[str, set[str]]:
    """Load graph adjacency for Jaccard similarity."""
    print(f"Loading graph from {pairs_csv}...")
    df = pd.read_csv(pairs_csv)
    
    adj: dict[str, set[str]] = {}
    for _, row in df.iterrows():
        card1, card2 = row["NAME_1"], row["NAME_2"]
        if card1 not in adj:
            adj[card1] = set()
        if card2 not in adj:
            adj[card2] = set()
        adj[card1].add(card2)
        adj[card2].add(card1)
    
    print(f"  Loaded {len(adj):,} cards")
    return adj


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
            print(f"\n⚠️  No queries evaluated! Coverage: {vocab_coverage}")
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
        print(f"\n⚠️  Skipped {len(skipped_queries)} queries:")
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
            print(f"\n⚠️  No queries evaluated! Coverage: {vocab_coverage}")
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
        print(f"\n⚠️  Skipped {len(skipped_queries)} queries:")
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
        default="experiments/test_set_canonical_magic.json",
        help="Test set path",
    )
    parser.add_argument(
        "--pairs-csv",
        type=str,
        default="data/processed/pairs_large.csv",
        help="Pairs CSV for Jaccard",
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
        default="experiments/name_mapping.json",
        help="Name mapping JSON (optional)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="experiments/embedding_comparison.json",
        help="Output JSON file",
    )
    parser.add_argument(
        "--confidence-intervals",
        action="store_true",
        help="Compute bootstrap confidence intervals (recommended)",
    )
    parser.add_argument(
        "--per-query",
        action="store_true",
        help="Include per-query breakdown in output",
    )
    
    args = parser.parse_args()
    
    if not HAS_DEPS:
        print("❌ Missing dependencies")
        return 1
    
    print("=" * 70)
    print("Evaluate All Embedding Methods")
    print("=" * 70)
    print()
    
    # Load test set
    test_set_path = Path(args.test_set)
    if not test_set_path.exists():
        print(f"❌ Test set not found: {test_set_path}")
        return 1
    
    test_set = load_test_set(test_set_path)
    print(f"📊 Loaded test set: {len(test_set)} queries")
    
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
            print(f"📊 Loading name mapping from {mapping_path}")
            name_mapper = NameMapper.load_from_file(mapping_path)
            print(f"  Loaded {len(name_mapper.mapping)} name mappings")
        except ImportError:
            print(f"⚠️  NameMapper not available, proceeding without name mapping")
    else:
        print(f"⚠️  No name mapping found at {mapping_path}, proceeding without mapping")
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
    methods = {
        "trained_validated": embeddings_dir / "trained_validated.wv",  # New embeddings with validation
        "deepwalk": embeddings_dir / "deepwalk.wv",
        "node2vec_default": embeddings_dir / "node2vec_default.wv",
        "node2vec_bfs": embeddings_dir / "node2vec_bfs.wv",
        "node2vec_dfs": embeddings_dir / "node2vec_dfs.wv",
        "magic_128d_test_pecanpy": embeddings_dir / "magic_128d_test_pecanpy.wv",
    }
    
    for method_name, embed_path in methods.items():
        if not embed_path.exists():
            print(f"⚠️  {method_name}: {embed_path} not found, skipping")
            continue
        
        print(f"Evaluating {method_name}...")
        try:
            wv = KeyedVectors.load(str(embed_path))
            
            if args.confidence_intervals:
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
                    metrics = evaluate_with_confidence(
                        flat_test_set,  # Converted to flat format
                        similarity_func,
                        top_k=10,
                        n_bootstrap=1000,
                        confidence=0.95,
                    )
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
            else:
                # Standard evaluation
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
            
            results[method_name] = metrics
            
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
            print(f"  ❌ Error: {e}")
            results[method_name] = {"error": str(e)}
        print()
    
    # Evaluate Jaccard baseline
    pairs_csv = Path(args.pairs_csv)
    if pairs_csv.exists():
        print("Evaluating Jaccard (baseline)...")
        try:
            adj = load_graph_for_jaccard(pairs_csv)
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
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results["jaccard"] = {"error": str(e)}
    else:
        print(f"⚠️  Pairs CSV not found: {pairs_csv}, skipping Jaccard")
    
    print()
    print("=" * 70)
    print("Results Summary")
    print("=" * 70)
    print()
    
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
    
    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump({
            "test_set": str(test_set_path),
            "results": results,
            "summary": {
                "best_p@10": sorted_results[0][1].get("p@10", 0.0) if sorted_results else 0.0,
                "best_method": sorted_results[0][0] if sorted_results else None,
            },
        }, f, indent=2)
    
    print()
    print(f"✅ Results saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

