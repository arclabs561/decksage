#!/usr/bin/env python3
"""
Agentic Graph Quality Assurance System

Uses LLM agents with tools to sample and validate graph data quality.
Checks for:
- Data consistency
- Label accuracy
- Edge weight validity
- Annotation quality
- Graph structure integrity
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


@dataclass
class QualityIssue:
    """Represents a quality issue found in the graph."""
    severity: str  # "critical", "warning", "info"
    category: str  # "data_quality", "consistency", "completeness", "accuracy"
    description: str
    affected_items: list[str]
    recommendation: str
    evidence: dict[str, Any] | None = None


@dataclass
class QualityReport:
    """Comprehensive quality report."""
    timestamp: str
    total_nodes: int
    total_edges: int
    issues: list[QualityIssue]
    statistics: dict[str, Any]
    sample_validations: list[dict[str, Any]]
    overall_score: float  # 0-1


class GraphQualityAgent:
    """Agentic system for graph quality assurance."""
    
    def __init__(
        self,
        graph_db: Path | None = None,
        sample_size: int = 100,
        use_llm: bool = True,
    ):
        """Initialize quality agent."""
        self.graph_db = graph_db or PATHS.incremental_graph_db
        self.sample_size = sample_size
        self.use_llm = use_llm
        self.issues: list[QualityIssue] = []
        self.statistics: dict[str, Any] = {}
        self._agentic_agent = None
        
        if use_llm:
            try:
                from .agentic_qa_agent import AgenticQAAgent
                self._agentic_agent = AgenticQAAgent(graph_db)
            except Exception as e:
                logger.debug(f"Could not initialize agentic QA agent: {e}")
                self.use_llm = False
        
    def run_quality_check(self) -> QualityReport:
        """Run comprehensive quality check."""
        logger.info("=" * 70)
        logger.info("Graph Quality Assurance Check")
        logger.info("=" * 70)
        
        # Load graph statistics
        self._collect_statistics()
        
        # Run validation checks
        self._check_data_quality()
        self._check_consistency()
        self._check_completeness()
        self._check_accuracy()
        
        # Sample validations
        sample_validations = self._sample_validate()
        
        # Calculate overall score
        overall_score = self._calculate_score()
        
        report = QualityReport(
            timestamp=datetime.now().isoformat(),
            total_nodes=self.statistics.get("total_nodes", 0),
            total_edges=self.statistics.get("total_edges", 0),
            issues=self.issues,
            statistics=self.statistics,
            sample_validations=sample_validations,
            overall_score=overall_score,
        )
        
        return report
    
    def _collect_statistics(self) -> None:
        """Collect graph statistics."""
        conn = sqlite3.connect(str(self.graph_db))
        
        # Node statistics
        node_stats = conn.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN game IS NULL OR game = 'Unknown' THEN 1 END) as unknown,
                COUNT(CASE WHEN game = 'MTG' THEN 1 END) as mtg,
                COUNT(CASE WHEN game = 'YGO' THEN 1 END) as ygo,
                COUNT(CASE WHEN game = 'PKM' THEN 1 END) as pkm,
                AVG(total_decks) as avg_decks,
                MAX(total_decks) as max_decks
            FROM nodes
        """).fetchone()
        
        # Edge statistics
        edge_stats = conn.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN game IS NULL OR game = 'Unknown' THEN 1 END) as unknown,
                AVG(weight) as avg_weight,
                MIN(weight) as min_weight,
                MAX(weight) as max_weight,
                COUNT(CASE WHEN weight > 100000 THEN 1 END) as suspicious_weights
            FROM edges
        """).fetchone()
        
        # Game distribution
        game_dist = conn.execute("""
            SELECT game, COUNT(*) as count
            FROM nodes
            GROUP BY game
            ORDER BY count DESC
        """).fetchall()
        
        conn.close()
        
        self.statistics = {
            "total_nodes": node_stats[0],
            "unknown_nodes": node_stats[1],
            "mtg_nodes": node_stats[2],
            "ygo_nodes": node_stats[3],
            "pkm_nodes": node_stats[4],
            "avg_decks_per_node": node_stats[5],
            "max_decks_per_node": node_stats[6],
            "total_edges": edge_stats[0],
            "unknown_edges": edge_stats[1],
            "avg_edge_weight": edge_stats[2],
            "min_edge_weight": edge_stats[3],
            "max_edge_weight": edge_stats[4],
            "suspicious_weights": edge_stats[5],
            "game_distribution": {game: count for game, count in game_dist},
        }
        
        logger.info(f"Statistics collected: {self.statistics['total_nodes']:,} nodes, {self.statistics['total_edges']:,} edges")
    
    def _check_data_quality(self) -> None:
        """Check data quality issues."""
        logger.info("Checking data quality...")
        
        # Check for corrupted weights
        if self.statistics.get("suspicious_weights", 0) > 0:
            self.issues.append(QualityIssue(
                severity="critical",
                category="data_quality",
                description=f"{self.statistics['suspicious_weights']} edges have suspiciously high weights (>100k)",
                affected_items=[f"{self.statistics['suspicious_weights']} edges"],
                recommendation="Run fix_corrupted_edge_weights.py to recalculate weights",
                evidence={"suspicious_count": self.statistics["suspicious_weights"]},
            ))
        
        # Check for negative weights
        if self.statistics.get("min_edge_weight", 0) < 0:
            self.issues.append(QualityIssue(
                severity="critical",
                category="data_quality",
                description="Some edges have negative weights",
                affected_items=[],
                recommendation="Investigate and fix negative weights",
                evidence={"min_weight": self.statistics["min_edge_weight"]},
            ))
        
        # Check for zero weights
        conn = sqlite3.connect(str(self.graph_db))
        zero_weight_count = conn.execute("SELECT COUNT(*) FROM edges WHERE weight = 0").fetchone()[0]
        conn.close()
        
        if zero_weight_count > 0:
            self.issues.append(QualityIssue(
                severity="warning",
                category="data_quality",
                description=f"{zero_weight_count} edges have zero weight",
                affected_items=[f"{zero_weight_count} edges"],
                recommendation="Consider removing zero-weight edges or investigating why they exist",
                evidence={"zero_weight_count": zero_weight_count},
            ))
    
    def _check_consistency(self) -> None:
        """Check consistency issues."""
        logger.info("Checking consistency...")
        
        conn = sqlite3.connect(str(self.graph_db))
        
        # Check for edges with mismatched game labels
        mismatched = conn.execute("""
            SELECT COUNT(*) 
            FROM edges e
            JOIN nodes n1 ON e.card1 = n1.name
            JOIN nodes n2 ON e.card2 = n2.name
            WHERE e.game IS NOT NULL 
              AND n1.game IS NOT NULL 
              AND n2.game IS NOT NULL
              AND (e.game != n1.game OR e.game != n2.game)
        """).fetchone()[0]
        
        # Check for nodes with no edges
        isolated_nodes = conn.execute("""
            SELECT COUNT(*) 
            FROM nodes n
            WHERE NOT EXISTS (
                SELECT 1 FROM edges e 
                WHERE e.card1 = n.name OR e.card2 = n.name
            )
        """).fetchone()[0]
        
        conn.close()
        
        if mismatched > 0:
            self.issues.append(QualityIssue(
                severity="warning",
                category="consistency",
                description=f"{mismatched} edges have game labels that don't match their nodes",
                affected_items=[f"{mismatched} edges"],
                recommendation="Run fix_graph_game_labels.py to fix game label mismatches",
                evidence={"mismatched_count": mismatched},
            ))
        
        if isolated_nodes > 0:
            self.issues.append(QualityIssue(
                severity="info",
                category="consistency",
                description=f"{isolated_nodes} nodes have no edges (isolated)",
                affected_items=[f"{isolated_nodes} nodes"],
                recommendation="Consider removing isolated nodes or investigating why they exist",
                evidence={"isolated_count": isolated_nodes},
            ))
    
    def _check_completeness(self) -> None:
        """Check completeness issues."""
        logger.info("Checking completeness...")
        
        # Check unknown nodes percentage
        total_nodes = self.statistics.get("total_nodes", 1)
        unknown_nodes = self.statistics.get("unknown_nodes", 0)
        unknown_pct = (unknown_nodes / total_nodes) * 100 if total_nodes > 0 else 0
        
        if unknown_pct > 10:
            self.issues.append(QualityIssue(
                severity="warning",
                category="completeness",
                description=f"{unknown_pct:.1f}% of nodes have unknown game labels",
                affected_items=[f"{unknown_nodes:,} nodes"],
                recommendation="Expand card database and run fix_graph_game_labels.py",
                evidence={"unknown_percentage": unknown_pct, "unknown_count": unknown_nodes},
            ))
        elif unknown_pct > 5:
            self.issues.append(QualityIssue(
                severity="info",
                category="completeness",
                description=f"{unknown_pct:.1f}% of nodes have unknown game labels",
                affected_items=[f"{unknown_nodes:,} nodes"],
                recommendation="Consider expanding card database for remaining unknown nodes",
                evidence={"unknown_percentage": unknown_pct},
            ))
        
        # Check for nodes without attributes and other completeness issues
        conn = sqlite3.connect(str(self.graph_db))
        
        nodes_without_attrs = conn.execute("""
            SELECT COUNT(*) 
            FROM nodes 
            WHERE attributes IS NULL OR attributes = ''
        """).fetchone()[0]
        
        # Check for high-frequency unknown nodes (likely Spanish cards)
        high_freq_unknown = 0
        if unknown_nodes > 0:
            high_freq_unknown = conn.execute("""
                SELECT COUNT(*) 
                FROM nodes 
                WHERE (game IS NULL OR game = 'Unknown')
                AND total_decks >= 100
            """).fetchone()[0]
        
        # Check for edges missing deck_sources (critical for data lineage)
        edges_missing_sources = conn.execute("""
            SELECT COUNT(*) 
            FROM edges 
            WHERE deck_sources IS NULL 
               OR deck_sources = '[]'
               OR deck_sources = ''
        """).fetchone()[0]
        
        # Check for edges missing temporal data
        edges_missing_temporal = conn.execute("""
            SELECT COUNT(*) 
            FROM edges 
            WHERE monthly_counts IS NULL 
               OR monthly_counts = '{}'
               OR monthly_counts = ''
        """).fetchone()[0]
        
        total_edges = self.statistics.get("total_edges", 1)
        missing_sources_pct = (edges_missing_sources / total_edges) * 100 if total_edges > 0 else 0
        missing_temporal_pct = (edges_missing_temporal / total_edges) * 100 if total_edges > 0 else 0
        
        # Check for high-frequency unknown nodes (likely Spanish cards)
        if unknown_nodes > 0 and high_freq_unknown > 10:
            self.issues.append(QualityIssue(
                severity="warning",
                category="completeness",
                description=f"{high_freq_unknown} high-frequency unknown nodes (>=100 decks) - likely Spanish cards",
                affected_items=[f"{high_freq_unknown} nodes"],
                recommendation="Run fix_spanish_card_names.py to translate and fix",
                evidence={"high_freq_unknown": high_freq_unknown},
            ))
        
        conn.close()
        
        if nodes_without_attrs > total_nodes * 0.5:
            self.issues.append(QualityIssue(
                severity="info",
                category="completeness",
                description=f"{(nodes_without_attrs/total_nodes)*100:.1f}% of nodes lack card attributes",
                affected_items=[f"{nodes_without_attrs:,} nodes"],
                recommendation="Enrich nodes with card attributes from card_attributes_enriched.csv",
                evidence={"nodes_without_attrs": nodes_without_attrs},
            ))
        
        # Check for edges missing deck_sources (critical for data lineage)
        if missing_sources_pct > 50:
            self.issues.append(QualityIssue(
                severity="warning",
                category="completeness",
                description=f"{missing_sources_pct:.1f}% of edges missing deck_sources ({edges_missing_sources:,} edges)",
                affected_items=[f"{edges_missing_sources:,} edges"],
                recommendation="Deck sources are critical for data lineage. Consider rebuilding graph with proper tracking.",
                evidence={"missing_sources_pct": missing_sources_pct, "missing_count": edges_missing_sources},
            ))
        elif missing_sources_pct > 10:
            self.issues.append(QualityIssue(
                severity="info",
                category="completeness",
                description=f"{missing_sources_pct:.1f}% of edges missing deck_sources",
                affected_items=[f"{edges_missing_sources:,} edges"],
                recommendation="Consider fixing missing deck_sources for better data lineage",
                evidence={"missing_sources_pct": missing_sources_pct},
            ))
        
        # Check for edges missing temporal data
        if missing_temporal_pct > 50:
            self.issues.append(QualityIssue(
                severity="info",
                category="completeness",
                description=f"{missing_temporal_pct:.1f}% of edges missing temporal data (monthly_counts)",
                affected_items=[f"{edges_missing_temporal:,} edges"],
                recommendation="Temporal data helps with format-specific analysis",
                evidence={"missing_temporal_pct": missing_temporal_pct},
            ))
    
    def _check_accuracy(self) -> None:
        """Check accuracy issues using sampling with agentic tools."""
        logger.info("Checking accuracy (sampling with agentic tools)...")
        
        # Use agentic QA tools for more sophisticated validation
        try:
            from .agentic_qa_tools import GraphQATools
            
            qa_tools = GraphQATools(self.graph_db)
            
            # Check data integrity first
            integrity = qa_tools.check_data_integrity()
            if integrity["integrity_score"] < 0.9:
                self.issues.append(QualityIssue(
                    severity="critical" if integrity["integrity_score"] < 0.7 else "warning",
                    category="accuracy",
                    description=f"Data integrity issues detected (score: {integrity['integrity_score']:.2%})",
                    affected_items=[
                        f"{integrity['orphaned_edges']} orphaned edges",
                        f"{integrity['duplicate_edges']} duplicate edges",
                        f"{integrity['invalid_weights']} invalid weights",
                    ],
                    recommendation="Run data integrity checks and fix issues",
                    evidence=integrity,
                ))
            
            # Sample high-frequency edges for validation
            sample_edges = qa_tools.sample_high_frequency_edges(limit=min(self.sample_size, 20))
            
            edge_issues = 0
            node_issues = 0
            
            for edge in sample_edges:
                # Validate nodes exist
                node1_check = qa_tools.check_node_exists(edge["card1"])
                node2_check = qa_tools.check_node_exists(edge["card2"])
                
                if not node1_check.get("exists"):
                    node_issues += 1
                if not node2_check.get("exists"):
                    node_issues += 1
                
                # Validate game labels
                game1_check = qa_tools.validate_game_label(edge["card1"])
                game2_check = qa_tools.validate_game_label(edge["card2"])
                
                if not game1_check.get("valid", True):
                    edge_issues += 1
                if not game2_check.get("valid", True):
                    edge_issues += 1
                
                # Check weight validity
                if edge["weight"] < 0 or edge["weight"] > 100000:
                    edge_issues += 1
            
            qa_tools.close()
            
            if node_issues > len(sample_edges) * 0.1:
                self.issues.append(QualityIssue(
                    severity="warning",
                    category="accuracy",
                    description=f"{node_issues}/{len(sample_edges)} sampled edges have node issues",
                    affected_items=[],
                    recommendation="Investigate missing nodes",
                    evidence={"sample_size": len(sample_edges), "issues_found": node_issues},
                ))
            
            if edge_issues > len(sample_edges) * 0.1:
                self.issues.append(QualityIssue(
                    severity="warning",
                    category="accuracy",
                    description=f"{edge_issues}/{len(sample_edges)} sampled edges have accuracy issues",
                    affected_items=[],
                    recommendation="Investigate edge data quality and game labels",
                    evidence={"sample_size": len(sample_edges), "issues_found": edge_issues},
                ))
            
        except Exception as e:
            logger.warning(f"Could not use agentic tools for accuracy check: {e}")
            # Fallback to basic validation
            conn = sqlite3.connect(str(self.graph_db))
            conn.row_factory = sqlite3.Row
            
            sample_nodes = conn.execute("""
                SELECT name, game, total_decks, attributes
                FROM nodes
                WHERE game IS NOT NULL AND game != 'Unknown'
                ORDER BY RANDOM()
                LIMIT ?
            """, (self.sample_size,)).fetchall()
            
            sample_edges = conn.execute("""
                SELECT card1, card2, game, weight, metadata
                FROM edges
                WHERE game IS NOT NULL AND game != 'Unknown'
                ORDER BY RANDOM()
                LIMIT ?
            """, (self.sample_size,)).fetchall()
            
            conn.close()
            
            node_issues = sum(1 for n in sample_nodes if len(n["name"]) < 2 or n["game"] not in ["MTG", "PKM", "YGO", "DIG", "OP", "RFT"])
            edge_issues = sum(1 for e in sample_edges if e["weight"] < 0 or e["weight"] > 100000 or not e["card1"] or not e["card2"])
            
            if node_issues > self.sample_size * 0.1:
                self.issues.append(QualityIssue(
                    severity="warning",
                    category="accuracy",
                    description=f"{node_issues}/{self.sample_size} sampled nodes have accuracy issues",
                    affected_items=[],
                    recommendation="Investigate node data quality",
                    evidence={"sample_size": self.sample_size, "issues_found": node_issues},
                ))
            
            if edge_issues > self.sample_size * 0.1:
                self.issues.append(QualityIssue(
                    severity="warning",
                    category="accuracy",
                    description=f"{edge_issues}/{self.sample_size} sampled edges have accuracy issues",
                    affected_items=[],
                    recommendation="Investigate edge data quality",
                    evidence={"sample_size": self.sample_size, "issues_found": edge_issues},
                ))
    
    def _sample_validate(self) -> list[dict[str, Any]]:
        """Perform sample validations with agentic reasoning."""
        logger.info(f"Performing sample validations (n={self.sample_size})...")
        
        conn = sqlite3.connect(str(self.graph_db))
        conn.row_factory = sqlite3.Row
        
        # Sample diverse nodes
        samples = conn.execute("""
            SELECT name, game, total_decks, attributes
            FROM nodes
            WHERE game IS NOT NULL AND game != 'Unknown'
            ORDER BY RANDOM()
            LIMIT ?
        """, (min(self.sample_size, 50),)).fetchall()
        
        conn.close()
        
        validations = []
        for sample in samples:
            validation = {
                "node": sample["name"],
                "game": sample["game"],
                "total_decks": sample["total_decks"],
                "has_attributes": bool(sample["attributes"]),
                "validation_status": "valid",
                "issues": [],
            }
            
            # Basic validation
            if not sample["name"] or len(sample["name"]) < 2:
                validation["validation_status"] = "invalid"
                validation["issues"].append("Invalid node name")
            
            if sample["total_decks"] < 0:
                validation["validation_status"] = "invalid"
                validation["issues"].append("Negative deck count")
            
            validations.append(validation)
        
        return validations
    
    def _calculate_score(self) -> float:
        """Calculate overall quality score (0-1)."""
        if not self.issues:
            return 1.0
        
        # Weight issues by severity
        critical_penalty = sum(1 for issue in self.issues if issue.severity == "critical") * 0.2
        warning_penalty = sum(1 for issue in self.issues if issue.severity == "warning") * 0.1
        info_penalty = sum(1 for issue in self.issues if issue.severity == "info") * 0.05
        
        score = 1.0 - min(1.0, critical_penalty + warning_penalty + info_penalty)
        
        # Adjust based on statistics
        unknown_pct = (self.statistics.get("unknown_nodes", 0) / max(1, self.statistics.get("total_nodes", 1))) * 100
        if unknown_pct > 10:
            score -= 0.1
        elif unknown_pct > 5:
            score -= 0.05
        
        return max(0.0, min(1.0, score))
    
    def generate_report(self, report: QualityReport, output_file: Path | None = None) -> Path:
        """Generate quality report."""
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = PATHS.experiments / f"quality_report_{timestamp}.json"
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        report_dict = {
            "timestamp": report.timestamp,
            "overall_score": report.overall_score,
            "statistics": report.statistics,
            "issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "description": issue.description,
                    "affected_items": issue.affected_items,
                    "recommendation": issue.recommendation,
                    "evidence": issue.evidence or {},
                }
                for issue in report.issues
            ],
            "sample_validations": report.sample_validations,
        }
        
        with open(output_file, "w") as f:
            json.dump(report_dict, f, indent=2, default=str)
        
        logger.info(f"Quality report saved: {output_file}")
        return output_file


def main() -> int:
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Graph Quality Assurance Check")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of samples to validate",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for report",
    )
    
    args = parser.parse_args()
    
    agent = GraphQualityAgent(
        graph_db=args.graph_db,
        sample_size=args.sample_size,
    )
    
    report = agent.run_quality_check()
    
    # Print summary
    print("\n" + "=" * 70)
    print("Quality Report Summary")
    print("=" * 70)
    print(f"Overall Score: {report.overall_score:.2%}")
    print(f"Total Issues: {len(report.issues)}")
    print(f"  Critical: {sum(1 for i in report.issues if i.severity == 'critical')}")
    print(f"  Warnings: {sum(1 for i in report.issues if i.severity == 'warning')}")
    print(f"  Info: {sum(1 for i in report.issues if i.severity == 'info')}")
    print("\nIssues:")
    for issue in report.issues:
        print(f"  [{issue.severity.upper()}] {issue.description}")
        print(f"    Recommendation: {issue.recommendation}")
    
    # Save report
    output_file = agent.generate_report(report, args.output)
    print(f"\nFull report saved: {output_file}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

