#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sentence-transformers>=2.2.0",
#     "torch>=2.0.0",
#     "numpy>=1.24.0",
#     "gensim>=4.3.0",
#     "datasets>=2.0.0",
#     "accelerate>=1.1.0",
# ]
# ///
"""
Evaluate fine-tuned E5 vs zero-shot E5 on substitution + contextual recall.

Compares:
1. Zero-shot E5-base-v2 (default text_embed)
2. Fine-tuned E5 (multi-task, mode-aware)

On:
- Substitution nDCG: do text embeddings rank functional substitutes better?
- Contextual recall: does the fine-tuned model find more alternatives?
- Synergy nDCG: does fine-tuning help or hurt synergy ranking?

Usage:
    uv run scripts/evaluation/eval_e5_finetuned.py --game magic
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))


def dcg(scores: list[float], k: int) -> float:
    return sum(s / np.log2(i + 2) for i, s in enumerate(scores[:k]))


def ndcg_at_k(relevance: list[float], k: int) -> float:
    actual = dcg(relevance, k)
    ideal = dcg(sorted(relevance, reverse=True), k)
    return actual / ideal if ideal > 0 else 0.0


def evaluate_text_embedder(embedder, test_data: dict, card_data: dict, k: int = 10) -> dict:
    """Evaluate a text embedder on substitution + synergy + recall."""
    queries = test_data.get("queries", {})

    mode_scores = {"substitution": [], "synergy": [], "meta": []}
    recall_hits = 0
    recall_total = 0

    mode_field = {
        "substitution": "functional_score",
        "synergy": "synergy_score",
        "meta": "meta_relevance",
    }

    for query_card, labels in queries.items():
        annotations = labels.get("annotations", [])
        if not annotations:
            continue

        # Build candidate list from annotations
        candidates = []
        for ann in annotations:
            cand = ann.get("candidate", "")
            if cand:
                candidates.append(ann)

        if len(candidates) < 2:
            continue

        # Encode query
        query_info = card_data.get(query_card, query_card)
        try:
            q_emb = embedder.embed_card(query_info, instruction_type="substitution")
        except Exception:
            continue

        # Encode all candidates and rank by similarity
        cand_sims = []
        for ann in candidates:
            cand_name = ann["candidate"]
            cand_info = card_data.get(cand_name, cand_name)
            try:
                c_emb = embedder.embed_card(cand_info, instruction_type="substitution")
                sim = float(
                    np.dot(q_emb, c_emb) / (np.linalg.norm(q_emb) * np.linalg.norm(c_emb) + 1e-8)
                )
                cand_sims.append((ann, sim))
            except Exception:
                continue

        if not cand_sims:
            continue

        # Sort by embedding similarity (descending)
        cand_sims.sort(key=lambda x: x[1], reverse=True)

        # Evaluate per mode
        for mode, field in mode_field.items():
            relevance = [float(ann.get(field, 0.0) or 0.0) for ann, _ in cand_sims]
            if any(r > 0 for r in relevance):
                mode_scores[mode].append(ndcg_at_k(relevance, k))

        # Recall: substitution pairs with high substitutability
        expected = {
            ann["candidate"]
            for ann in candidates
            if ann.get("mode") == "substitution"
            and float(ann.get("substitutability", 0.0) or 0.0) >= 0.5
        }
        if expected:
            top_k_cards = {ann["candidate"] for ann, _ in cand_sims[:k]}
            recall_hits += len(top_k_cards & expected)
            recall_total += len(expected)

    results = {}
    for mode, scores in mode_scores.items():
        results[f"{mode}_ndcg"] = float(np.mean(scores)) if scores else 0.0
        results[f"{mode}_queries"] = len(scores)
    results["recall"] = recall_hits / recall_total if recall_total > 0 else 0.0
    results["recall_hits"] = recall_hits
    results["recall_total"] = recall_total
    return results


def load_card_data(game: str) -> dict:
    """Load card metadata for text embedding."""
    try:
        import pandas as pd
    except ImportError:
        return {}
    path = DATA_DIR / "processed" / f"card_attributes_{game}_enriched.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path, low_memory=False)
    result = {}
    for _, row in df.iterrows():
        n = str(row.get("name", ""))
        if n:
            result[n] = {
                k: v for k, v in row.to_dict().items() if not (isinstance(v, float) and v != v)
            }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", default="magic")
    parser.add_argument("--finetuned-model", default="data/embeddings/e5_finetuned_magic_multitask")
    parser.add_argument("--base-model", default="intfloat/e5-base-v2")
    args = parser.parse_args()

    # Load test set
    test_path = DATA_DIR / "test_sets" / f"annotated_{args.game}_v2.json"
    with open(test_path) as f:
        test_data = json.load(f)
    print(f"Test set: {len(test_data.get('queries', {}))} queries")

    # Load card data
    card_data = load_card_data(args.game)
    print(f"Card metadata: {len(card_data)} cards")

    from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder

    # Evaluate zero-shot
    print(f"\n{'=' * 60}")
    print(f"Zero-shot E5: {args.base_model}")
    print(f"{'=' * 60}")
    zs_embedder = InstructionTunedCardEmbedder(model_name=args.base_model)
    zs_results = evaluate_text_embedder(zs_embedder, test_data, card_data)
    for k, v in zs_results.items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    # Evaluate fine-tuned
    ft_path = Path(args.finetuned_model)
    if not ft_path.exists():
        ft_path = PROJECT_ROOT / args.finetuned_model
    if ft_path.exists():
        print(f"\n{'=' * 60}")
        print(f"Fine-tuned E5: {ft_path}")
        print(f"{'=' * 60}")
        ft_embedder = InstructionTunedCardEmbedder(model_name=str(ft_path))
        ft_results = evaluate_text_embedder(ft_embedder, test_data, card_data)
        for k, v in ft_results.items():
            print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

        # Delta
        print(f"\n{'=' * 60}")
        print("DELTA (fine-tuned - zero-shot)")
        print(f"{'=' * 60}")
        for k in zs_results:
            if isinstance(zs_results[k], float):
                delta = ft_results[k] - zs_results[k]
                sign = "+" if delta >= 0 else ""
                print(f"  {k}: {sign}{delta:.4f}")
    else:
        print(f"\nFine-tuned model not found at {ft_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
