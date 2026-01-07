#!/usr/bin/env python3
"""
Comprehensive test of agentic validation system.

Tests the agent's ability to:
1. Detect and diagnose complex issues
2. Use temporal tools to find stale data
3. Validate cross-order consistency
4. Provide actionable recommendations
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .agentic_qa_agent import AgenticQAAgent
from ..utils.paths import PATHS


async def test_comprehensive_agent():
    """Test comprehensive agentic validation."""
    print("=" * 70)
    print("Comprehensive Agentic Validation Test")
    print("=" * 70)
    print()
    
    try:
        agent = AgenticQAAgent(graph_db=PATHS.incremental_graph_db)
        print("✓ Agent initialized with 21 tools")
        print()
        
        # Test 1: Pipeline validation with freshness
        print("Test 1: Pipeline Validation with Freshness Analysis")
        print("-" * 70)
        pipeline = await agent.validate_pipeline()
        
        if isinstance(pipeline, dict):
            summary = pipeline.get('pipeline_summary', {})
            freshness = pipeline.get('freshness_analysis', {})
            agent_analysis = pipeline.get('agent_analysis', {})
            
            print(f"Pipeline Summary:")
            print(f"  - Orders with data: {summary.get('orders_with_data', 0)}/{summary.get('total_orders', 7)}")
            print(f"  - Orders with issues: {summary.get('orders_with_issues', 0)}")
            
            if freshness:
                stale_orders = [
                    order for order, data in freshness.items()
                    if isinstance(data, dict) and not data.get('is_fresh', True)
                ]
                if stale_orders:
                    print(f"  - Stale orders detected: {stale_orders}")
                    for order in stale_orders[:2]:
                        stale_data = freshness.get(order, {})
                        issues = stale_data.get('stale_issues', [])
                        if issues:
                            issue = issues[0]
                            print(f"    Order {order}: Stale by {issue.get('stale_by_days', 0):.1f} days")
            
            if agent_analysis:
                print(f"\nAgent Analysis:")
                print(f"  - Severity: {agent_analysis.get('severity', 'unknown')}")
                print(f"  - Root Cause: {agent_analysis.get('root_cause', 'N/A')[:100]}...")
                print(f"  - Recommended Fix: {agent_analysis.get('recommended_fix', 'N/A')[:100]}...")
                print(f"  - Confidence: {agent_analysis.get('confidence', 0):.1%}")
        
        print()
        
        # Test 2: Complex issue analysis
        print("Test 2: Complex Issue Analysis")
        print("-" * 70)
        analysis = await agent.analyze_quality_issue(
            "Graph has 1000+ orphaned edges. Investigate root cause and recommend fix."
        )
        print(f"Issue: Graph has 1000+ orphaned edges")
        print(f"Analysis:")
        print(f"  - Severity: {analysis.severity}")
        print(f"  - Root Cause: {analysis.root_cause}")
        print(f"  - Impact: {analysis.impact}")
        print(f"  - Recommended Fix: {analysis.recommended_fix}")
        print(f"  - Confidence: {analysis.confidence:.1%}")
        print()
        
        # Test 3: Data freshness check
        print("Test 3: Data Freshness Check")
        print("-" * 70)
        freshness = agent.tools.check_data_freshness(3)  # Order 3 (Graph)
        print(f"Order 3 (Graph) Freshness:")
        print(f"  - Is Fresh: {freshness.get('is_fresh', False)}")
        if freshness.get('stale_issues'):
            for issue in freshness['stale_issues'][:2]:
                print(f"  - Stale Issue:")
                print(f"    Order location: {issue.get('order_location', 'N/A')}")
                print(f"    Dependency: {issue.get('dependency', 'N/A')}")
                print(f"    Stale by: {issue.get('stale_by_days', 0):.1f} days")
        print()
        
        # Test 4: Cross-order validation
        print("Test 4: Cross-Order Validation")
        print("-" * 70)
        cross_validation = agent.tools.validate_nodes_against_decks()
        print(f"Graph Nodes vs Decks:")
        print(f"  - Graph nodes: {cross_validation.get('graph_nodes_count', 0)}")
        print(f"  - Deck cards sampled: {cross_validation.get('deck_cards_sampled', 0)}")
        print(f"  - Coverage: {cross_validation.get('coverage_pct', 0):.1f}%")
        if cross_validation.get('nodes_missing_in_decks', 0) > 0:
            print(f"  - Nodes missing in decks: {cross_validation['nodes_missing_in_decks']}")
            print(f"    Sample: {cross_validation.get('sample_missing_nodes', [])[:3]}")
        print()
        
        # Test 5: File timestamp check
        print("Test 5: File Timestamp Analysis")
        print("-" * 70)
        if PATHS.incremental_graph_db.exists():
            graph_ts = agent.tools.check_file_timestamp(PATHS.incremental_graph_db)
            print(f"Graph DB: {PATHS.incremental_graph_db.name}")
            print(f"  - Modified: {graph_ts.get('modified_time', 'N/A')}")
            print(f"  - Age: {graph_ts.get('age_days', 0):.1f} days")
            print(f"  - Size: {graph_ts.get('size_mb', 0):.2f} MB")
        
        # Check pairs file if exists
        pairs_files = list(PATHS.processed.glob("pairs_*.csv"))
        if pairs_files:
            pairs_ts = agent.tools.check_file_timestamp(pairs_files[0])
            print(f"\nPairs File: {pairs_files[0].name}")
            print(f"  - Modified: {pairs_ts.get('modified_time', 'N/A')}")
            print(f"  - Age: {pairs_ts.get('age_days', 0):.1f} days")
            
            # Compare timestamps
            if PATHS.incremental_graph_db.exists():
                comparison = agent.tools.compare_file_timestamps(
                    PATHS.incremental_graph_db,
                    pairs_files[0]
                )
                if comparison.get('path1_newer'):
                    print(f"  - Graph is NEWER than pairs (good)")
                elif comparison.get('path2_newer'):
                    print(f"  - Graph is OLDER than pairs by {comparison.get('age_difference_days', 0):.1f} days (stale!)")
        print()
        
        # Test 6: Enhanced investigation
        print("Test 6: Enhanced Sample Investigation")
        print("-" * 70)
        investigations = await agent.investigate_sample(sample_size=5)
        if isinstance(investigations, dict) and 'agent_analysis' in investigations:
            analysis = investigations['agent_analysis']
            print(f"Investigation Results:")
            print(f"  - Edges sampled: {investigations.get('edges_sampled', 0)}")
            print(f"  - Severity: {analysis.get('severity', 'unknown')}")
            print(f"  - Root Cause: {analysis.get('root_cause', 'N/A')[:80]}...")
            print(f"  - Confidence: {analysis.get('confidence', 0):.1%}")
        else:
            print(f"Investigated {len(investigations)} edges")
        print()
        
        agent.close()
        
        print("=" * 70)
        print("✓ All comprehensive tests completed!")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_comprehensive_agent())
    exit(0 if success else 1)

