#!/usr/bin/env python3
"""
Training/Evaluation Leakage Analysis

Identifies and documents potential data leakage points in the hybrid embedding system.
Leakage occurs when test/validation data influences training, leading to overly optimistic results.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..data.incremental_graph import IncrementalCardGraph
from ..utils.paths import PATHS

try:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


@dataclass
class LeakageIssue:
    """Represents a potential leakage issue."""
    severity: str  # 'critical', 'high', 'medium', 'low'
    location: str  # File/function where issue occurs
    description: str
    impact: str
    recommendation: str
    fixed: bool = False


class LeakageAnalyzer:
    """Analyzes the codebase for potential data leakage."""
    
    def __init__(self):
        self.issues: list[LeakageIssue] = []
    
    def analyze_graph_construction(self, graph_path: Path, decks_path: Path) -> list[LeakageIssue]:
        """
        Analyze graph construction for leakage.
        
        Issue: If graph is built from ALL decks (including test period),
        then test data influences training.
        """
        issues = []
        
        # Check if graph includes all decks
        graph = IncrementalCardGraph(graph_path)
        
        # Load decks to check timestamps
        if decks_path.exists():
            with open(decks_path) as f:
                decks = [json.loads(line) for line in f if line.strip()]
            
            # Extract timestamps
            timestamps = []
            for deck in decks:
                ts_str = deck.get('timestamp') or deck.get('created_at') or deck.get('date')
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                        timestamps.append(ts)
                    except:
                        pass
            
            if timestamps:
                min_ts = min(timestamps)
                max_ts = max(timestamps)
                
                # Check if graph edges span entire time period
                graph_edge_times = [
                    edge.first_seen for edge in graph.edges.values()
                ]
                if graph_edge_times:
                    graph_min_ts = min(graph_edge_times)
                    graph_max_ts = max(graph_edge_times)
                    
                    # If graph includes all time periods, there's potential leakage
                    if graph_min_ts <= min_ts and graph_max_ts >= max_ts:
                        issues.append(LeakageIssue(
                            severity='critical',
                            location='build_incremental_graph()',
                            description='Graph is built from ALL decks including test period. Test data influences training embeddings.',
                            impact='Co-occurrence and GNN embeddings trained on test data → inflated performance metrics',
                            recommendation='Split decks by timestamp BEFORE building graph. Only use train/val decks for graph construction.',
                            fixed=False,
                        ))
        
        return issues
    
    def analyze_gnn_training(self, edgelist_path: Path, graph_path: Path) -> list[LeakageIssue]:
        """
        Analyze GNN training for leakage.
        
        Issue: If GNN is trained on edges from test period, test data influences training.
        """
        issues = []
        
        # Check if edgelist includes test period edges
        graph = IncrementalCardGraph(graph_path)
        
        # If graph was built from all decks, GNN training will leak
        # This is a consequence of graph construction leakage
        issues.append(LeakageIssue(
            severity='critical',
            location='CardGNNEmbedder.train()',
            description='GNN trained on edgelist that may include test period edges.',
            impact='GNN embeddings learned from test data → inflated performance on test set',
            recommendation='Export edgelist only from train/val graph. Ensure graph split happens before GNN training.',
            fixed=False,
        ))
        
        return issues
    
    def analyze_cooccurrence_training(self, pairs_path: Path) -> list[LeakageIssue]:
        """
        Analyze co-occurrence embedding training for leakage.
        
        Issue: If Node2Vec/PecanPy trained on pairs from test period.
        """
        issues = []
        
        # Check if pairs CSV includes test period
        # This requires knowing the split point, which we may not have
        # But we can document the issue
        issues.append(LeakageIssue(
            severity='critical',
            location='card_similarity_pecan.py / Node2Vec training',
            description='Co-occurrence embeddings may be trained on pairs from test period if pairs_large.csv includes all time periods.',
            impact='Co-occurrence embeddings learned from test data → inflated performance',
            recommendation='Filter pairs by timestamp. Only use train/val period pairs for training.',
            fixed=False,
        ))
        
        return issues
    
    def analyze_test_set_construction(self, test_set_path: Path, graph_path: Path) -> list[LeakageIssue]:
        """
        Analyze test set construction for leakage.
        
        Issue: If test set cards/edges are in the training graph.
        """
        issues = []
        
        # Load test set
        if test_set_path.exists():
            with open(test_set_path) as f:
                test_data = json.load(f)
            
            test_queries = test_data.get('queries', test_data) if isinstance(test_data, dict) else test_data
            
            # Load graph
            graph = IncrementalCardGraph(graph_path)
            
            # Check if test queries are in training graph
            test_cards_in_graph = 0
            for query in test_queries.keys():
                if query in graph.nodes:
                    test_cards_in_graph += 1
            
            if test_cards_in_graph > 0:
                # This is actually OK - we want to test on known cards
                # But we need to ensure edges aren't from test period
                issues.append(LeakageIssue(
                    severity='medium',
                    location='Test set construction',
                    description=f'{test_cards_in_graph}/{len(test_queries)} test queries are in training graph.',
                    impact='If test cards have edges from test period in graph, there is leakage.',
                    recommendation='Ensure test set cards only have edges from train/val period in graph. Or use temporal split to exclude test period edges.',
                    fixed=False,
                ))
        
        return issues
    
    def analyze_evaluation(self, evaluation_scripts: list[Path]) -> list[LeakageIssue]:
        """
        Analyze evaluation scripts for leakage.
        
        Issue: If evaluation uses training data or full graph.
        """
        issues = []
        
        # Check if evaluation uses full graph instead of train-only graph
        issues.append(LeakageIssue(
            severity='high',
            location='evaluate_hybrid_with_runctl.py',
            description='Evaluation may use full graph (including test period) for Jaccard similarity.',
            impact='Jaccard similarity computed on test period edges → inflated performance',
            recommendation='Use train-only graph for Jaccard computation during evaluation.',
            fixed=False,
        ))
        
        return issues
    
    def analyze_instruction_tuned(self) -> list[LeakageIssue]:
        """
        Analyze instruction-tuned embeddings for leakage.
        
        Note: Instruction-tuned embeddings are zero-shot, so they shouldn't have leakage
        unless test set was used during model training (unlikely for E5-base-v2).
        """
        issues = []
        
        # Instruction-tuned embeddings are pre-trained, so no leakage from our data
        # But we should verify test set wasn't in pre-training data
        issues.append(LeakageIssue(
            severity='low',
            location='InstructionTunedCardEmbedder',
            description='Instruction-tuned embeddings are pre-trained. Verify test set cards were not in E5-base-v2 pre-training data.',
            impact='If test cards were in pre-training, performance is inflated (unlikely but possible).',
            recommendation='Verify E5-base-v2 pre-training data. For card games, this is unlikely to be an issue.',
            fixed=False,
        ))
        
        return issues
    
    def analyze_feature_engineering(self) -> list[LeakageIssue]:
        """
        Analyze feature engineering for leakage.
        
        Issue: If features are computed using future data.
        """
        issues = []
        
        # Check if functional tags, LLM enrichment, etc. use future information
        issues.append(LeakageIssue(
            severity='medium',
            location='Feature engineering (functional tags, LLM enrichment)',
            description='Features may be computed using all-time data, including test period.',
            impact='If features use test period data, there is leakage.',
            recommendation='Ensure features are computed only from train/val period data. Or use features that are time-invariant (card text, type).',
            fixed=False,
        ))
        
        return issues
    
    def validate_temporal_split(
        self,
        decks: list[dict[str, Any]],
        test_period_start: datetime | None = None,
        train_frac: float = 0.7,
        val_frac: float = 0.15,
    ) -> tuple[bool, list[str]]:
        """
        Validate that temporal split is correct (no test period in training).
        
        Args:
            decks: List of deck dicts with timestamps
            test_period_start: Optional explicit test period start (if None, computed from train_frac)
            train_frac: Training fraction
            val_frac: Validation fraction
            
        Returns:
            (is_valid, list_of_warnings)
        """
        warnings = []
        
        # Extract and sort timestamps
        timestamps = []
        for deck in decks:
            ts_str = deck.get('timestamp') or deck.get('created_at') or deck.get('date') or deck.get('_parsed_timestamp')
            if ts_str:
                try:
                    if isinstance(ts_str, datetime):
                        ts = ts_str
                    else:
                        ts = datetime.fromisoformat(str(ts_str).replace('Z', '+00:00'))
                    timestamps.append((ts, deck))
                except Exception:
                    continue
        
        if not timestamps:
            warnings.append("No timestamps found in decks - cannot validate temporal split")
            return False, warnings
        
        sorted_decks = sorted(timestamps, key=lambda x: x[0])
        n = len(sorted_decks)
        
        # Compute split points
        train_end = int(n * train_frac)
        val_end = train_end + int(n * val_frac)
        
        train_decks = sorted_decks[:train_end]
        val_decks = sorted_decks[train_end:val_end]
        test_decks = sorted_decks[val_end:]
        
        if not train_decks or not test_decks:
            warnings.append("Insufficient decks for temporal split")
            return False, warnings
        
        train_max_ts = train_decks[-1][0]
        test_min_ts = test_decks[0][0]
        
        # Validate: train period ends before test period starts
        if train_max_ts >= test_min_ts:
            warnings.append(f"Temporal split violation: train period ({train_max_ts}) overlaps with test period ({test_min_ts})")
            return False, warnings
        
        return True, warnings
    
    def run_full_analysis(
        self,
        graph_path: Path,
        decks_path: Path,
        test_set_path: Path,
        pairs_path: Path | None = None,
    ) -> list[LeakageIssue]:
        """
        Run complete leakage analysis.
        
        Returns:
            List of all identified leakage issues
        """
        logger.info("="*70)
        logger.info("LEAKAGE ANALYSIS: Hybrid Embedding System")
        logger.info("="*70)
        
        all_issues = []
        
        # 1. Graph construction
        logger.info("\n1. Analyzing graph construction...")
        issues = self.analyze_graph_construction(graph_path, decks_path)
        all_issues.extend(issues)
        logger.info(f"   Found {len(issues)} issues")
        
        # 2. GNN training
        logger.info("\n2. Analyzing GNN training...")
        edgelist_path = graph_path.parent / "hybrid_training_edgelist.edg"
        issues = self.analyze_gnn_training(edgelist_path, graph_path)
        all_issues.extend(issues)
        logger.info(f"   Found {len(issues)} issues")
        
        # 3. Co-occurrence training
        if pairs_path and pairs_path.exists():
            logger.info("\n3. Analyzing co-occurrence training...")
            issues = self.analyze_cooccurrence_training(pairs_path)
            all_issues.extend(issues)
            logger.info(f"   Found {len(issues)} issues")
        
        # 4. Test set construction
        logger.info("\n4. Analyzing test set construction...")
        issues = self.analyze_test_set_construction(test_set_path, graph_path)
        all_issues.extend(issues)
        logger.info(f"   Found {len(issues)} issues")
        
        # 5. Evaluation
        logger.info("\n5. Analyzing evaluation...")
        eval_scripts = [
            PATHS.experiments.parent / "src/ml/scripts/evaluate_hybrid_with_runctl.py",
        ]
        issues = self.analyze_evaluation(eval_scripts)
        all_issues.extend(issues)
        logger.info(f"   Found {len(issues)} issues")
        
        # 6. Instruction-tuned
        logger.info("\n6. Analyzing instruction-tuned embeddings...")
        issues = self.analyze_instruction_tuned()
        all_issues.extend(issues)
        logger.info(f"   Found {len(issues)} issues")
        
        # 7. Feature engineering
        logger.info("\n7. Analyzing feature engineering...")
        issues = self.analyze_feature_engineering()
        all_issues.extend(issues)
        logger.info(f"   Found {len(issues)} issues")
        
        # Summary
        logger.info("\n" + "="*70)
        logger.info("LEAKAGE ANALYSIS SUMMARY")
        logger.info("="*70)
        
        by_severity = defaultdict(list)
        for issue in all_issues:
            by_severity[issue.severity].append(issue)
        
        for severity in ['critical', 'high', 'medium', 'low']:
            count = len(by_severity[severity])
            if count > 0:
                logger.info(f"{severity.upper()}: {count} issues")
                for issue in by_severity[severity]:
                    logger.info(f"  - {issue.location}: {issue.description}")
        
        return all_issues


def generate_leakage_report(
    graph_path: Path,
    decks_path: Path,
    test_set_path: Path,
    pairs_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """
    Generate comprehensive leakage analysis report.
    
    Args:
        graph_path: Path to incremental graph
        decks_path: Path to decks JSONL
        test_set_path: Path to test set JSON
        pairs_path: Optional path to pairs CSV
        output_path: Optional path to save report
        
    Returns:
        Path to saved report
    """
    analyzer = LeakageAnalyzer()
    issues = analyzer.run_full_analysis(
        graph_path=graph_path,
        decks_path=decks_path,
        test_set_path=test_set_path,
        pairs_path=pairs_path,
    )
    
    # Generate report
    report = {
        'timestamp': datetime.now().isoformat(),
        'graph_path': str(graph_path),
        'decks_path': str(decks_path),
        'test_set_path': str(test_set_path),
        'pairs_path': str(pairs_path) if pairs_path else None,
        'total_issues': len(issues),
        'issues_by_severity': {
            severity: [asdict(issue) for issue in issues if issue.severity == severity]
            for severity in ['critical', 'high', 'medium', 'low']
        },
        'all_issues': [asdict(issue) for issue in issues],
    }
    
    if output_path is None:
        output_path = PATHS.experiments / "leakage_analysis_report.json"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"\nReport saved to: {output_path}")
    return output_path


def validate_temporal_split(
    decks: list[dict[str, Any]],
    test_period_start: datetime | None = None,
    train_frac: float = 0.7,
    val_frac: float = 0.15,
) -> tuple[bool, list[str]]:
    """
    Validate temporal split to prevent data leakage.
    
    Convenience function that uses LeakageAnalyzer.
    """
    analyzer = LeakageAnalyzer()
    return analyzer.validate_temporal_split(decks, test_period_start, train_frac, val_frac)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze hybrid embedding system for data leakage")
    parser.add_argument("--graph", type=Path, default=PATHS.graphs / "incremental_graph.db", help="Graph path (SQLite .db or JSON .json)")
    parser.add_argument("--decks", type=Path, default=PATHS.decks_all_final, help="Decks JSONL path")
    parser.add_argument("--test-set", type=Path, default=PATHS.test_magic, help="Test set JSON path")
    parser.add_argument("--pairs", type=Path, default=PATHS.pairs_large, help="Pairs CSV path (optional)")
    parser.add_argument("--output", type=Path, default=PATHS.experiments / "leakage_analysis_report.json", help="Output report path")
    
    args = parser.parse_args()
    
    # Logging already configured via get_logger above
    
    generate_leakage_report(
        graph_path=args.graph,
        decks_path=args.decks,
        test_set_path=args.test_set,
        pairs_path=args.pairs if args.pairs.exists() else None,
        output_path=args.output,
    )

