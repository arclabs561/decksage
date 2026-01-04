#!/usr/bin/env python3
"""
Cross-Validation and Ablation Study Framework for Hybrid Embeddings

Implements:
- Temporal train/val/test splits for graph data
- K-Fold cross-validation with temporal ordering
- Ablation studies for hybrid embedding components
- Statistical significance testing
- Comprehensive metrics tracking
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.model_selection import KFold

from ..data.incremental_graph import IncrementalCardGraph
from ..similarity.fusion import WeightedLateFusion, FusionWeights
from ..utils.paths import PATHS

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


@dataclass
class SplitConfig:
    """Configuration for data splits."""
    train_frac: float = 0.7
    val_frac: float = 0.15
    test_frac: float = 0.15
    temporal: bool = True  # Use temporal ordering (not random)
    seed: int = 42
    
    def __post_init__(self):
        assert abs(self.train_frac + self.val_frac + self.test_frac - 1.0) < 0.001


@dataclass
class AblationConfig:
    """Configuration for ablation studies.
    
    Tests different combinations of embedding components:
    - Co-occurrence only
    - Instruction-tuned only
    - GNN only (GraphSAGE, LightGCN, etc.)
    - All combinations
    - Full hybrid system
    """
    components: list[str] = None  # ['cooccurrence', 'instruction', 'gnn', 'jaccard', 'functional']
    fusion_weights: dict[str, float] = None
    
    def __post_init__(self):
        if self.components is None:
            self.components = ['cooccurrence', 'instruction', 'gnn', 'jaccard', 'functional']
        if self.fusion_weights is None:
            self.fusion_weights = {}


@dataclass
class CVResult:
    """Results from a single CV fold."""
    fold: int
    train_metrics: dict[str, float]
    val_metrics: dict[str, float]
    test_metrics: dict[str, float]
    config: dict[str, Any]


@dataclass
class AblationResult:
    """Results from an ablation study."""
    component_config: dict[str, bool]  # Which components are enabled
    metrics: dict[str, float]
    improvement_over_baseline: dict[str, float]


class TemporalSplitter:
    """Split graph data by temporal ordering."""
    
    def __init__(self, config: SplitConfig):
        self.config = config
    
    def split_decks(
        self,
        decks: list[dict[str, Any]],
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """
        Split decks by temporal ordering.
        
        Args:
            decks: List of deck dicts with 'timestamp' field
            
        Returns:
            (train_decks, val_decks, test_decks)
        """
        # Sort by timestamp
        sorted_decks = sorted(
            decks,
            key=lambda d: datetime.fromisoformat(
                d.get('timestamp', d.get('created_at', d.get('date', datetime.now().isoformat())))
                .replace('Z', '+00:00')
            )
        )
        
        n = len(sorted_decks)
        train_end = int(n * self.config.train_frac)
        val_end = train_end + int(n * self.config.val_frac)
        
        train_decks = sorted_decks[:train_end]
        val_decks = sorted_decks[train_end:val_end]
        test_decks = sorted_decks[val_end:]
        
        logger.info(f"Temporal split: {len(train_decks)} train, {len(val_decks)} val, {len(test_decks)} test")
        return train_decks, val_decks, test_decks
    
    def split_graph_edges(
        self,
        graph: IncrementalCardGraph,
    ) -> tuple[IncrementalCardGraph, IncrementalCardGraph, IncrementalCardGraph]:
        """
        Split graph edges by temporal ordering.
        
        Args:
            graph: IncrementalCardGraph to split
            
        Returns:
            (train_graph, val_graph, test_graph)
        """
        # Sort edges by first_seen timestamp
        sorted_edges = sorted(
            graph.edges.items(),
            key=lambda x: x[1].first_seen
        )
        
        n = len(sorted_edges)
        train_end = int(n * self.config.train_frac)
        val_end = train_end + int(n * self.config.val_frac)
        
        train_edges = dict(sorted_edges[:train_end])
        val_edges = dict(sorted_edges[train_end:val_end])
        test_edges = dict(sorted_edges[val_end:])
        
        # Create subgraphs
        train_graph = IncrementalCardGraph(None)
        val_graph = IncrementalCardGraph(None)
        test_graph = IncrementalCardGraph(None)
        
        # Copy nodes (all graphs share same nodes)
        train_graph.nodes = graph.nodes.copy()
        val_graph.nodes = graph.nodes.copy()
        test_graph.nodes = graph.nodes.copy()
        
        # Assign edges
        train_graph.edges = train_edges
        val_graph.edges = val_edges
        test_graph.edges = test_edges
        
        return train_graph, val_graph, test_graph


class CrossValidator:
    """K-Fold cross-validation for hybrid embeddings."""
    
    def __init__(self, n_folds: int = 5, temporal: bool = True, seed: int = 42):
        self.n_folds = n_folds
        self.temporal = temporal
        self.seed = seed
        self.kfold = KFold(n_splits=n_folds, shuffle=not temporal, random_state=seed)
    
    def cv_fold_decks(
        self,
        decks: list[dict[str, Any]],
        fold: int,
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """
        Get train/val/test split for a specific fold.
        
        Args:
            decks: List of deck dicts
            fold: Fold index (0 to n_folds-1)
            
        Returns:
            (train_decks, val_decks, test_decks)
        """
        if self.temporal:
            # Temporal split: use first (n_folds-1)/n_folds for train, rest for val/test
            sorted_decks = sorted(
                decks,
                key=lambda d: datetime.fromisoformat(
                    d.get('timestamp', d.get('created_at', d.get('date', datetime.now().isoformat())))
                    .replace('Z', '+00:00')
                )
            )
            
            n = len(sorted_decks)
            # For k-fold, we use (k-1)/k for train, 1/k for test
            # Then split test into val and test
            train_size = int(n * (self.n_folds - 1) / self.n_folds)
            test_size = n - train_size
            
            # Shift window for each fold
            fold_size = n // self.n_folds
            start_idx = fold * fold_size
            end_idx = start_idx + test_size
            
            if end_idx > n:
                # Wrap around
                train_decks = sorted_decks[end_idx:] + sorted_decks[:start_idx]
                test_decks = sorted_decks[start_idx:end_idx]
            else:
                train_decks = sorted_decks[:start_idx] + sorted_decks[end_idx:]
                test_decks = sorted_decks[start_idx:end_idx]
            
            # Split test into val and test
            val_size = int(len(test_decks) * 0.5)
            val_decks = test_decks[:val_size]
            test_decks = test_decks[val_size:]
            
        else:
            # Random k-fold
            indices = np.arange(len(decks))
            train_indices, test_indices = list(self.kfold.split(indices))[fold]
            
            # Split test into val and test
            np.random.seed(self.seed)
            np.random.shuffle(test_indices)
            val_size = len(test_indices) // 2
            val_indices = test_indices[:val_size]
            test_indices = test_indices[val_size:]
            
            train_decks = [decks[i] for i in train_indices]
            val_decks = [decks[i] for i in val_indices]
            test_decks = [decks[i] for i in test_indices]
        
        return train_decks, val_decks, test_decks


class AblationStudy:
    """Ablation study framework for hybrid embeddings."""
    
    def __init__(self, config: AblationConfig):
        self.config = config
    
    def generate_ablation_configs(self) -> list[dict[str, bool]]:
        """
        Generate all ablation study configurations.
        
        Returns:
            List of config dicts, each specifying which components are enabled
        """
        components = self.config.components
        configs = []
        
        # Single component
        for comp in components:
            configs.append({c: (c == comp) for c in components})
        
        # Pairs
        for i, comp1 in enumerate(components):
            for comp2 in components[i+1:]:
                configs.append({c: (c in [comp1, comp2]) for c in components})
        
        # All components
        configs.append({c: True for c in components})
        
        # Baseline (none)
        configs.append({c: False for c in components})
        
        return configs
    
    def create_fusion_weights(
        self,
        component_config: dict[str, bool],
    ) -> FusionWeights:
        """
        Create fusion weights based on component configuration.
        
        Args:
            component_config: Dict mapping component names to enabled/disabled
            
        Returns:
            FusionWeights object
        """
        # Default weights when all enabled
        default_weights = {
            'cooccurrence': 0.20,
            'instruction': 0.25,
            'gnn': 0.30,
            'jaccard': 0.15,
            'functional': 0.10,
        }
        
        # Get enabled components
        enabled = [c for c, enabled in component_config.items() if enabled]
        
        if not enabled:
            # All disabled - return zero weights
            return FusionWeights()
        
        # Normalize weights for enabled components only
        total = sum(default_weights.get(c, 0.0) for c in enabled)
        if total == 0:
            # Equal weights
            weight_per = 1.0 / len(enabled)
            weights = {c: weight_per if c in enabled else 0.0 for c in component_config.keys()}
        else:
            weights = {
                c: (default_weights.get(c, 0.0) / total) if c in enabled else 0.0
                for c in component_config.keys()
            }
        
        return FusionWeights(
            embed=weights.get('cooccurrence', 0.0),
            text_embed=weights.get('instruction', 0.0),
            gnn=weights.get('gnn', 0.0),
            jaccard=weights.get('jaccard', 0.0),
            functional=weights.get('functional', 0.0),
        )


def evaluate_ablation(
    test_set: dict[str, Any],
    fusion_system: WeightedLateFusion,
    top_k: int = 10,
) -> dict[str, float]:
    """
    Evaluate fusion system on test set.
    
    Args:
        test_set: Test set dict with queries and labels
        fusion_system: WeightedLateFusion system to evaluate
        top_k: Top K for precision metrics
        
    Returns:
        Dict of metrics
    """
    from ..scripts.evaluate_all_embeddings import evaluate_embedding
    
    # Wrap fusion system for evaluate_embedding interface
    class FusionWrapper:
        def __init__(self, fusion: WeightedLateFusion):
            self.fusion = fusion
            self.vector_size = 128  # Dummy
            self.index_to_key = []
        
        def most_similar(self, query: str, topn: int = 10) -> list[tuple[str, float]]:
            return self.fusion.most_similar(query, topn=topn)
        
        def __contains__(self, card_name: str) -> bool:
            return True  # Fusion can handle any card via text embedder
    
    wrapper = FusionWrapper(fusion_system)
    results = evaluate_embedding(wrapper, test_set, top_k=top_k, verbose=False)
    
    return {
        'p_at_10': results.get('mean_p_at_k', 0.0),
        'p_at_5': results.get('p_at_5', 0.0),
        'mrr': results.get('mean_reciprocal_rank', 0.0),
        'ndcg': results.get('mean_ndcg', 0.0),
    }


def run_ablation_study(
    test_set_path: Path,
    graph_path: Path,
    gnn_path: Path | None = None,
    cooccurrence_path: Path | None = None,
    output_path: Path | None = None,
) -> list[AblationResult]:
    """
    Run full ablation study on hybrid embedding system.
    
    Args:
        test_set_path: Path to test set JSON
        graph_path: Path to incremental graph JSON
        gnn_path: Path to GNN embeddings JSON (optional)
        cooccurrence_path: Path to co-occurrence embeddings .wv (optional)
        output_path: Path to save results JSON (optional)
        
    Returns:
        List of AblationResult objects
    """
    logger.info("="*70)
    logger.info("ABLATION STUDY: Hybrid Embedding System")
    logger.info("="*70)
    
    # Load test set
    with open(test_set_path) as f:
        test_set = json.load(f)
    logger.info(f"Loaded test set: {len(test_set)} queries")
    
    # Load graph
    graph = IncrementalCardGraph(graph_path)
    logger.info(f"Loaded graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    
    # Initialize ablation study
    ablation = AblationStudy(AblationConfig())
    configs = ablation.generate_ablation_configs()
    logger.info(f"Generated {len(configs)} ablation configurations")
    
    results = []
    
    for i, component_config in enumerate(configs):
        logger.info(f"\n--- Ablation Config {i+1}/{len(configs)} ---")
        logger.info(f"Components: {component_config}")
        
        # Create fusion weights
        weights = ablation.create_fusion_weights(component_config)
        
        # Load components based on config
        cooccurrence_embeddings = None
        instruction_embedder = None
        gnn_embedder = None
        adj = {}
        tagger = None
        
        try:
            # Load co-occurrence embeddings
            if component_config.get('cooccurrence'):
                from gensim.models import KeyedVectors
                from ml.utils.paths import PATHS
                cooccurrence_path = PATHS.embeddings / "node2vec_default.wv"
                if cooccurrence_path.exists():
                    cooccurrence_embeddings = KeyedVectors.load(str(cooccurrence_path))
                    logger.info("  Loaded co-occurrence embeddings")
            
            # Load instruction-tuned embedder
            if component_config.get('instruction'):
                try:
                    from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
                    instruction_embedder = InstructionTunedCardEmbedder(model_name="intfloat/e5-base-v2")
                    logger.info("  Loaded instruction-tuned embedder")
                except Exception as e:
                    logger.warning(f"  Could not load instruction embedder: {e}")
            
            # Load GNN embedder
            if component_config.get('gnn'):
                try:
                    from ml.similarity.gnn_embeddings import CardGNNEmbedder
                    gnn_path = PATHS.embeddings / "gnn_graphsage.json"
                    if gnn_path.exists():
                        gnn_embedder = CardGNNEmbedder.load(str(gnn_path))
                        logger.info("  Loaded GNN embedder")
                except Exception as e:
                    logger.warning(f"  Could not load GNN embedder: {e}")
            
            # Load graph for Jaccard
            if component_config.get('jaccard'):
                try:
                    from ml.utils.shared_operations import load_graph_for_jaccard
                    adj = load_graph_for_jaccard(graph_db=PATHS.incremental_graph_db)
                    logger.info(f"  Loaded Jaccard graph: {len(adj)} cards")
                except Exception as e:
                    logger.warning(f"  Could not load Jaccard graph: {e}")
            
            # Load functional tagger
            if component_config.get('functional'):
                try:
                    from ml.enrichment.card_functional_tagger import FunctionalTagger
                    tagger = FunctionalTagger()
                    logger.info("  Loaded functional tagger")
                except Exception as e:
                    logger.warning(f"  Could not load functional tagger: {e}")
            
            # Create fusion system
            from ml.similarity.fusion import WeightedLateFusion, FusionWeights
            
            fusion_weights = FusionWeights(
                embed=weights.get('cooccurrence', 0.0),
                jaccard=weights.get('jaccard', 0.0),
                functional=weights.get('functional', 0.0),
                text_embed=weights.get('instruction', 0.0),
                gnn=weights.get('gnn', 0.0),
            ).normalized()
            
            fusion = WeightedLateFusion(
                embeddings=cooccurrence_embeddings,
                adj=adj,
                tagger=tagger,
                weights=fusion_weights,
                text_embedder=instruction_embedder,
                gnn_embedder=gnn_embedder,
            )
            
            # Evaluate if test set available (check both parameter and graph metadata)
            test_set = None
            if test_set_path and Path(test_set_path).exists():
                test_set = Path(test_set_path)
            elif hasattr(graph, 'test_set_path') and graph.test_set_path:
                test_set = Path(graph.test_set_path)
            
            if test_set and test_set.exists():
                from ml.scripts.evaluate_all_embeddings import evaluate_embedding
                import json
                
                with open(test_set_path) as f:
                    test_data = json.load(f)
                test_set = test_data.get("queries", test_data)
                
                # Create KeyedVectors wrapper for fusion
                class FusionKeyedVectors:
                    def __init__(self, fusion: WeightedLateFusion):
                        self.fusion = fusion
                    
                    def __contains__(self, key: str) -> bool:
                        return True  # Fusion handles OOV
                    
                    def similarity(self, word1: str, word2: str) -> float:
                        return self.fusion.similarity(word1, word2)
                    
                    def most_similar(self, word: str, topn: int = 10) -> list[tuple[str, float]]:
                        return self.fusion.most_similar(word, topn=topn)
                
                fusion_wv = FusionKeyedVectors(fusion)
                eval_results = evaluate_embedding(fusion_wv, test_set, top_k=10, per_query=False)
                
                metrics = {
                    'p_at_10': eval_results.get('p@10', 0.0),
                    'p_at_5': eval_results.get('p@5', 0.0),
                    'mrr': eval_results.get('mrr', 0.0),
                    'ndcg': eval_results.get('ndcg', 0.0),
                }
                logger.info(f"  Evaluation: P@10={metrics['p_at_10']:.4f}, MRR={metrics['mrr']:.4f}")
            else:
                # No test set - use placeholder
                metrics = {
                    'p_at_10': 0.0,
                    'p_at_5': 0.0,
                    'mrr': 0.0,
                    'ndcg': 0.0,
                }
                logger.warning("  No test set provided - using placeholder metrics")
                
        except Exception as e:
            from ..utils.logging_config import log_exception
            log_exception(logger, "Failed to load fusion components", e, include_context=True)
            metrics = {
                'p_at_10': 0.0,
                'p_at_5': 0.0,
                'mrr': 0.0,
                'ndcg': 0.0,
            }
        
        result = AblationResult(
            component_config=component_config,
            metrics=metrics,
            improvement_over_baseline={},
        )
        results.append(result)
    
    # Calculate improvements over baseline
    baseline_metrics = results[-1].metrics if results else {}
    for result in results:
        result.improvement_over_baseline = {
            metric: result.metrics[metric] - baseline_metrics.get(metric, 0.0)
            for metric in result.metrics.keys()
        }
    
    # Save results
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump([asdict(r) for r in results], f, indent=2)
        logger.info(f"Saved ablation results to {output_path}")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run ablation study on hybrid embeddings")
    parser.add_argument("--test-set", type=Path, default=PATHS.test_magic, help="Test set path")
    parser.add_argument("--graph", type=Path, default=PATHS.graphs / "incremental_graph.db", help="Graph path (SQLite .db or JSON .json)")
    parser.add_argument("--gnn", type=Path, default=PATHS.embeddings / "gnn_graphsage.json", help="GNN embeddings path")
    parser.add_argument("--cooccurrence", type=Path, default=PATHS.embeddings / "production.wv", help="Co-occurrence embeddings path")
    parser.add_argument("--output", type=Path, default=PATHS.experiments / "ablation_results.json", help="Output path")
    
    args = parser.parse_args()
    
    # Logging already configured via get_logger above
    
    results = run_ablation_study(
        test_set_path=args.test_set,
        graph_path=args.graph,
        gnn_path=args.gnn,
        cooccurrence_path=args.cooccurrence,
        output_path=args.output,
    )
    
    logger.info(f"\nAblation study complete: {len(results)} configurations tested")

