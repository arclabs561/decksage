#!/usr/bin/env python3
"""
Comprehensive Quality Assurance Runner

Runs all QA checks:
1. Graph quality check
2. Annotation quality check
3. Agentic investigation of issues
4. Generate comprehensive report
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Any

from .graph_quality_agent import GraphQualityAgent
from .annotation_quality_agent import AnnotationQualityAgent
from .agentic_qa_agent import AgenticQAAgent
from ..utils.logging_config import setup_script_logging
from ..utils.paths import PATHS

logger = setup_script_logging()


async def run_comprehensive_qa(
    graph_db: Path | None = None,
    annotations_dir: Path | None = None,
    sample_size: int = 100,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Run comprehensive QA checks."""
    logger.info("=" * 70)
    logger.info("Comprehensive Quality Assurance")
    logger.info("=" * 70)
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "graph_qa": None,
        "annotation_qa": None,
        "pipeline_validation": None,
        "agentic_investigations": [],
    }
    
    # 1. Graph Quality Check
    logger.info("\n[1/3] Running graph quality check...")
    graph_agent = GraphQualityAgent(
        graph_db=graph_db or PATHS.incremental_graph_db,
        sample_size=sample_size,
        use_llm=use_llm,
    )
    graph_report = graph_agent.run_quality_check()
    results["graph_qa"] = {
        "overall_score": graph_report.overall_score,
        "total_issues": len(graph_report.issues),
        "critical_issues": sum(1 for i in graph_report.issues if i.severity == "critical"),
        "warnings": sum(1 for i in graph_report.issues if i.severity == "warning"),
        "statistics": graph_report.statistics,
        "issues": [
            {
                "severity": i.severity,
                "category": i.category,
                "description": i.description,
                "recommendation": i.recommendation,
            }
            for i in graph_report.issues
        ],
    }
    
    # Save graph report
    graph_report_file = graph_agent.generate_report(graph_report)
    results["graph_qa"]["report_file"] = str(graph_report_file)
    
    # 2. Annotation Quality Check
    logger.info("\n[2/3] Running annotation quality check...")
    ann_agent = AnnotationQualityAgent(annotations_dir=annotations_dir or Path("annotations"))
    ann_report = ann_agent.check_all_annotations()
    results["annotation_qa"] = ann_report
    
    # 3. Agentic Pipeline Validation & Comprehensive Analysis
    agentic_agent = None
    if use_llm:
        logger.info("\n[3/5] Running agentic pipeline validation...")
        try:
            agentic_agent = AgenticQAAgent(graph_db=graph_db or PATHS.incremental_graph_db)
            
            # Full pipeline validation with freshness analysis
            pipeline_validation = await agentic_agent.validate_pipeline()
            results["pipeline_validation"] = pipeline_validation
            
            # Comprehensive analysis if issues found
            if pipeline_validation.get('pipeline_summary', {}).get('orders_with_issues', 0) > 0:
                logger.info("Issues detected - running comprehensive agentic analysis...")
                comprehensive = await agentic_agent.comprehensive_analysis()
                results["agentic_comprehensive_analysis"] = comprehensive
        except Exception as e:
            logger.warning(f"Could not run agentic pipeline validation: {e}")
            # Fallback to non-agentic validation
            from .agentic_qa_tools import GraphQATools
            tools = GraphQATools(graph_db or PATHS.incremental_graph_db)
            results["pipeline_validation"] = tools.get_pipeline_summary()
            tools.close()
    
    # 4. Agentic Investigation of Graph Issues
    if use_llm and graph_agent._agentic_agent:
        logger.info("\n[4/5] Running agentic graph investigations...")
        try:
            investigations = await graph_agent._agentic_agent.investigate_sample(sample_size=min(sample_size, 10))
            results["agentic_investigations"] = investigations
        except Exception as e:
            logger.warning(f"Could not run agentic investigations: {e}")
    
    # 5. Agentic Analysis of Critical Issues
    if use_llm and agentic_agent:
        logger.info("\n[5/5] Running agentic issue analysis...")
        try:
            # Analyze any critical issues found
            critical_issues = [
                i for i in results.get('graph_qa', {}).get('issues', [])
                if i.get('severity') == 'critical'
            ]
            
            if critical_issues:
                issue_descriptions = [i.get('description', '') for i in critical_issues[:3]]
                combined_issue = "Critical issues detected: " + "; ".join(issue_descriptions)
                analysis = await agentic_agent.analyze_quality_issue(combined_issue)
                results["agentic_critical_analysis"] = {
                    "issues": issue_descriptions,
                    "analysis": analysis.dict() if hasattr(analysis, 'dict') else str(analysis),
                }
        except Exception as e:
            logger.warning(f"Could not run agentic critical issue analysis: {e}")
        
        if agentic_agent:
            agentic_agent.close()
    
    return results


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Comprehensive Quality Assurance")
    parser.add_argument(
        "--graph-db",
        type=Path,
        default=PATHS.incremental_graph_db,
        help="Path to graph database",
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Directory containing annotation files",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Sample size for validation",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        default=True,
        help="Use LLM agents for investigation",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file for comprehensive report",
    )
    
    args = parser.parse_args()
    
    # Run comprehensive QA
    results = asyncio.run(
        run_comprehensive_qa(
            graph_db=args.graph_db,
            annotations_dir=args.annotations_dir,
            sample_size=args.sample_size,
            use_llm=args.use_llm,
        )
    )
    
    # Save comprehensive report
    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = PATHS.experiments / f"comprehensive_qa_report_{timestamp}.json"
    
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    # Print summary
    print("\n" + "=" * 70)
    print("Comprehensive QA Summary")
    print("=" * 70)
    print(f"Graph Quality Score: {results['graph_qa']['overall_score']:.2%}")
    print(f"Graph Issues: {results['graph_qa']['total_issues']} ({results['graph_qa']['critical_issues']} critical)")
    print(f"Annotation Files: {results['annotation_qa']['total_files']}")
    print(f"Total Annotations: {results['annotation_qa']['total_annotations']}")
    print(f"Annotation Issues: {results['annotation_qa']['total_issues']}")
    
    if results.get('pipeline_validation'):
        pipeline = results['pipeline_validation']
        if isinstance(pipeline, dict):
            summary = pipeline.get('pipeline_summary', pipeline)
            orders_with_data = summary.get('orders_with_data', 0)
            orders_with_issues = summary.get('orders_with_issues', 0)
            print(f"Pipeline: {orders_with_data}/{summary.get('total_orders', 7)} orders have data")
            if orders_with_issues > 0:
                print(f"Pipeline Issues: {orders_with_issues} orders have problems")
    
    if results.get('agentic_investigations'):
        print(f"Agentic Investigations: {len(results['agentic_investigations'])} samples analyzed")
    
    if results.get('agentic_comprehensive_analysis'):
        analysis = results['agentic_comprehensive_analysis']
        if isinstance(analysis, dict) and 'agent_analysis' in analysis:
            agent_analysis = analysis['agent_analysis']
            print(f"\nAgentic Comprehensive Analysis:")
            print(f"  Severity: {agent_analysis.get('severity', 'unknown')}")
            print(f"  Confidence: {agent_analysis.get('confidence', 0):.1%}")
            if agent_analysis.get('recommended_fix'):
                fix = agent_analysis['recommended_fix']
                if len(fix) > 150:
                    fix = fix[:150] + "..."
                print(f"  Recommended Fix: {fix}")
    
    if results.get('agentic_critical_analysis'):
        print(f"\nAgentic Critical Issue Analysis: Available in report")
    
    print(f"\nFull report: {args.output}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())


