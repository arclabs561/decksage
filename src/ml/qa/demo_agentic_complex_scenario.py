#!/usr/bin/env python3
"""
Complex scenario demonstration: Agent handling multiple issues.

Shows how the agent prioritizes, investigates, and provides comprehensive analysis.
"""

from __future__ import annotations

import json
from pathlib import Path

from .agentic_qa_tools import GraphQATools
from ..utils.paths import PATHS


def complex_scenario():
    """Demonstrate agent handling complex multi-issue scenario."""
    print("=" * 70)
    print("Complex Scenario: Multiple Issues Detected")
    print("=" * 70)
    print()
    print("User reports: 'Graph seems wrong, embeddings don't work, test set fails'")
    print()
    
    tools = GraphQATools(graph_db=PATHS.incremental_graph_db)
    
    print("Agent's Investigation Plan:")
    print("  1. Assess overall system health")
    print("  2. Identify all issues")
    print("  3. Prioritize by severity")
    print("  4. Investigate root causes")
    print("  5. Provide comprehensive fix plan")
    print()
    
    # Phase 1: Overall Assessment
    print("=" * 70)
    print("Phase 1: Overall System Assessment")
    print("=" * 70)
    print()
    
    print("Agent calls: get_pipeline_summary()")
    pipeline = tools.get_pipeline_summary()
    print(f"  → Orders with issues: {pipeline.get('orders_with_issues', 0)}/{pipeline.get('total_orders', 7)}")
    
    print("\nAgent calls: check_graph_statistics()")
    stats = tools.check_graph_statistics()
    print(f"  → Nodes: {stats.get('nodes', {}).get('total', 0):,}")
    print(f"  → Edges: {stats.get('edges', {}).get('total', 0):,}")
    print(f"  → Unknown game labels: {stats.get('nodes', {}).get('unknown', 0):,}")
    
    print("\nAgent calls: check_data_integrity()")
    integrity = tools.check_data_integrity()
    print(f"  → Integrity score: {integrity.get('integrity_score', 0):.2%}")
    print(f"  → Orphaned edges: {integrity.get('orphaned_edges', 0):,}")
    
    # Phase 2: Issue Identification
    print()
    print("=" * 70)
    print("Phase 2: Issue Identification & Prioritization")
    print("=" * 70)
    print()
    
    issues = []
    
    # Issue 1: Pipeline dependencies
    print("Checking: Pipeline Dependencies")
    print("-" * 70)
    orders_with_issues = pipeline.get('orders_with_issues', 0)
    if orders_with_issues > 0:
        print(f"  ⚠️  Found: {orders_with_issues} orders with missing dependencies")
        issues.append({
            "type": "pipeline_dependencies",
            "severity": "critical",
            "count": orders_with_issues,
            "impact": "Blocks downstream processing"
        })
        print("  Agent notes: Critical - blocks entire pipeline")
    else:
        print("  ✓ All dependencies satisfied")
    
    # Issue 2: Data freshness
    print("\nChecking: Data Freshness")
    print("-" * 70)
    print("Agent calls: check_data_freshness(3)  # Graph")
    freshness_graph = tools.check_data_freshness(3)
    if not freshness_graph.get('is_fresh'):
        stale_count = len(freshness_graph.get('stale_issues', []))
        print(f"  ⚠️  Found: {stale_count} stale data issues")
        issues.append({
            "type": "stale_data",
            "severity": "warning",
            "count": stale_count,
            "impact": "Graph may be missing recent data"
        })
        print("  Agent notes: Warning - data may be outdated")
    else:
        print("  ✓ Graph is fresh")
    
    # Issue 3: Cross-order consistency
    print("\nChecking: Cross-Order Consistency")
    print("-" * 70)
    print("Agent calls: validate_nodes_against_decks()")
    cross_val = tools.validate_nodes_against_decks()
    coverage = cross_val.get('coverage_pct', 0)
    if coverage < 50:
        print(f"  ⚠️  Found: Low coverage ({coverage:.1f}%)")
        issues.append({
            "type": "low_coverage",
            "severity": "warning",
            "coverage": coverage,
            "impact": "Graph may not match source data"
        })
        print("  Agent notes: Warning - graph-source mismatch")
    else:
        print(f"  ✓ Good coverage ({coverage:.1f}%)")
    
    # Issue 4: Embedding validation
    print("\nChecking: Embedding Validation")
    print("-" * 70)
    print("Agent calls: check_embedding_exists('cooccurrence')")
    emb_check = tools.check_embedding_exists("cooccurrence")
    if not emb_check.get('exists'):
        print("  ⚠️  Found: Embeddings missing")
        issues.append({
            "type": "missing_embeddings",
            "severity": "critical",
            "impact": "Embeddings not available"
        })
        print("  Agent notes: Critical - embeddings required")
    else:
        print(f"  ✓ Embeddings exist (age: {emb_check.get('age_days', 0):.1f} days)")
        
        # Check vocabulary match
        print("\nAgent calls: validate_embedding_vocabulary('cooccurrence')")
        vocab_check = tools.validate_embedding_vocabulary("cooccurrence")
        if not vocab_check.get('valid'):
            coverage_emb = vocab_check.get('coverage_pct', 0)
            print(f"  ⚠️  Found: Low vocabulary coverage ({coverage_emb:.1f}%)")
            issues.append({
                "type": "vocab_mismatch",
                "severity": "warning",
                "coverage": coverage_emb,
                "impact": "Embeddings don't match graph vocabulary"
            })
            print("  Agent notes: Warning - vocab mismatch")
        else:
            print(f"  ✓ Vocabulary matches ({vocab_check.get('coverage_pct', 0):.1f}%)")
    
    # Issue 5: Test set validation
    print("\nChecking: Test Set Validation")
    print("-" * 70)
    print("Agent calls: validate_test_set_exists('magic')")
    test_check = tools.validate_test_set_exists("magic")
    if not test_check.get('exists'):
        print("  ⚠️  Found: Test set missing")
        issues.append({
            "type": "missing_test_set",
            "severity": "warning",
            "impact": "Cannot evaluate embeddings"
        })
        print("  Agent notes: Warning - evaluation blocked")
    else:
        print(f"  ✓ Test set exists ({test_check.get('query_count', 0)} queries)")
        
        # Check coverage
        print("\nAgent calls: check_test_set_coverage('magic')")
        test_coverage = tools.check_test_set_coverage("magic")
        if test_coverage.get('exists'):
            graph_cov = test_coverage.get('graph_coverage_pct', 0)
            if graph_cov < 80:
                print(f"  ⚠️  Found: Low test set coverage ({graph_cov:.1f}%)")
                issues.append({
                    "type": "low_test_coverage",
                    "severity": "warning",
                    "coverage": graph_cov,
                    "impact": "Many test queries not in graph"
                })
                print("  Agent notes: Warning - evaluation incomplete")
            else:
                print(f"  ✓ Good test coverage ({graph_cov:.1f}%)")
    
    # Phase 3: Root Cause Analysis
    print()
    print("=" * 70)
    print("Phase 3: Root Cause Analysis")
    print("=" * 70)
    print()
    
    if not issues:
        print("✓ No issues detected - system is healthy")
    else:
        print(f"Found {len(issues)} issues. Analyzing root causes...")
        print()
        
        # Group by severity
        critical = [i for i in issues if i['severity'] == 'critical']
        warnings = [i for i in issues if i['severity'] == 'warning']
        
        if critical:
            print("CRITICAL Issues:")
            for issue in critical:
                print(f"  - {issue['type']}: {issue.get('impact', 'N/A')}")
        
        if warnings:
            print("\nWARNING Issues:")
            for issue in warnings:
                print(f"  - {issue['type']}: {issue.get('impact', 'N/A')}")
        
        # Root cause analysis
        print("\nRoot Cause Analysis:")
        print("-" * 70)
        
        if any(i['type'] == 'pipeline_dependencies' for i in issues):
            print("  Primary Issue: Missing pipeline dependencies")
            print("    → Blocks: All downstream processing")
            print("    → Root Cause: Order 1 (Exported Decks) missing or incomplete")
            print("    → Impact: Cascading failures across orders 2-6")
        
        if any(i['type'] == 'stale_data' for i in issues):
            print("\n  Secondary Issue: Stale data")
            print("    → Blocks: Accurate graph relationships")
            print("    → Root Cause: Graph not updated after source data changed")
            print("    → Impact: Missing recent card relationships")
        
        if any(i['type'] == 'vocab_mismatch' for i in issues):
            print("\n  Secondary Issue: Vocabulary mismatch")
            print("    → Blocks: Embedding-based similarity")
            print("    → Root Cause: Embeddings trained on different graph version")
            print("    → Impact: Embeddings don't match current graph")
        
        # Phase 4: Comprehensive Fix Plan
        print()
        print("=" * 70)
        print("Phase 4: Comprehensive Fix Plan")
        print("=" * 70)
        print()
        
        print("Prioritized Fix Plan:")
        print()
        
        step = 1
        if any(i['type'] == 'pipeline_dependencies' for i in issues):
            print(f"{step}. Fix Pipeline Dependencies (CRITICAL)")
            print("   Command: python -m src.ml.scripts.export_decks")
            print("   Expected: Generate Order 1 data")
            print("   Then: Regenerate dependent orders (2-6)")
            step += 1
        
        if any(i['type'] == 'stale_data' for i in issues):
            print(f"\n{step}. Update Stale Graph Data (HIGH PRIORITY)")
            print("   Command: python -m src.ml.scripts.update_graph_incremental")
            print("   Expected: Graph synced with latest pairs")
            step += 1
        
        if any(i['type'] == 'vocab_mismatch' for i in issues):
            print(f"\n{step}. Retrain Embeddings (HIGH PRIORITY)")
            print("   Command: python -m src.ml.scripts.train_embeddings")
            print("   Expected: Embeddings match current graph vocabulary")
            step += 1
        
        if any(i['type'] == 'low_coverage' for i in issues):
            print(f"\n{step}. Rebuild Graph from Source (MEDIUM PRIORITY)")
            print("   Command: python -m src.ml.scripts.build_graph_from_pairs")
            print("   Expected: Graph matches source deck data")
            step += 1
        
        if any(i['type'] == 'low_test_coverage' for i in issues):
            print(f"\n{step}. Update Test Set (MEDIUM PRIORITY)")
            print("   Command: python -m src.ml.scripts.generate_test_set")
            print("   Expected: Test queries exist in graph")
            step += 1
        
        print()
        print("Agent's Confidence: High")
        print("  → All issues identified with evidence")
        print("  → Root causes traced to specific orders")
        print("  → Fix plan prioritized by severity")
    
    print()
    print("=" * 70)
    
    tools.close()


def main():
    """Run complex scenario demonstration."""
    complex_scenario()
    
    print()
    print("=" * 70)
    print("Complex Scenario Complete")
    print("=" * 70)
    print()
    print("This demonstrates the agent's ability to:")
    print("  ✓ Handle multiple simultaneous issues")
    print("  ✓ Prioritize by severity and impact")
    print("  ✓ Trace root causes across orders")
    print("  ✓ Provide comprehensive, prioritized fix plan")
    print("  ✓ Use 23 tools strategically to build complete picture")


if __name__ == "__main__":
    main()

