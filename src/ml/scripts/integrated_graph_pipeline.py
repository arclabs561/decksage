#!/usr/bin/env python3
"""
Integrated Graph Pipeline with Quality Assurance

Complete pipeline for updating the graph with automatic quality fixes.
Integrates graph updates, quality checks, and fixes into a single workflow.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS
from .update_graph_incremental import update_graph_incremental, run_post_update_quality_fixes

logger = setup_script_logging()


def run_integrated_pipeline(
    graph_path: Path,
    new_decks_path: Path | None = None,
    card_attributes_path: Path | None = None,
    run_quality_fixes: bool = True,
    api_fallback: bool = False,
    run_qa_check: bool = False,
) -> dict[str, any]:
    """
    Run integrated graph update pipeline with quality assurance.
    
    Args:
        graph_path: Path to graph database
        new_decks_path: Path to new decks JSONL file
        card_attributes_path: Path to card attributes CSV
        run_quality_fixes: Run post-update quality fixes
        api_fallback: Use API fallback for unknown nodes
        run_qa_check: Run comprehensive QA check after fixes
        
    Returns:
        Dictionary with pipeline results
    """
    results = {}
    
    logger.info("=" * 70)
    logger.info("Integrated Graph Update Pipeline")
    logger.info("=" * 70)
    
    # Step 1: Update graph
    logger.info("\nStep 1: Updating graph...")
    try:
        graph = update_graph_incremental(
            graph_path=graph_path,
            new_decks_path=new_decks_path,
            card_attributes_path=card_attributes_path,
        )
        results["graph_updated"] = True
        results["nodes"] = len(graph.nodes)
        results["edges"] = len(graph.edges)
        logger.info(f"✓ Graph updated: {results['nodes']:,} nodes, {results['edges']:,} edges")
    except Exception as e:
        logger.error(f"Graph update failed: {e}")
        results["graph_updated"] = False
        results["error"] = str(e)
        return results
    
    # Step 2: Run quality fixes
    if run_quality_fixes:
        logger.info("\nStep 2: Running quality fixes...")
        try:
            fix_results = run_post_update_quality_fixes(
                graph_path=graph_path,
                api_fallback=api_fallback,
            )
            results["quality_fixes"] = fix_results
            logger.info("✓ Quality fixes completed")
        except Exception as e:
            logger.warning(f"Quality fixes failed: {e}")
            results["quality_fixes"] = {}
    
    # Step 3: Run QA check (optional)
    if run_qa_check:
        logger.info("\nStep 3: Running QA check...")
        try:
            from ..qa.graph_quality_agent import GraphQualityAgent
            
            qa_agent = GraphQualityAgent(graph_db=graph_path, sample_size=50)
            qa_report = qa_agent.run_quality_check()
            
            results["qa_score"] = qa_report.get("overall_score", 0)
            results["qa_issues"] = len(qa_report.get("issues", []))
            logger.info(f"✓ QA check completed: {results['qa_score']:.0%} score, {results['qa_issues']} issues")
        except Exception as e:
            logger.warning(f"QA check failed: {e}")
            results["qa_score"] = None
    
    logger.info("\n" + "=" * 70)
    logger.info("Pipeline Complete")
    logger.info("=" * 70)
    
    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Integrated graph update pipeline with QA")
    parser.add_argument(
        "--graph-path",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--new-decks",
        type=Path,
        help="Path to new decks JSONL file",
    )
    parser.add_argument(
        "--card-attributes",
        type=Path,
        default=PATHS.card_attributes,
        help="Path to card attributes CSV",
    )
    parser.add_argument(
        "--skip-fixes",
        action="store_true",
        help="Skip quality fixes",
    )
    parser.add_argument(
        "--api-fallback",
        action="store_true",
        help="Use API fallback for unknown nodes",
    )
    parser.add_argument(
        "--qa-check",
        action="store_true",
        help="Run comprehensive QA check after fixes",
    )
    
    args = parser.parse_args()
    
    if not args.new_decks:
        logger.error("Must provide --new-decks")
        return 1
    
    results = run_integrated_pipeline(
        graph_path=args.graph_path,
        new_decks_path=args.new_decks,
        card_attributes_path=args.card_attributes,
        run_quality_fixes=not args.skip_fixes,
        api_fallback=args.api_fallback,
        run_qa_check=args.qa_check,
    )
    
    if not results.get("graph_updated"):
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

