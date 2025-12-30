#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Create HTML evaluation dashboard showing trends over time.

Aggregates results from multiple evaluation runs into a single HTML report.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def load_evaluation_results(results_dir: Path) -> list[dict[str, Any]]:
    """Load all evaluation results from directory."""
    results = []
    
    for json_file in results_dir.glob("*.json"):
        try:
            with open(json_file) as f:
                data = json.load(f)
            
            # Extract metadata
            result = {
                "file": json_file.name,
                "timestamp": json_file.stat().st_mtime,
                "data": data,
            }
            results.append(result)
        except Exception:
            continue
    
    # Sort by timestamp
    results.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return results


def extract_metrics(result: dict[str, Any]) -> dict[str, Any]:
    """Extract key metrics from evaluation result."""
    data = result["data"]
    
    metrics = {
        "file": result["file"],
        "timestamp": datetime.fromtimestamp(result["timestamp"]).isoformat(),
    }
    
    # Try different result formats
    if "results" in data:
        # Format: {"results": {"model1": {"p@10": ...}, ...}}
        for model_name, model_results in data["results"].items():
            if isinstance(model_results, dict):
                metrics[f"{model_name}_p@10"] = model_results.get("p@10", 0.0)
                metrics[f"{model_name}_mrr"] = model_results.get("mrr", 0.0)
                if "r@10" in model_results:
                    metrics[f"{model_name}_r@10"] = model_results.get("r@10", 0.0)
                if "map@10" in model_results:
                    metrics[f"{model_name}_map@10"] = model_results.get("map@10", 0.0)
    
    elif "summary" in data:
        # Format: {"summary": {"best_p@10": ...}}
        summary = data["summary"]
        metrics["best_p@10"] = summary.get("best_p@10", 0.0)
        metrics["best_method"] = summary.get("best_method", "unknown")
    
    elif "p@10" in data:
        # Format: {"p@10": ..., "mrr": ...}
        metrics["p@10"] = data.get("p@10", 0.0)
        metrics["mrr"] = data.get("mrr", 0.0)
        if "r@10" in data:
            metrics["r@10"] = data.get("r@10", 0.0)
        if "map@10" in data:
            metrics["map@10"] = data.get("map@10", 0.0)
    
    return metrics


def generate_html_dashboard(results: list[dict[str, Any]], output_path: Path) -> None:
    """Generate HTML dashboard."""
    html_template = """<!DOCTYPE html>
<html>
<head>
    <title>Evaluation Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        h1 {{
            color: #333;
        }}
        .metrics-table {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        tr:hover {{
            background: #f8f9fa;
        }}
        .metric-value {{
            font-family: 'Monaco', monospace;
        }}
        .good {{ color: #28a745; }}
        .bad {{ color: #dc3545; }}
        .warning {{ color: #ffc107; }}
    </style>
</head>
<body>
    <h1>Evaluation Dashboard</h1>
    <p>Generated: {timestamp}</p>
    
    <div class="metrics-table">
        <h2>Recent Evaluations</h2>
        <table>
            <thead>
                <tr>
                    <th>File</th>
                    <th>Timestamp</th>
                    <th>P@10</th>
                    <th>R@10</th>
                    <th>MAP@10</th>
                    <th>MRR</th>
                </tr>
            </thead>
            <tbody>
{rows}
            </tbody>
        </table>
    </div>
</body>
</html>
"""
    
    rows = []
    for result in results[:50]:  # Show last 50
        metrics = extract_metrics(result)
        
        p10 = metrics.get("p@10") or metrics.get("best_p@10", 0.0)
        r10 = metrics.get("r@10", "N/A")
        map10 = metrics.get("map@10", "N/A")
        mrr = metrics.get("mrr", "N/A")
        
        p10_class = "good" if isinstance(p10, (int, float)) and p10 > 0.1 else "bad" if isinstance(p10, (int, float)) and p10 < 0.05 else "warning"
        
        def format_val(v):
            if isinstance(v, (int, float)):
                return f"{v:.4f}"
            return str(v)
        
        row = f"""
                <tr>
                    <td>{metrics['file']}</td>
                    <td>{metrics['timestamp']}</td>
                    <td class="metric-value {p10_class}">{format_val(p10)}</td>
                    <td class="metric-value">{format_val(r10)}</td>
                    <td class="metric-value">{format_val(map10)}</td>
                    <td class="metric-value">{format_val(mrr)}</td>
                </tr>"""
        rows.append(row)
    
    html = html_template.format(
        timestamp=datetime.now().isoformat(),
        rows="".join(rows),
    )
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)


def main() -> int:
    """Create evaluation dashboard."""
    parser = argparse.ArgumentParser(description="Create evaluation dashboard")
    parser.add_argument("--results-dir", type=Path, default=Path("experiments"), help="Directory with evaluation JSON files")
    parser.add_argument("--output", type=Path, default=Path("experiments/dashboard.html"), help="Output HTML file")
    
    args = parser.parse_args()
    
    print(f"Loading evaluation results from {args.results_dir}...")
    results = load_evaluation_results(args.results_dir)
    print(f"  Found {len(results)} evaluation files")
    
    print(f"\nGenerating dashboard...")
    generate_html_dashboard(results, args.output)
    
    print(f"✅ Dashboard saved to {args.output}")
    
    return 0


if __name__ == "__main__":
    exit(main())

