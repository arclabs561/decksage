#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27.0", "pyyaml>=6.0"]
# ///
"""
Evaluate similarity quality against gold-standard annotations.

Loads annotated test sets and ground truth, hits the live API, computes
NDCG@5, NDCG@10, MRR, P@K per game and per mode.

Usage:
    uv run scripts/eval_similarity.py [--base-url http://localhost:8001]
    uv run scripts/eval_similarity.py --game magic --verbose
    uv run scripts/eval_similarity.py --json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from math import log2
from pathlib import Path

import httpx
import yaml


RELEVANCE_WEIGHTS = {
    "highly_relevant": 1.0,
    "relevant": 0.75,
    "somewhat_relevant": 0.5,
    "marginally_relevant": 0.25,
    "irrelevant": 0.0,
}

GAMES = ["magic", "pokemon", "yugioh"]
MODES = ["fusion", "substitute", "synergy"]


def load_ground_truth(path: Path) -> list[dict]:
    """Load YAML ground truth file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("tasks", [])


def load_annotated_test_set(path: Path) -> dict[str, dict]:
    """Load JSON annotated test set. Returns {query: {level: [cards]}}."""
    with open(path) as f:
        data = json.load(f)
    # Format varies; handle both list-of-dicts and dict-of-dicts
    if isinstance(data, list):
        result = {}
        for entry in data:
            query = entry.get("query") or entry.get("card_name", "")
            if not query:
                continue
            labels = entry.get("ground_truth") or entry.get("labels", {})
            if labels:
                result[query] = labels
        return result
    return data


def compute_ndcg(predictions: list[str], labels: dict[str, list[str]], k: int) -> float:
    """Compute nDCG@k."""

    def rel_gain(card: str) -> float:
        for level, weight in RELEVANCE_WEIGHTS.items():
            if card in labels.get(level, []):
                return weight
        return 0.0

    def dcg(items: list[str]) -> float:
        return sum(rel_gain(c) / log2(i + 2) for i, c in enumerate(items[:k]))

    ideal = (
        labels.get("highly_relevant", [])
        + labels.get("relevant", [])
        + labels.get("somewhat_relevant", [])
        + labels.get("marginally_relevant", [])
    )
    idcg = dcg(ideal)
    return (dcg(predictions) / idcg) if idcg > 0 else 0.0


def compute_mrr(predictions: list[str], labels: dict[str, list[str]], k: int) -> float:
    """Compute MRR@k (first hit in highly_relevant or relevant)."""
    target = set(labels.get("highly_relevant", [])) | set(labels.get("relevant", []))
    for i, c in enumerate(predictions[:k], 1):
        if c in target:
            return 1.0 / i
    return 0.0


def compute_precision(predictions: list[str], labels: dict[str, list[str]], k: int) -> float:
    """Compute weighted P@k."""
    score = 0.0
    for pred in predictions[:k]:
        for level, weight in RELEVANCE_WEIGHTS.items():
            if pred in labels.get(level, []):
                score += weight
                break
    return score / k if k > 0 else 0.0


def query_api(
    client: httpx.Client,
    base_url: str,
    card: str,
    game: str,
    mode: str,
    k: int = 10,
) -> list[str]:
    """Hit the similarity API and return ranked card names."""
    try:
        resp = client.post(
            f"{base_url}/v1/similar",
            json={
                "card_name": card,
                "game": game,
                "k": k,
                "mode": mode,
            },
            timeout=30.0,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = data.get("results", [])
        return [r.get("card", r.get("name", "")) for r in results]
    except Exception:
        return []


def evaluate_game(
    client: httpx.Client,
    base_url: str,
    game: str,
    test_set: dict[str, dict],
    modes: list[str],
    verbose: bool = False,
) -> dict[str, dict[str, float]]:
    """Evaluate one game across modes. Returns {mode: {metric: value}}."""
    results = {}

    for mode in modes:
        ndcg5s, ndcg10s, mrrs, p5s, p10s = [], [], [], [], []
        skipped = []

        for query, labels in test_set.items():
            predictions = query_api(client, base_url, query, game, mode, k=10)
            if not predictions:
                skipped.append(query)
                continue

            ndcg5s.append(compute_ndcg(predictions, labels, 5))
            ndcg10s.append(compute_ndcg(predictions, labels, 10))
            mrrs.append(compute_mrr(predictions, labels, 10))
            p5s.append(compute_precision(predictions, labels, 5))
            p10s.append(compute_precision(predictions, labels, 10))

            if verbose:
                print(
                    f"  {game}/{mode} {query}: "
                    f"nDCG@5={ndcg5s[-1]:.3f} nDCG@10={ndcg10s[-1]:.3f} "
                    f"MRR={mrrs[-1]:.3f} P@5={p5s[-1]:.3f}"
                )

        def avg(xs):
            return sum(xs) / len(xs) if xs else 0.0

        results[mode] = {
            "ndcg@5": avg(ndcg5s),
            "ndcg@10": avg(ndcg10s),
            "mrr@10": avg(mrrs),
            "p@5": avg(p5s),
            "p@10": avg(p10s),
            "n_evaluated": len(ndcg5s),
            "n_skipped": len(skipped),
        }

        if skipped and verbose:
            print(f"  {game}/{mode} skipped: {skipped}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate similarity quality")
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--game", choices=GAMES, help="Evaluate single game")
    parser.add_argument("--mode", choices=MODES, help="Evaluate single mode")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    games = [args.game] if args.game else GAMES
    modes = [args.mode] if args.mode else MODES

    # Load test data
    test_sets: dict[str, dict[str, dict]] = {}

    # Load ground truth YAML (baseline queries)
    gt_path = project_root / "data" / "annotations" / "ground_truth_v1.yaml"
    if gt_path.exists():
        gt_entries = load_ground_truth(gt_path)
        for entry in gt_entries:
            query = entry.get("query", "")
            labels = entry.get("ground_truth", {})
            game_tag = entry.get("game", "magic")
            if query and labels:
                test_sets.setdefault(game_tag, {})[query] = labels

    # Load annotated JSON test sets
    for game in games:
        ann_path = project_root / "data" / f"test_set_annotated_{game}.json"
        if ann_path.exists():
            loaded = load_annotated_test_set(ann_path)
            test_sets.setdefault(game, {}).update(loaded)

    if not test_sets:
        print("No test data found.", file=sys.stderr)
        sys.exit(1)

    # Run evaluation
    all_results = {}
    client = httpx.Client()

    try:
        for game in games:
            if game not in test_sets:
                if not args.json:
                    print(f"No test data for {game}, skipping.")
                continue

            ts = test_sets[game]
            if not args.json:
                print(f"\n=== {game.upper()} ({len(ts)} queries) ===")

            t0 = time.time()
            game_results = evaluate_game(client, args.base_url, game, ts, modes, args.verbose)
            elapsed = time.time() - t0

            all_results[game] = game_results

            if not args.json:
                for mode, metrics in game_results.items():
                    print(
                        f"  {mode:12s}  nDCG@5={metrics['ndcg@5']:.4f}  "
                        f"nDCG@10={metrics['ndcg@10']:.4f}  "
                        f"MRR={metrics['mrr@10']:.4f}  "
                        f"P@5={metrics['p@5']:.4f}  "
                        f"({metrics['n_evaluated']}/{metrics['n_evaluated'] + metrics['n_skipped']} queries)"
                    )
                print(f"  elapsed: {elapsed:.1f}s")
    finally:
        client.close()

    # Save CSV results
    csv_path = project_root / "data"
    for game, game_results in all_results.items():
        out_path = csv_path / f"eval_{game}_similarity_results.csv"
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "game",
                    "mode",
                    "ndcg@5",
                    "ndcg@10",
                    "mrr@10",
                    "p@5",
                    "p@10",
                    "n_evaluated",
                    "n_skipped",
                ],
            )
            writer.writeheader()
            for mode, metrics in game_results.items():
                writer.writerow({"game": game, "mode": mode, **metrics})
        if not args.json:
            print(f"\nResults saved to {out_path}")

    if args.json:
        print(json.dumps(all_results, indent=2))


if __name__ == "__main__":
    main()
