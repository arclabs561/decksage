#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "scikit-learn>=1.3.0",
# ]
# ///
"""
A/B Testing Framework for Model Comparison (T1.2)

Provides statistical comparison of similarity models with:
- Train/test splits with proper stratification
- Multiple metrics (P@K, MRR, NDCG)
- Statistical significance testing (bootstrap, permutation)
- Comparison reports with confidence intervals
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..utils.paths import PATHS


@dataclass
class ABTestConfig:
    """Configuration for A/B test"""
    train_frac: float = 0.7
    val_frac: float = 0.15
    test_frac: float = 0.15
    seed: int = 42
    k_values: list[int] = None
    n_bootstrap: int = 1000
    confidence: float = 0.95
    min_samples: int = 100

    def __post_init__(self):
        if self.k_values is None:
            self.k_values = [5, 10, 20]
        assert abs(self.train_frac + self.val_frac + self.test_frac - 1.0) < 0.001


@dataclass
class ModelResults:
    """Results for a single model"""
    model_name: str
    metrics: dict[str, float]
    confidence_intervals: dict[str, tuple[float, float]]
    scores: dict[str, list[float]]


@dataclass
class ComparisonResult:
    """Comparison between two models"""
    model_a: str
    model_b: str
    metric: str
    diff: float  # A - B
    p_value: float
    significant: bool
    improvement_pct: float


class ABTestFramework:
    """A/B testing framework for similarity models (T1.2)."""
    
    def __init__(self, config: ABTestConfig | None = None):
        self.config = config or ABTestConfig()
        self.results: dict[str, ModelResults] = {}

    def split_data(
        self,
        pairs_csv: Path | str,
        stratify_by: str | None = None
    ) -> tuple[Any, Any, Any]:
        """
        Split data into train/val/test.
        
        Args:
            pairs_csv: Path to pairs CSV file
            stratify_by: Optional column to stratify by (e.g., 'game')
        
        Returns:
            (train_df, val_df, test_df)
        """
        import pandas as pd
        
        df = pd.read_csv(pairs_csv)
        
        # Set seed for reproducibility
        random.seed(self.config.seed)
        np.random.seed(self.config.seed)
        
        if stratify_by and stratify_by in df.columns:
            # Stratified split
            from sklearn.model_selection import train_test_split
            
            train_df, temp_df = train_test_split(
                df,
                test_size=(1 - self.config.train_frac),
                stratify=df[stratify_by],
                random_state=self.config.seed,
            )
            
            val_size = self.config.val_frac / (self.config.val_frac + self.config.test_frac)
            val_df, test_df = train_test_split(
                temp_df,
                test_size=(1 - val_size),
                stratify=temp_df[stratify_by],
                random_state=self.config.seed,
            )
        else:
            # Random split
            n = len(df)
            indices = np.random.permutation(n)
            train_end = int(n * self.config.train_frac)
            val_end = train_end + int(n * self.config.val_frac)
            
            train_df = df.iloc[indices[:train_end]]
            val_df = df.iloc[indices[train_end:val_end]]
            test_df = df.iloc[indices[val_end:]]
        
        return train_df, val_df, test_df

    def evaluate_model(
        self,
        model_name: str,
        similarity_fn: Callable[[str, int], list[tuple[str, float]]],
        test_set: dict[str, list[str]],
        verbose: bool = True,
    ) -> ModelResults:
        """
        Evaluate a model on test set with confidence intervals.
        
        Args:
            model_name: Name of the model
            similarity_fn: Function (query, k) -> [(card, score), ...]
            test_set: Dict mapping query -> list of relevant cards
            verbose: Print progress
        
        Returns:
            ModelResults with metrics and confidence intervals
        """
        from ..utils.evaluation_with_ci import evaluate_with_confidence
        
        if verbose:
            print(f"\n Evaluating {model_name}...")
        
        # Evaluate with confidence intervals
        results = {}
        ci_results = {}
        all_scores = {}
        
        for k in self.config.k_values:
            def similarity_func(query: str, top_k: int) -> list[tuple[str, float]]:
                return similarity_fn(query, top_k)
            
            eval_result = evaluate_with_confidence(
                test_set=test_set,
                similarity_func=similarity_func,
                top_k=k,
                n_bootstrap=self.config.n_bootstrap,
                confidence=self.config.confidence,
            )
            
            metric_name = f"P@{k}"
            results[metric_name] = eval_result["mean"]
            ci_results[metric_name] = (eval_result["ci_lower"], eval_result["ci_upper"])
            all_scores[metric_name] = eval_result["scores"]
            
            if verbose:
                print(
                    f"  {metric_name}: {eval_result['mean']:.4f} "
                    f"(95% CI: [{eval_result['ci_lower']:.4f}, {eval_result['ci_upper']:.4f}])"
                )
        
        # Compute MRR
        mrr_scores = []
        for query, relevant in test_set.items():
            try:
                predictions = similarity_fn(query, k=20)
                pred_cards = [card for card, _ in predictions]
                
                for rank, card in enumerate(pred_cards, start=1):
                    if card in relevant:
                        mrr_scores.append(1.0 / rank)
                        break
                else:
                    mrr_scores.append(0.0)
            except Exception:
                mrr_scores.append(0.0)
        
        if mrr_scores:
            mrr_mean = np.mean(mrr_scores)
            
            # Bootstrap CI for MRR
            mrr_bootstrap = []
            for _ in range(self.config.n_bootstrap):
                sample = np.random.choice(mrr_scores, size=len(mrr_scores), replace=True)
                mrr_bootstrap.append(np.mean(sample))
            
            alpha = 1 - self.config.confidence
            mrr_ci_lower = np.percentile(mrr_bootstrap, 100 * alpha / 2)
            mrr_ci_upper = np.percentile(mrr_bootstrap, 100 * (1 - alpha / 2))
            
            results["MRR"] = mrr_mean
            ci_results["MRR"] = (mrr_ci_lower, mrr_ci_upper)
            all_scores["MRR"] = mrr_scores
            
            if verbose:
                print(
                    f"  MRR: {mrr_mean:.4f} "
                    f"(95% CI: [{mrr_ci_lower:.4f}, {mrr_ci_upper:.4f}])"
                )
        
        model_results = ModelResults(
            model_name=model_name,
            metrics=results,
            confidence_intervals=ci_results,
            scores=all_scores,
        )
        
        self.results[model_name] = model_results
        return model_results

    def compare_models(
        self,
        model_a: str,
        model_b: str,
        metric: str = "P@10"
    ) -> ComparisonResult:
        """
        Compare two models with statistical significance testing.
        
        Args:
            model_a: Name of first model
            model_b: Name of second model
            metric: Metric to compare (e.g., "P@10", "MRR")
        
        Returns:
            ComparisonResult with p-value and significance
        """
        if model_a not in self.results:
            raise ValueError(f"Model {model_a} not found in results")
        if model_b not in self.results:
            raise ValueError(f"Model {model_b} not found in results")
        
        result_a = self.results[model_a]
        result_b = self.results[model_b]
        
        if metric not in result_a.scores or metric not in result_b.scores:
            raise ValueError(f"Metric {metric} not available for both models")
        
        scores_a = result_a.scores[metric]
        scores_b = result_b.scores[metric]
        
        # Compute difference
        mean_a = np.mean(scores_a)
        mean_b = np.mean(scores_b)
        diff = mean_a - mean_b
        
        # Permutation test for p-value
        combined = np.concatenate([scores_a, scores_b])
        n_a = len(scores_a)
        n_b = len(scores_b)
        
        n_permutations = 10000
        permuted_diffs = []
        for _ in range(n_permutations):
            np.random.shuffle(combined)
            perm_a = combined[:n_a]
            perm_b = combined[n_a:]
            permuted_diffs.append(np.mean(perm_a) - np.mean(perm_b))
        
        # Two-tailed p-value
        p_value = np.mean(np.abs(permuted_diffs) >= np.abs(diff))
        
        # Improvement percentage
        improvement_pct = (diff / mean_b * 100) if mean_b > 0 else 0.0
        
        significant = p_value < (1 - self.config.confidence)
        
        return ComparisonResult(
            model_a=model_a,
            model_b=model_b,
            metric=metric,
            diff=diff,
            p_value=p_value,
            significant=significant,
            improvement_pct=improvement_pct,
        )

    def generate_report(
        self,
        output_path: Path | None = None,
        format: str = "json"
    ) -> dict[str, Any]:
        """
        Generate comparison report.
        
        Args:
            output_path: Optional path to save report
            format: "json" or "html"
        
        Returns:
            Report dictionary
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "config": asdict(self.config),
            "models": {},
            "comparisons": [],
        }
        
        # Add model results
        for model_name, results in self.results.items():
            report["models"][model_name] = {
                "metrics": results.metrics,
                "confidence_intervals": {
                    k: {"lower": v[0], "upper": v[1]}
                    for k, v in results.confidence_intervals.items()
                },
            }
        
        # Add pairwise comparisons
        model_names = list(self.results.keys())
        for i, model_a in enumerate(model_names):
            for model_b in model_names[i + 1:]:
                for metric in self.config.k_values:
                    metric_name = f"P@{metric}"
                    try:
                        comparison = self.compare_models(model_a, model_b, metric_name)
                        report["comparisons"].append(asdict(comparison))
                    except Exception:
                        pass
                
                # MRR comparison
                try:
                    comparison = self.compare_models(model_a, model_b, "MRR")
                    report["comparisons"].append(asdict(comparison))
                except Exception:
                    pass
        
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if format == "json":
                with open(output_path, "w") as f:
                    json.dump(report, f, indent=2)
            elif format == "html":
                self._generate_html_report(report, output_path)
        
        return report

    def _generate_html_report(self, report: dict[str, Any], output_path: Path) -> None:
        """Generate HTML comparison report"""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>A/B Test Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        body {{
            font-family: sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}
        .metric-card {{
            background: #f5f5f5;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
        }}
        .significant {{
            color: green;
            font-weight: bold;
        }}
        .not-significant {{
            color: gray;
        }}
    </style>
</head>
<body>
    <h1>A/B Test Report</h1>
    <p>Generated: {report['timestamp']}</p>
    
    <h2>Model Results</h2>
    <div id="results"></div>
    
    <h2>Comparisons</h2>
    <div id="comparisons"></div>
    
    <script>
        const report = {json.dumps(report)};
        
        // Render results
        const resultsDiv = document.getElementById('results');
        for (const [model, data] of Object.entries(report.models)) {{
            const div = document.createElement('div');
            div.className = 'metric-card';
            div.innerHTML = `<h3>${{model}}</h3>`;
            for (const [metric, value] of Object.entries(data.metrics)) {{
                const ci = data.confidence_intervals[metric];
                div.innerHTML += `<p>${{metric}}: ${{value.toFixed(4)}} (95% CI: [${{ci.lower.toFixed(4)}}, ${{ci.upper.toFixed(4)}}])</p>`;
            }}
            resultsDiv.appendChild(div);
        }}
        
        // Render comparisons
        const compDiv = document.getElementById('comparisons');
        for (const comp of report.comparisons) {{
            const div = document.createElement('div');
            div.className = 'metric-card';
            const sigClass = comp.significant ? 'significant' : 'not-significant';
            div.innerHTML = `
                <h3>${{comp.model_a}} vs ${{comp.model_b}} - ${{comp.metric}}</h3>
                <p class="${{sigClass}}">
                    Difference: ${{comp.diff.toFixed(4)}} (${{comp.improvement_pct > 0 ? '+' : ''}}${{comp.improvement_pct.toFixed(1)}}%)
                    <br>P-value: ${{comp.p_value.toFixed(4)}}
                    <br>Significant: ${{comp.significant ? 'Yes' : 'No'}}
                </p>
            `;
            compDiv.appendChild(div);
        }}
    </script>
</body>
</html>"""
        
        with open(output_path, "w") as f:
            f.write(html)


# Alias for backward compatibility
ABTester = ABTestFramework


def main():
    """Example usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description="A/B test similarity models")
    parser.add_argument("--pairs", type=str, required=True, help="Pairs CSV")
    parser.add_argument("--test-set", type=str, required=True, help="Test set JSON")
    parser.add_argument("--output", type=str, default="ab_test_report.json")
    parser.add_argument("--seed", type=int, default=42)
    
    args = parser.parse_args()
    
    config = ABTestConfig(seed=args.seed)
    tester = ABTestFramework(config)
    
    # Load test set
    with open(args.test_set) as f:
        test_set = json.load(f)
    
    # Example: Compare two models
    # tester.evaluate_model("model_a", similarity_fn_a, test_set)
    # tester.evaluate_model("model_b", similarity_fn_b, test_set)
    # comparison = tester.compare_models("model_a", "model_b")
    # tester.generate_report(args.output)
    
    print("A/B testing framework ready. See ab_testing.py for usage examples.")


if __name__ == "__main__":
    main()
