#!/usr/bin/env python3
"""
Quality Dashboard

Generates HTML dashboard showing system health and quality metrics.
Part of T0.3 foundation refinement.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..utils.paths import PATHS

logger = logging.getLogger(__name__)


@dataclass
class QualityMetric:
    """Single quality metric with status."""
    name: str
    value: float
    target: float
    status: str  # "pass", "warn", "fail"
    description: str


@dataclass
class SystemHealth:
    """Overall system health status."""
    timestamp: str
    overall_status: str  # "healthy", "degraded", "unhealthy"
    metrics: list[QualityMetric]
    test_set_coverage: dict[str, Any]
    deck_completion_quality: dict[str, Any]
    embedding_performance: dict[str, Any]


def load_metric_from_file(path: Path, key: str, default: float = 0.0) -> float:
    """Load a metric value from JSON file."""
    if not path.exists():
        return default
    
    try:
        with open(path) as f:
            data = json.load(f)
            return float(data.get(key, default))
    except Exception:
        return default


def compute_system_health(
    test_set_validation_path: Optional[Path] = None,
    completion_validation_path: Optional[Path] = None,
    evaluation_results_path: Optional[Path] = None,
) -> SystemHealth:
    """
    Compute overall system health from validation results.
    
    Args:
        test_set_validation_path: Path to test set validation JSON
        completion_validation_path: Path to completion validation JSON
        evaluation_results_path: Path to evaluation results JSON
    
    Returns:
        SystemHealth with all metrics
    """
    metrics: list[QualityMetric] = []
    
    # Load test set validation
    test_set_coverage = {}
    if test_set_validation_path and test_set_validation_path.exists():
        try:
            with open(test_set_validation_path) as f:
                test_set_coverage = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load test set validation: {e}")
            test_set_coverage = {}
        
        stats = test_set_coverage.get("stats", {})
        total_queries = stats.get("total_queries", 0)
        queries_with_labels = stats.get("queries_with_labels", 0)
        
        # Test set coverage metric
        coverage_pct = (
            queries_with_labels / total_queries * 100
            if total_queries > 0
            else 0.0
        )
        metrics.append(
            QualityMetric(
                name="Test Set Coverage",
                value=coverage_pct,
                target=95.0,
                status="pass" if coverage_pct >= 95.0 else "warn" if coverage_pct >= 80.0 else "fail",
                description=f"{queries_with_labels}/{total_queries} queries have labels",
            )
        )
        
        # Test set size metric
        metrics.append(
            QualityMetric(
                name="Test Set Size",
                value=float(total_queries),
                target=100.0,
                status="pass" if total_queries >= 100 else "warn" if total_queries >= 50 else "fail",
                description=f"{total_queries} total queries",
            )
        )
    
    # Load completion validation
    deck_completion_quality = {}
    if completion_validation_path and completion_validation_path.exists():
        try:
            with open(completion_validation_path) as f:
                deck_completion_quality = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load completion validation: {e}")
            deck_completion_quality = {}
        
        success_rate = deck_completion_quality.get("success_rate", 0.0)
        avg_quality = deck_completion_quality.get("avg_quality_score", 0.0)
        
        # Completion success rate
        metrics.append(
            QualityMetric(
                name="Deck Completion Success",
                value=success_rate * 100,
                target=70.0,
                status="pass" if success_rate >= 0.7 else "warn" if success_rate >= 0.5 else "fail",
                description=f"{success_rate * 100:.1f}% of completions meet quality threshold",
            )
        )
        
        # Average quality score
        metrics.append(
            QualityMetric(
                name="Average Deck Quality",
                value=avg_quality,
                target=6.0,
                status="pass" if avg_quality >= 6.0 else "warn" if avg_quality >= 5.0 else "fail",
                description=f"Average quality score: {avg_quality:.2f}/10.0",
            )
        )
    
    # Load evaluation results (handle multiple formats)
    embedding_performance = {}
    if evaluation_results_path and evaluation_results_path.exists():
        try:
            from ml.scripts.fix_nuances import safe_json_load
            data = safe_json_load(evaluation_results_path, default={})
        except Exception as e:
            logger.warning(f"Failed to load evaluation results: {e}")
            data = {}
        
        # Handle different evaluation output formats
        # Format 1: Direct metrics {"p@10": 0.08, "mrr": 0.12, ...}
        # Format 2: Nested {"results": {"method": {"p@10": 0.08, ...}}}
        # Format 3: Summary {"summary": {"best_p@10": 0.08, ...}}
        
        if "results" in data:
            # Multi-method evaluation - use best method
            results = data["results"]
            best_method = data.get("summary", {}).get("best_method")
            if best_method and best_method in results:
                embedding_performance = results[best_method]
            elif results:
                # Use first method
                embedding_performance = list(results.values())[0]
        elif "summary" in data:
            # Summary format
            summary = data["summary"]
            embedding_performance = {
                "p_at_10": summary.get("best_p@10", 0.0),
                "mrr": summary.get("best_mrr", 0.0),
            }
        elif "tasks" in data:
            # Downstream evaluation format
            tasks = data["tasks"]
            # Extract from completion task if available
            if "completion" in tasks:
                comp = tasks["completion"]
                embedding_performance = {
                    "p_at_10": comp.get("p@10", comp.get("precision_at_10", 0.0)),
                    "mrr": comp.get("mrr", 0.0),
                }
        else:
            # Direct format
            embedding_performance = data
        
        p_at_10 = embedding_performance.get("p_at_10", embedding_performance.get("p@10", 0.0))
        mrr = embedding_performance.get("mrr", embedding_performance.get("mrr@10", 0.0))
        
        # P@10 metric
        metrics.append(
            QualityMetric(
                name="P@10 (Precision at 10)",
                value=p_at_10,
                target=0.15,
                status="pass" if p_at_10 >= 0.15 else "warn" if p_at_10 >= 0.10 else "fail",
                description=f"Precision at 10: {p_at_10:.3f} (target: 0.15-0.20)",
            )
        )
        
        # MRR metric
        metrics.append(
            QualityMetric(
                name="MRR (Mean Reciprocal Rank)",
                value=mrr,
                target=0.20,
                status="pass" if mrr >= 0.20 else "warn" if mrr >= 0.15 else "fail",
                description=f"Mean Reciprocal Rank: {mrr:.3f}",
            )
        )
    
    # Compute overall status
    fail_count = sum(1 for m in metrics if m.status == "fail")
    warn_count = sum(1 for m in metrics if m.status == "warn")
    
    if fail_count > 0:
        overall_status = "unhealthy"
    elif warn_count > 0:
        overall_status = "degraded"
    else:
        overall_status = "healthy"
    
    return SystemHealth(
        timestamp=datetime.now().isoformat(),
        overall_status=overall_status,
        metrics=metrics,
        test_set_coverage=test_set_coverage,
        deck_completion_quality=deck_completion_quality,
        embedding_performance=embedding_performance,
    )


def generate_dashboard_html(health: SystemHealth, output_path: Path) -> None:
    """Generate HTML dashboard from system health data."""
    
    # Status colors
    status_colors = {
        "pass": "#10b981",  # green
        "warn": "#f59e0b",  # amber
        "fail": "#ef4444",  # red
    }
    
    status_bg_colors = {
        "pass": "#d1fae5",
        "warn": "#fef3c7",
        "fail": "#fee2e2",
    }
    
    overall_colors = {
        "healthy": "#10b981",
        "degraded": "#f59e0b",
        "unhealthy": "#ef4444",
    }
    
    # Generate metrics HTML
    metrics_html = ""
    for metric in health.metrics:
        status_color = status_colors[metric.status]
        status_bg = status_bg_colors[metric.status]
        
        # Compute progress percentage
        progress_pct = min(100, (metric.value / metric.target * 100)) if metric.target > 0 else 0
        
        metrics_html += f"""
        <div class="metric-card">
            <div class="metric-header">
                <h3>{metric.name}</h3>
                <span class="status-badge" style="background-color: {status_bg}; color: {status_color};">
                    {metric.status.upper()}
                </span>
            </div>
            <div class="metric-value">
                <span class="value">{metric.value:.2f}</span>
                <span class="target">/ {metric.target:.2f}</span>
            </div>
            <div class="metric-description">{metric.description}</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {progress_pct}%; background-color: {status_color};"></div>
            </div>
        </div>
        """
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeckSage Quality Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f5f5f5;
            padding: 20px;
            color: #1f2937;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        
        .header .timestamp {{
            color: #6b7280;
            font-size: 14px;
        }}
        
        .status-banner {{
            display: inline-block;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: 600;
            margin-top: 10px;
            background-color: {overall_colors[health.overall_status]};
            color: white;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .metric-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        
        .metric-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        
        .metric-header h3 {{
            font-size: 16px;
            font-weight: 600;
        }}
        
        .status-badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        
        .metric-value {{
            font-size: 32px;
            font-weight: 700;
            margin-bottom: 10px;
        }}
        
        .metric-value .value {{
            color: #1f2937;
        }}
        
        .metric-value .target {{
            color: #6b7280;
            font-size: 20px;
        }}
        
        .metric-description {{
            color: #6b7280;
            font-size: 14px;
            margin-bottom: 15px;
        }}
        
        .progress-bar {{
            height: 8px;
            background: #e5e7eb;
            border-radius: 4px;
            overflow: hidden;
        }}
        
        .progress-fill {{
            height: 100%;
            transition: width 0.3s ease;
        }}
        
        .section {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        
        .section h2 {{
            font-size: 20px;
            margin-bottom: 15px;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 10px;
        }}
        
        .section pre {{
            background: #f9fafb;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>DeckSage Quality Dashboard</h1>
            <div class="timestamp">Last updated: {health.timestamp}</div>
            <div class="status-banner">Status: {health.overall_status.upper()}</div>
        </div>
        
        <div class="metrics-grid">
            {metrics_html}
        </div>
        
        <div class="section">
            <h2>Test Set Coverage</h2>
            <pre>{json.dumps(health.test_set_coverage, indent=2)}</pre>
        </div>
        
        <div class="section">
            <h2>Deck Completion Quality</h2>
            <pre>{json.dumps(health.deck_completion_quality, indent=2)}</pre>
        </div>
        
        <div class="section">
            <h2>Embedding Performance</h2>
            <pre>{json.dumps(health.embedding_performance, indent=2)}</pre>
        </div>
    </div>
</body>
</html>
"""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)


def main() -> int:
    """CLI for quality dashboard generation."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate quality dashboard")
    parser.add_argument(
        "--test-set-validation",
        type=Path,
        help="Path to test set validation JSON",
    )
    parser.add_argument(
        "--completion-validation",
        type=Path,
        help="Path to completion validation JSON",
    )
    parser.add_argument(
        "--evaluation-results",
        type=Path,
        help="Path to evaluation results JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PATHS.experiments / "quality_dashboard.html",
        help="Output HTML file",
    )
    
    args = parser.parse_args()
    
    health = compute_system_health(
        test_set_validation_path=args.test_set_validation,
        completion_validation_path=args.completion_validation,
        evaluation_results_path=args.evaluation_results,
    )
    
    generate_dashboard_html(health, args.output)
    
    print(f"Quality dashboard generated: {args.output}")
    print(f"Status: {health.overall_status.upper()}")
    print(f"Metrics: {len(health.metrics)}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

