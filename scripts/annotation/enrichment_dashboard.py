#!/usr/bin/env python3
"""Generate HTML dashboard showing enrichment statistics and usage.

Creates an interactive dashboard showing:
- Enrichment coverage across annotation files
- Quality metrics (validation results)
- Usage statistics (training, API, graph)
- Sample enriched annotations
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.annotation_utils import load_similarity_annotations
from ml.utils.enriched_annotation_utils import get_enrichment_summary, validate_annotation_against_graph


def generate_dashboard(output_path: Path, annotations_dir: Path) -> None:
    """Generate HTML dashboard."""
    
    # Collect data
    annotation_files = list(annotations_dir.glob("*_llm_annotations*.jsonl"))
    
    stats = {
        "total_files": len(annotation_files),
        "total_annotations": 0,
        "enrichment_stats": defaultdict(int),
        "validation_stats": defaultdict(int),
        "files": [],
    }
    
    for ann_file in annotation_files:
        try:
            annotations = load_similarity_annotations(ann_file)
            if not annotations:
                continue
            
            stats["total_annotations"] += len(annotations)
            
            summary = get_enrichment_summary(annotations)
            
            # Validation
            valid_count = 0
            invalid_count = 0
            for ann in annotations:
                validation = validate_annotation_against_graph(ann)
                if validation["is_valid"]:
                    valid_count += 1
                else:
                    invalid_count += 1
            
            file_stats = {
                "file": ann_file.name,
                "count": len(annotations),
                "enriched": summary["with_graph_features"] + summary["with_card_attributes"],
                "enrichment_rate": (summary["with_graph_features"] + summary["with_card_attributes"]) / len(annotations) if annotations else 0.0,
                "valid": valid_count,
                "invalid": invalid_count,
                "graph_features": summary["with_graph_features"],
                "card_attributes": summary["with_card_attributes"],
                "contextual": summary["with_contextual_analysis"],
            }
            
            stats["files"].append(file_stats)
            stats["enrichment_stats"]["with_graph"] += summary["with_graph_features"]
            stats["enrichment_stats"]["with_attributes"] += summary["with_card_attributes"]
            stats["enrichment_stats"]["with_context"] += summary["with_contextual_analysis"]
            stats["validation_stats"]["valid"] += valid_count
            stats["validation_stats"]["invalid"] += invalid_count
            
        except Exception as e:
            print(f"Error processing {ann_file}: {e}")
            continue
    
    # Load usage tracking if available
    usage_tracking_file = annotations_dir / "usage_tracking.json"
    usage_data = {}
    if usage_tracking_file.exists():
        with open(usage_tracking_file) as f:
            usage_data = json.load(f)
    
    # Generate HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Annotation Enrichment Dashboard</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: #2563eb;
        }}
        .stat-label {{
            color: #666;
            margin-top: 5px;
        }}
        table {{
            width: 100%;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        th {{
            background: #2563eb;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #eee;
        }}
        tr:hover {{
            background: #f9fafb;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 500;
        }}
        .badge-success {{
            background: #d1fae5;
            color: #065f46;
        }}
        .badge-warning {{
            background: #fef3c7;
            color: #92400e;
        }}
        .badge-error {{
            background: #fee2e2;
            color: #991b1b;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Annotation Enrichment Dashboard</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{stats['total_files']}</div>
            <div class="stat-label">Annotation Files</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{stats['total_annotations']:,}</div>
            <div class="stat-label">Total Annotations</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{stats['enrichment_stats']['with_attributes']:,}</div>
            <div class="stat-label">With Card Attributes</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{stats['validation_stats']['valid']:,}</div>
            <div class="stat-label">Valid Annotations</div>
        </div>
    </div>
    
    <h2>File Statistics</h2>
    <table>
        <thead>
            <tr>
                <th>File</th>
                <th>Count</th>
                <th>Enriched</th>
                <th>Enrichment Rate</th>
                <th>Graph Features</th>
                <th>Card Attributes</th>
                <th>Contextual</th>
                <th>Valid</th>
                <th>Invalid</th>
            </tr>
        </thead>
        <tbody>
"""
    
    for file_stat in sorted(stats["files"], key=lambda x: x["count"], reverse=True):
        enrichment_badge = "badge-success" if file_stat["enrichment_rate"] > 0.8 else "badge-warning" if file_stat["enrichment_rate"] > 0.5 else "badge-error"
        html += f"""
            <tr>
                <td>{file_stat['file']}</td>
                <td>{file_stat['count']}</td>
                <td>{file_stat['enriched']}</td>
                <td><span class="badge {enrichment_badge}">{file_stat['enrichment_rate']:.1%}</span></td>
                <td>{file_stat['graph_features']}</td>
                <td>{file_stat['card_attributes']}</td>
                <td>{file_stat['contextual']}</td>
                <td>{file_stat['valid']}</td>
                <td>{file_stat['invalid']}</td>
            </tr>
"""
    
    html += """
        </tbody>
    </table>
"""
    
    # Usage statistics
    if usage_data:
        html += """
    <h2>Usage Statistics</h2>
    <div class="stats">
"""
        training_files = len(usage_data.get("training_usage", {}))
        api_queries = len(usage_data.get("api_queries", {}))
        graph_integrations = len(usage_data.get("graph_integration", {}))
        
        html += f"""
        <div class="stat-card">
            <div class="stat-value">{training_files}</div>
            <div class="stat-label">Files Used in Training</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{api_queries}</div>
            <div class="stat-label">API Query Pairs</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{graph_integrations}</div>
            <div class="stat-label">Graph Integrations</div>
        </div>
"""
        html += """
    </div>
"""
    
    html += """
</body>
</html>
"""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = output_path.with_suffix(output_path.suffix + ".tmp")
    with open(temp_file, "w") as f:
        f.write(html)
    temp_file.replace(output_path)
    
    print(f"Dashboard generated: {output_path}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate enrichment dashboard")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("annotations/enrichment_dashboard.html"),
        help="Output HTML file",
    )
    parser.add_argument(
        "--annotations-dir",
        type=Path,
        default=Path("annotations"),
        help="Annotations directory",
    )
    
    args = parser.parse_args()
    
    generate_dashboard(args.output, args.annotations_dir)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


