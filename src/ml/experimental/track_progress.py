#!/usr/bin/env python3
"""
Track annotation quality and model performance over time.

Generates trend visualization showing:
- Dataset size growth
- Model performance improvement
- Inter-annotator agreement
- Coverage expansion
"""

import json
from pathlib import Path


def load_all_metrics():
    """Load all quality metric snapshots"""
    metrics_dir = Path("../../annotations/metrics")

    snapshots = []
    for json_file in sorted(metrics_dir.glob("quality_*.json")):
        with open(json_file) as f:
            snapshots.append(json.load(f))

    return snapshots


def plot_progress(snapshots, output_file="progress_dashboard.html"):
    """Generate HTML dashboard with progress charts"""

    if not snapshots:
        print("No metrics to plot yet")
        return

    # Extract data
    dates = [s["date"] for s in snapshots]
    dataset_sizes = [s["dataset_metrics"]["total_queries"] for s in snapshots]
    p10_scores = [s["model_performance"]["node2vec_500decks"]["P@10"] for s in snapshots]

    # Create HTML with embedded Chart.js
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="color-scheme" content="light dark">
    <title>Annotation Progress Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            color-scheme: light dark;
            --bg: #ffffff; --fg: #1a1a1a;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{ --bg: #1a1a1a; --fg: #e0e0e0; }}
        }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                background: var(--bg); color: var(--fg); padding: 2rem; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ font-size: 2rem; font-weight: 600; margin-bottom: 1rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 2rem; }}
        .chart {{ background: var(--bg); padding: 1rem; border: 1px solid #e5e5e5; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Annotation Progress Dashboard</h1>

        <div class="grid">
            <div class="chart">
                <h2>Dataset Growth</h2>
                <canvas id="datasetChart"></canvas>
            </div>

            <div class="chart">
                <h2>Model Performance (P@10)</h2>
                <canvas id="performanceChart"></canvas>
            </div>
        </div>

        <h2>Latest Metrics ({dates[-1]})</h2>
        <table style="width: 100%; border-collapse: collapse; margin-top: 1rem;">
            <tr>
                <th style="border: 1px solid #e5e5e5; padding: 0.5rem;">Metric</th>
                <th style="border: 1px solid #e5e5e5; padding: 0.5rem;">Value</th>
            </tr>
            <tr>
                <td style="border: 1px solid #e5e5e5; padding: 0.5rem;">Total Queries</td>
                <td style="border: 1px solid #e5e5e5; padding: 0.5rem;">{dataset_sizes[-1]}</td>
            </tr>
            <tr>
                <td style="border: 1px solid #e5e5e5; padding: 0.5rem;">Node2Vec P@10</td>
                <td style="border: 1px solid #e5e5e5; padding: 0.5rem;">{p10_scores[-1]:.4f}</td>
            </tr>
        </table>
    </div>

    <script>
        const datasetCtx = document.getElementById('datasetChart').getContext('2d');
        new Chart(datasetCtx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(dates)},
                datasets: [{{
                    label: 'Total Queries',
                    data: {json.dumps(dataset_sizes)},
                    borderColor: '#0066cc',
                    tension: 0.1
                }}]
            }},
            options: {{ responsive: true }}
        }});

        const perfCtx = document.getElementById('performanceChart').getContext('2d');
        new Chart(perfCtx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(dates)},
                datasets: [{{
                    label: 'P@10',
                    data: {json.dumps(p10_scores)},
                    borderColor: '#16a34a',
                    tension: 0.1
                }}]
            }},
            options: {{
                responsive: true,
                scales: {{
                    y: {{ beginAtZero: true, max: 1.0 }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""

    with open(output_file, "w") as f:
        f.write(html)

    print(f"📊 Progress dashboard: {output_file}")


if __name__ == "__main__":
    snapshots = load_all_metrics()
    plot_progress(snapshots, "../../assets/experiments/annotation_progress.html")
