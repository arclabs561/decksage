#!/usr/bin/env python3
"""
Standalone agentic validation script.

Provides focused agentic validation for specific issues or comprehensive analysis.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .agentic_qa_agent import AgenticQAAgent
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


async def validate_pipeline_agentic(graph_db: Path | None = None) -> int:
    """Run agentic pipeline validation."""
    logger.info("Running agentic pipeline validation...")
    
    try:
        agent = AgenticQAAgent(graph_db=graph_db or PATHS.incremental_graph_db)
        pipeline = await agent.validate_pipeline()
        
        summary = pipeline.get('pipeline_summary', {})
        orders_with_issues = summary.get('orders_with_issues', 0)
        
        print("\n" + "=" * 70)
        print("Pipeline Validation Results")
        print("=" * 70)
        print(f"Orders with data: {summary.get('orders_with_data', 0)}/{summary.get('total_orders', 7)}")
        print(f"Orders with issues: {orders_with_issues}")
        
        if orders_with_issues > 0:
            print("\nIssues by Order:")
            for order, validation in sorted(summary.get('orders', {}).items()):
                if not validation.get('valid'):
                    print(f"  Order {order} ({validation.get('order_name', 'Unknown')}):")
                    if validation.get('missing_dependencies'):
                        print(f"    Missing: {', '.join(validation['missing_dependencies'][:2])}")
        
        if pipeline.get('agent_analysis'):
            analysis = pipeline['agent_analysis']
            print("\nAgent Analysis:")
            print(f"  Severity: {analysis.get('severity', 'unknown')}")
            print(f"  Root Cause: {analysis.get('root_cause', 'N/A')[:100]}...")
            print(f"  Recommended Fix: {analysis.get('recommended_fix', 'N/A')[:100]}...")
            print(f"  Confidence: {analysis.get('confidence', 0):.1%}")
        
        agent.close()
        
        return 1 if orders_with_issues > 0 else 0
        
    except ImportError:
        # Fallback to non-agentic validation
        logger.warning("pydantic-ai not available, using non-agentic validation")
        from .agentic_qa_tools import GraphQATools
        
        tools = GraphQATools(graph_db or PATHS.incremental_graph_db)
        summary = tools.get_pipeline_summary()
        orders_with_issues = summary.get('orders_with_issues', 0)
        
        print("\n" + "=" * 70)
        print("Pipeline Validation Results (Non-Agentic)")
        print("=" * 70)
        print(f"Orders with data: {summary.get('orders_with_data', 0)}/{summary.get('total_orders', 7)}")
        print(f"Orders with issues: {orders_with_issues}")
        
        if orders_with_issues > 0:
            print("\nIssues by Order:")
            critical_orders = []
            for order, validation in sorted(summary.get('orders', {}).items()):
                if not validation.get('valid'):
                    order_name = validation.get('order_name', 'Unknown')
                    print(f"  Order {order} ({order_name}):")
                    if validation.get('missing_dependencies'):
                        missing = validation['missing_dependencies']
                        print(f"    Missing: {', '.join(missing[:2])}")
                        if len(missing) > 2:
                            print(f"    ... and {len(missing) - 2} more")
                        
                        # Identify critical blocking issues
                        if order in [2, 3, 4, 5, 6]:  # Downstream orders
                            if any('Order 1' in dep for dep in missing):
                                critical_orders.append((order, "Blocked by missing Order 1 (Exported Decks)"))
                            elif any('Order 2' in dep for dep in missing):
                                critical_orders.append((order, "Blocked by missing Order 2 (Co-occurrence Pairs)"))
            
            if critical_orders:
                print("\n⚠️  Critical Blocking Issues:")
                for order, reason in critical_orders:
                    print(f"  Order {order}: {reason}")
                print("\nRecommended Fix Order:")
                # Check if scripts exist
                from pathlib import Path
                export_script = Path("src/ml/scripts/export_decks.py")
                pairs_script = Path("src/ml/scripts/build_pairs_from_decks.py")
                
                if export_script.exists():
                    print("  1. Generate Order 1: python -m src.ml.scripts.export_decks")
                else:
                    print("  1. Generate Order 1 (Exported Decks)")
                    print("     → Script location: Check scripts/data_processing/ or src/ml/scripts/")
                
                if pairs_script.exists():
                    print("  2. Generate Order 2: python -m src.ml.scripts.build_pairs_from_decks")
                else:
                    print("  2. Generate Order 2 (Co-occurrence Pairs)")
                    print("     → Script location: Check scripts/data_processing/ or src/ml/scripts/")
                
                print("  3. Regenerate dependent orders (3-6) after fixing 1-2")
        
        tools.close()
        return 1 if orders_with_issues > 0 else 0
        
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


async def analyze_issue(issue_description: str, graph_db: Path | None = None) -> int:
    """Analyze a specific issue using agentic tools."""
    logger.info(f"Analyzing issue: {issue_description[:100]}...")
    
    try:
        agent = AgenticQAAgent(graph_db=graph_db or PATHS.incremental_graph_db)
        analysis = await agent.analyze_quality_issue(issue_description)
        
        print("\n" + "=" * 70)
        print("Issue Analysis")
        print("=" * 70)
        print(f"Issue: {issue_description}")
        print(f"\nSeverity: {analysis.severity}")
        print(f"Root Cause: {analysis.root_cause}")
        print(f"Impact: {analysis.impact}")
        print(f"Recommended Fix: {analysis.recommended_fix}")
        print(f"Confidence: {analysis.confidence:.1%}")
        
        agent.close()
        return 0
        
    except ImportError:
        logger.warning("pydantic-ai not available, cannot run agentic analysis")
        print("\n" + "=" * 70)
        print("Issue Analysis (Limited)")
        print("=" * 70)
        print(f"Issue: {issue_description}")
        print("\n⚠️  Agentic analysis requires pydantic-ai")
        print("Install with: uv pip install pydantic-ai")
        print("\nBasic tool-based checks available:")
        from .agentic_qa_tools import GraphQATools
        tools = GraphQATools(graph_db or PATHS.incremental_graph_db)
        integrity = tools.check_data_integrity()
        print(f"  Data integrity: {integrity.get('integrity_score', 0):.2%}")
        tools.close()
        return 0
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


async def comprehensive_analysis(graph_db: Path | None = None, output: Path | None = None) -> int:
    """Run comprehensive agentic analysis."""
    logger.info("Running comprehensive agentic analysis...")
    
    try:
        agent = AgenticQAAgent(graph_db=graph_db or PATHS.incremental_graph_db)
        analysis = await agent.comprehensive_analysis()
        
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            with open(output, 'w') as f:
                json.dump(analysis, f, indent=2, default=str)
            print(f"\nAnalysis saved to: {output}")
        
        if 'agent_analysis' in analysis:
            agent_analysis = analysis['agent_analysis']
            print("\n" + "=" * 70)
            print("Comprehensive Analysis Results")
            print("=" * 70)
            print(f"Severity: {agent_analysis.get('severity', 'unknown')}")
            print(f"Root Cause: {agent_analysis.get('root_cause', 'N/A')}")
            print(f"Impact: {agent_analysis.get('impact', 'N/A')}")
            print(f"Recommended Fix: {agent_analysis.get('recommended_fix', 'N/A')}")
            print(f"Confidence: {agent_analysis.get('confidence', 0):.1%}")
        
        agent.close()
        return 0
        
    except ImportError:
        logger.warning("pydantic-ai not available, using non-agentic analysis")
        from .agentic_qa_tools import GraphQATools
        
        tools = GraphQATools(graph_db or PATHS.incremental_graph_db)
        summary = tools.get_pipeline_summary()
        integrity = tools.check_data_integrity()
        stats = tools.check_graph_statistics()
        
        analysis = {
            "pipeline_summary": summary,
            "data_integrity": integrity,
            "graph_statistics": stats,
            "note": "Non-agentic analysis (pydantic-ai not available)",
        }
        
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            with open(output, 'w') as f:
                json.dump(analysis, f, indent=2, default=str)
            print(f"\nAnalysis saved to: {output}")
        
        print("\n" + "=" * 70)
        print("Comprehensive Analysis Results (Non-Agentic)")
        print("=" * 70)
        print(f"Pipeline: {summary.get('orders_with_data', 0)}/{summary.get('total_orders', 7)} orders have data")
        print(f"Issues: {summary.get('orders_with_issues', 0)} orders have problems")
        print(f"Integrity: {integrity.get('integrity_score', 0):.2%}")
        print(f"Nodes: {stats.get('nodes', {}).get('total', 0):,}")
        print(f"Edges: {stats.get('edges', {}).get('total', 0):,}")
        print("\n⚠️  For LLM-powered analysis, install: uv pip install pydantic-ai")
        
        tools.close()
        return 0
        
    except Exception as e:
        logger.error(f"Comprehensive analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Agentic validation and analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate entire pipeline
  python -m src.ml.qa.validate_agentic --pipeline

  # Analyze specific issue
  python -m src.ml.qa.validate_agentic --analyze "Graph has orphaned edges"

  # Comprehensive analysis
  python -m src.ml.qa.validate_agentic --comprehensive --output report.json
        """
    )
    
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Validate entire pipeline",
    )
    parser.add_argument(
        "--analyze",
        type=str,
        help="Analyze a specific issue",
    )
    parser.add_argument(
        "--comprehensive",
        action="store_true",
        help="Run comprehensive analysis",
    )
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for comprehensive analysis",
    )
    
    args = parser.parse_args()
    
    if not any([args.pipeline, args.analyze, args.comprehensive]):
        parser.print_help()
        return 1
    
    if args.pipeline:
        return asyncio.run(validate_pipeline_agentic(args.graph_db))
    elif args.analyze:
        return asyncio.run(analyze_issue(args.analyze, args.graph_db))
    elif args.comprehensive:
        return asyncio.run(comprehensive_analysis(args.graph_db, args.output))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

