#!/usr/bin/env python3
"""
Model Comparison Framework

Compare different embedding models and similarity methods:
- Different dimensions (64, 128, 256)
- Different algorithms (node2vec, DeepWalk, LINE)
- Different p,q parameters
- Different similarity metrics (cosine, euclidean, etc)

Uses annotated test sets for rigorous evaluation.
Supports per-use-case metric stratification (substitute, synergy, meta, etc).
"""

import argparse
import json
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.distance import cityblock, euclidean

try:
    from gensim.models import KeyedVectors

    HAS_GENSIM = True
except ImportError:
    HAS_GENSIM = False


RELEVANCE_GRADES = ("highly_relevant", "relevant", "somewhat_relevant",
                    "marginally_relevant", "irrelevant")


class SimilarityMethod:
    """Different methods to compute similarity from embeddings."""

    @staticmethod
    def cosine(wv, card1: str, card2: str) -> float:
        try:
            return wv.similarity(card1, card2)
        except KeyError:
            return 0.0

    @staticmethod
    def euclidean(wv, card1: str, card2: str) -> float:
        try:
            v1 = wv[card1]
            v2 = wv[card2]
            dist = euclidean(v1, v2)
            return 1.0 / (1.0 + dist)
        except KeyError:
            return 0.0

    @staticmethod
    def manhattan(wv, card1: str, card2: str) -> float:
        try:
            v1 = wv[card1]
            v2 = wv[card2]
            dist = cityblock(v1, v2)
            return 1.0 / (1.0 + dist)
        except KeyError:
            return 0.0


class ModelComparator:
    """Compare multiple embedding models with per-use-case stratification."""

    def __init__(self, test_set_file: str):
        with open(test_set_file) as f:
            raw = json.load(f)

        # Handle both formats: {queries: {...}} and flat {card: {...}}
        if "queries" in raw and isinstance(raw["queries"], dict):
            self.test_set = raw["queries"]
        else:
            self.test_set = raw

        print(f"  Loaded test set: {len(self.test_set)} queries")

        # Index queries by use_case
        self._use_case_index: dict[str, list[str]] = defaultdict(list)
        for query, gt in self.test_set.items():
            uc = gt.get("use_case", "unknown")
            self._use_case_index[uc].append(query)

        uc_counts = {uc: len(qs) for uc, qs in sorted(self._use_case_index.items())}
        print(f"  Use-case distribution: {uc_counts}")

    def evaluate_model(
        self,
        wv,
        similarity_fn: Callable = SimilarityMethod.cosine,
        k_values: list[int] | None = None,
        stratify_by_use_case: bool = False,
    ) -> dict:
        """Evaluate model on test set.

        When stratify_by_use_case=True, returns:
            {"overall": {...}, "by_use_case": {"substitute": {...}, ...}}
        Otherwise returns flat metrics dict (backward compatible).
        """
        if k_values is None:
            k_values = [5, 10, 20]

        # Collect per-query metrics
        per_query: dict[str, dict[str, float]] = {}
        for query, ground_truth in self.test_set.items():
            if query not in wv:
                continue

            all_test_cards = []
            for grade in RELEVANCE_GRADES:
                all_test_cards.extend(ground_truth.get(grade, []))

            scored_cards = []
            for card in all_test_cards:
                sim = similarity_fn(wv, query, card)
                scored_cards.append((card, sim))
            scored_cards.sort(key=lambda x: x[1], reverse=True)

            qm: dict[str, float] = {}
            for k in k_values:
                qm[f"P@{k}"] = self._precision_at_k(scored_cards[:k], ground_truth)
                qm[f"NDCG@{k}"] = self._ndcg_at_k(scored_cards[:k], ground_truth, k)
            qm["MRR"] = self._mrr(scored_cards, ground_truth)
            per_query[query] = qm

        # Aggregate: overall
        overall = self._aggregate_metrics(per_query, list(per_query.keys()))

        if not stratify_by_use_case:
            return overall

        # Aggregate: per use_case
        by_use_case: dict[str, dict] = {}
        for uc, queries in self._use_case_index.items():
            uc_queries = [q for q in queries if q in per_query]
            if uc_queries:
                agg = self._aggregate_metrics(per_query, uc_queries)
                agg["n_queries"] = len(uc_queries)
                by_use_case[uc] = agg

        return {"overall": overall, "by_use_case": by_use_case}

    def _aggregate_metrics(
        self,
        per_query: dict[str, dict[str, float]],
        query_subset: list[str],
    ) -> dict[str, float]:
        """Average metrics over a subset of queries."""
        if not query_subset:
            return {}
        metric_names = list(next(iter(per_query.values())).keys())
        return {
            m: float(np.mean([per_query[q][m] for q in query_subset]))
            for m in metric_names
        }

    def _precision_at_k(self, predictions: list, ground_truth: dict) -> float:
        relevance_weights = {
            "highly_relevant": 1.0,
            "relevant": 0.75,
            "somewhat_relevant": 0.5,
            "marginally_relevant": 0.25,
            "irrelevant": 0.0,
        }
        score = 0.0
        for card, _ in predictions:
            for level, weight in relevance_weights.items():
                if card in ground_truth.get(level, []):
                    score += weight
                    break
        return score / len(predictions) if predictions else 0.0

    def _ndcg_at_k(self, predictions: list, ground_truth: dict, k: int) -> float:
        relevance_scores = {
            "highly_relevant": 4,
            "relevant": 3,
            "somewhat_relevant": 2,
            "marginally_relevant": 1,
            "irrelevant": 0,
        }
        dcg = 0.0
        for i, (card, _) in enumerate(predictions[:k], 1):
            rel = 0
            for level, score in relevance_scores.items():
                if card in ground_truth.get(level, []):
                    rel = score
                    break
            dcg += rel / np.log2(i + 1)

        all_rels = []
        for level, cards in ground_truth.items():
            score = relevance_scores.get(level, 0)
            if isinstance(cards, list):
                all_rels.extend([score] * len(cards))
        all_rels.sort(reverse=True)
        idcg = sum(rel / np.log2(i + 1) for i, rel in enumerate(all_rels[:k], 1))

        return dcg / idcg if idcg > 0 else 0.0

    def _mrr(self, predictions: list, ground_truth: dict) -> float:
        highly_relevant = set(ground_truth.get("highly_relevant", []))
        relevant = set(ground_truth.get("relevant", []))
        target_set = highly_relevant | relevant
        for rank, (card, _) in enumerate(predictions, 1):
            if card in target_set:
                return 1.0 / rank
        return 0.0

    def compare_models(
        self,
        models: dict[str, str],
        similarity_methods: dict[str, Callable] | None = None,
        stratify_by_use_case: bool = False,
    ) -> pd.DataFrame:
        """Compare multiple models side-by-side.

        Returns DataFrame with comparison results. When stratify_by_use_case=True,
        includes per-use-case rows alongside overall rows.
        """
        if similarity_methods is None:
            similarity_methods = {"cosine": SimilarityMethod.cosine}

        results = []
        for model_name, wv_path in models.items():
            print(f"\n  Evaluating {model_name}...")
            wv = KeyedVectors.load(wv_path)

            for sim_name, sim_fn in similarity_methods.items():
                print(f"    Using {sim_name} similarity...")
                metrics = self.evaluate_model(
                    wv, sim_fn, stratify_by_use_case=stratify_by_use_case
                )

                if stratify_by_use_case:
                    # Overall row
                    results.append({
                        "model": model_name,
                        "similarity": sim_name,
                        "use_case": "overall",
                        **metrics["overall"],
                    })
                    # Per-use-case rows
                    for uc, uc_metrics in sorted(metrics["by_use_case"].items()):
                        results.append({
                            "model": model_name,
                            "similarity": sim_name,
                            "use_case": uc,
                            **uc_metrics,
                        })
                else:
                    results.append({
                        "model": model_name,
                        "similarity": sim_name,
                        **metrics,
                    })

        return pd.DataFrame(results)


def main():
    parser = argparse.ArgumentParser(description="Compare embedding models")
    parser.add_argument("--test-set", type=str, required=True, help="Test set JSON")
    parser.add_argument("--models", nargs="+", required=True, help="Model .wv files")
    parser.add_argument(
        "--methods",
        nargs="+",
        choices=["cosine", "euclidean", "manhattan"],
        default=["cosine"],
        help="Similarity methods",
    )
    parser.add_argument("--output", type=str, help="Output CSV")
    parser.add_argument(
        "--by-use-case",
        action="store_true",
        help="Report metrics per use-case (substitute, synergy, etc)",
    )
    args = parser.parse_args()

    if not HAS_GENSIM:
        print("Error: gensim not installed")
        return 1

    models = {}
    for model_path in args.models:
        name = Path(model_path).stem
        models[name] = model_path

    similarity_fns = {}
    for method in args.methods:
        if method == "cosine":
            similarity_fns["cosine"] = SimilarityMethod.cosine
        elif method == "euclidean":
            similarity_fns["euclidean"] = SimilarityMethod.euclidean
        elif method == "manhattan":
            similarity_fns["manhattan"] = SimilarityMethod.manhattan

    comparator = ModelComparator(args.test_set)
    results_df = comparator.compare_models(
        models, similarity_fns, stratify_by_use_case=args.by_use_case
    )

    print("\n" + "=" * 80)
    print("MODEL COMPARISON RESULTS")
    print("=" * 80)

    if args.by_use_case:
        # Show overall first, then per-use-case
        overall = results_df[results_df["use_case"] == "overall"]
        per_uc = results_df[results_df["use_case"] != "overall"]

        print("\n-- Overall --")
        overall_display = overall.drop(columns=["use_case"])
        overall_display = overall_display.sort_values("P@10", ascending=False)
        print(overall_display.to_string(index=False, float_format="%.4f"))

        print("\n-- Per Use-Case --")
        per_uc = per_uc.sort_values(["model", "use_case"])
        print(per_uc.to_string(index=False, float_format="%.4f"))
    else:
        results_df = results_df.sort_values("P@10", ascending=False)
        print(results_df.to_string(index=False, float_format="%.4f"))

    if args.output:
        results_df.to_csv(args.output, index=False)
        print(f"\n  Saved results to {args.output}")

    # Winner (from overall if stratified)
    if args.by_use_case:
        best_df = results_df[results_df["use_case"] == "overall"]
    else:
        best_df = results_df
    best = best_df.sort_values("P@10", ascending=False).iloc[0]
    print(f"\n  Best model: {best['model']} ({best.get('similarity', '')})")
    print(f"    P@10: {best['P@10']:.4f}")
    print(f"    NDCG@10: {best['NDCG@10']:.4f}")
    print(f"    MRR: {best['MRR']:.4f}")

    html_file = (
        Path(args.output).parent / "comparison_report.html"
        if args.output
        else Path("comparison_report.html")
    )
    generate_html_comparison(results_df, html_file, args)
    print(f"\n  HTML report: {html_file}")
    return 0


def generate_html_comparison(df, output_file, args):
    """Generate HTML comparison report with optional per-use-case breakdown."""
    from datetime import datetime

    has_use_case = "use_case" in df.columns
    if has_use_case:
        overall_df = df[df["use_case"] == "overall"]
        per_uc_df = df[df["use_case"] != "overall"]
    else:
        overall_df = df
        per_uc_df = pd.DataFrame()

    best = overall_df.sort_values("P@10", ascending=False).iloc[0]

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light dark">
<title>Model Comparison Report</title>
<style>
:root {{
    color-scheme: light dark;
    --bg: #ffffff; --fg: #1a1a1a; --fg-muted: #666666;
    --border: #e5e5e5; --accent: #0066cc; --code-bg: #f6f6f6;
    --success: #16a34a;
}}
@media (prefers-color-scheme: dark) {{
    :root {{
        --bg: #1a1a1a; --fg: #e0e0e0; --fg-muted: #999999;
        --border: #333333; --accent: #4a9eff; --code-bg: #2d2d2d;
        --success: #22c55e;
    }}
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    background: var(--bg); color: var(--fg);
    line-height: 1.6; padding: clamp(1rem, 3vw, 2rem);
}}
.container {{ max-width: 1400px; margin: 0 auto; }}
header {{ border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 2rem; }}
h1 {{ font-size: clamp(1.5rem, 4vw, 2rem); font-weight: 600; letter-spacing: -0.02em; }}
.timestamp {{ color: var(--fg-muted); font-size: 0.85rem; }}
h2 {{ font-size: 1.3rem; font-weight: 600; margin: 2rem 0 0.75rem 0; }}
.winner {{
    background: var(--code-bg); border: 2px solid var(--success);
    border-radius: 4px; padding: 1.5rem; margin: 1.5rem 0;
}}
.winner h2 {{ margin-top: 0; color: var(--success); font-size: 1.2rem; }}
table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.85rem; }}
th, td {{ padding: 0.5rem; text-align: left; border: 1px solid var(--border); }}
th {{ background: var(--code-bg); font-weight: 600; }}
tr:hover {{ background: var(--code-bg); }}
.metric {{
    font-family: "SF Mono", Monaco, "Cascadia Code", Consolas, monospace;
    font-size: 0.95em;
}}
.best {{ background: rgba(22, 163, 74, 0.1); }}
.uc-label {{
    display: inline-block; padding: 2px 6px; border-radius: 3px;
    font-size: 0.8em; font-weight: 600;
    background: var(--code-bg); border: 1px solid var(--border);
}}
.viz {{ margin: 1.5rem 0; }}
.viz p {{ margin: 0.25rem 0; }}
.bar {{
    background: var(--accent); height: 18px;
    border-radius: 2px; display: inline-block;
}}
</style>
</head>
<body>
<div class="container">
<header>
    <h1>Model Comparison Report</h1>
    <p class="timestamp">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
</header>

<div class="winner">
    <h2>Winner: {best["model"]} ({best.get("similarity", "")})</h2>
    <p>
        <span class="metric">P@10: {best["P@10"]:.4f}</span> |
        <span class="metric">NDCG@10: {best["NDCG@10"]:.4f}</span> |
        <span class="metric">MRR: {best["MRR"]:.4f}</span>
    </p>
</div>

<h2>Overall Results</h2>
<table>
<thead>
<tr>
    <th>Rank</th><th>Model</th><th>Similarity</th>
    <th>P@5</th><th>P@10</th><th>P@20</th>
    <th>NDCG@5</th><th>NDCG@10</th><th>NDCG@20</th>
    <th>MRR</th>
</tr>
</thead>
<tbody>
"""
    sorted_overall = overall_df.sort_values("P@10", ascending=False)
    for rank, (_, row) in enumerate(sorted_overall.iterrows(), 1):
        row_class = ' class="best"' if rank == 1 else ""
        html += f"""<tr{row_class}>
    <td>{rank}</td>
    <td><strong>{row["model"]}</strong></td>
    <td>{row.get("similarity", "")}</td>
    <td class="metric">{row.get("P@5", 0):.4f}</td>
    <td class="metric">{row.get("P@10", 0):.4f}</td>
    <td class="metric">{row.get("P@20", 0):.4f}</td>
    <td class="metric">{row.get("NDCG@5", 0):.4f}</td>
    <td class="metric">{row.get("NDCG@10", 0):.4f}</td>
    <td class="metric">{row.get("NDCG@20", 0):.4f}</td>
    <td class="metric">{row.get("MRR", 0):.4f}</td>
</tr>
"""
    html += "</tbody></table>\n"

    # Per-use-case breakdown
    if not per_uc_df.empty:
        html += """
<h2>Per Use-Case Breakdown</h2>
<p style="color: var(--fg-muted); font-size: 0.85rem; margin-bottom: 0.5rem;">
    Metrics stratified by query use-case. A model good at substitutes
    may underperform on synergy queries (or vice versa).
</p>
<table>
<thead>
<tr>
    <th>Model</th><th>Use Case</th><th>N</th>
    <th>P@5</th><th>P@10</th>
    <th>NDCG@5</th><th>NDCG@10</th>
    <th>MRR</th>
</tr>
</thead>
<tbody>
"""
        sorted_uc = per_uc_df.sort_values(["model", "use_case"])
        for _, row in sorted_uc.iterrows():
            n = int(row.get("n_queries", 0))
            html += f"""<tr>
    <td>{row["model"]}</td>
    <td><span class="uc-label">{row["use_case"]}</span></td>
    <td>{n}</td>
    <td class="metric">{row.get("P@5", 0):.4f}</td>
    <td class="metric">{row.get("P@10", 0):.4f}</td>
    <td class="metric">{row.get("NDCG@5", 0):.4f}</td>
    <td class="metric">{row.get("NDCG@10", 0):.4f}</td>
    <td class="metric">{row.get("MRR", 0):.4f}</td>
</tr>
"""
        html += "</tbody></table>\n"

    # Visual comparison
    html += """
<h2>P@10 Comparison (Visual)</h2>
<div class="viz">
"""
    max_p10 = overall_df["P@10"].max() if overall_df["P@10"].max() > 0 else 1
    for _, row in sorted_overall.iterrows():
        width = int((row["P@10"] / max_p10) * 300)
        html += f"""<p>
    <strong style="display: inline-block; width: 180px; font-size: 0.9em;">{row["model"]}</strong>
    <span class="bar" style="width: {width}px;"></span>
    <span class="metric" style="margin-left: 8px;">{row["P@10"]:.4f}</span>
</p>
"""
    html += "</div>\n</div>\n</body>\n</html>\n"

    with open(output_file, "w") as f:
        f.write(html)


if __name__ == "__main__":
    import sys

    sys.exit(main())
