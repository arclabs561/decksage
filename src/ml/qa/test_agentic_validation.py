#!/usr/bin/env python3
"""
Test script for agentic validation system.

Quick test to verify the agentic QA agent works correctly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .agentic_qa_agent import AgenticQAAgent
from ..utils.paths import PATHS


async def test_agentic_validation():
    """Test the agentic validation system."""
    print("Testing agentic validation system...")
    
    try:
        # Initialize agent
        agent = AgenticQAAgent(graph_db=PATHS.incremental_graph_db)
        print("✓ Agent initialized")
        
        # Test pipeline validation
        print("\n1. Testing pipeline validation...")
        pipeline_result = await agent.validate_pipeline()
        print(f"✓ Pipeline validation completed")
        if isinstance(pipeline_result, dict):
            summary = pipeline_result.get('pipeline_summary', pipeline_result)
            print(f"  - Orders with data: {summary.get('orders_with_data', 0)}/{summary.get('total_orders', 7)}")
        
        # Test graph statistics
        print("\n2. Testing graph statistics...")
        stats = agent.tools.check_graph_statistics()
        print(f"✓ Graph statistics retrieved")
        print(f"  - Total nodes: {stats.get('nodes', {}).get('total', 0)}")
        print(f"  - Total edges: {stats.get('edges', {}).get('total', 0)}")
        
        # Test quality issue analysis
        print("\n3. Testing quality issue analysis...")
        analysis = await agent.analyze_quality_issue(
            "Some edges have suspiciously high weights (>100k)"
        )
        print(f"✓ Quality analysis completed")
        print(f"  - Severity: {analysis.severity}")
        print(f"  - Confidence: {analysis.confidence:.2%}")
        print(f"  - Recommendation: {analysis.recommended_fix[:80]}...")
        
        # Test sample investigation
        print("\n4. Testing sample investigation...")
        investigations = await agent.investigate_sample(sample_size=3)
        print(f"✓ Sample investigation completed")
        print(f"  - Samples analyzed: {len(investigations)}")
        
        agent.close()
        print("\n✓ All tests passed!")
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_agentic_validation())
    exit(0 if success else 1)

