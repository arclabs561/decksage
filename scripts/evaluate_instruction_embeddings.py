#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
# "pandas>=2.0.0",
# "numpy<2.0.0",
# ]
# ///
"""Evaluate instruction-tuned embeddings (zero-shot vs fine-tuned) on downstream tasks. Compares: - Zero-shot E5-base-v2 (baseline) - Fine-tuned models per task - Task-specific instruction selection impact"""

from __future__ import annotations
import argparse
import json
import logging
from pathlib import Path
from typing import Any
import sys

_script_file = Path(__file__).resolve()
_src_dir = _script_file.parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
from ml.utils.paths import PATHS

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def evaluate_on_test_set(
    embedder: InstructionTunedCardEmbedder,
    test_set_path: Path,
    instruction_type: str = "substitution",
    top_k: int = 10,
) -> dict[str, Any]:
    """Evaluate embedder on test set. Returns: Dictionary with P@10, MRR, and other metrics"""
    with open(test_set_path) as f:
        test_data = json.load(f)
    queries = test_data.get("queries", test_data)
    if not isinstance(queries, dict) or not queries:
        raise ValueError("Expected a nonempty mapping of queries")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    candidates = {
        name
        for labels in queries.values()
        for grade in (
            "highly_relevant",
            "relevant",
            "somewhat_relevant",
            "marginally_relevant",
            "irrelevant",
        )
        for name in labels.get(grade, [])
    }
    precisions = []
    ranks = []
    hit_queries = 0
    for query, labels in queries.items():
        relevant = set(labels.get("highly_relevant", [])) | set(labels.get("relevant", []))
        relevant.discard(query)
        if not relevant:
            continue
        result = embedder.most_similar(
            query, sorted(candidates - {query}), topn=top_k, instruction_type=instruction_type
        )
        names = [card if isinstance(card, str) else card["name"] for card, _ in result[:top_k]]
        hits = relevant.intersection(names)
        precisions.append(len(hits) / top_k)
        hit_queries += bool(hits)
        ranks.append(
            next((1 / rank for rank, name in enumerate(names, 1) if name in relevant), 0.0)
        )
    if not precisions:
        raise ValueError("No labeled queries to evaluate")
    return {
        "total_queries": len(precisions),
        f"found_in_top_{top_k}": hit_queries,
        f"p_at_{top_k}": sum(precisions) / len(precisions),
        "mrr": sum(ranks) / len(ranks),
        "instruction_type": instruction_type,
    }


def compare_models(
    base_model_name: str = "intfloat/e5-base-v2",
    fine_tuned_path: Path | None = None,
    test_set_path: Path | None = None,
    task_type: str = "substitution",
) -> dict[str, Any]:
    """Compare zero-shot vs fine-tuned model performance. Returns: Dictionary with comparison results"""
    if not test_set_path or not test_set_path.exists():
        logger.error(f"Test set not found: {test_set_path}")
        raise FileNotFoundError(test_set_path)
    results = {
        "task_type": task_type,
        "test_set": str(test_set_path),
        "models": {},
    }
    # Evaluate zero-shot baseline
    logger.info(f"Evaluating zero-shot model: {base_model_name}")
    from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder

    zero_shot_embedder = InstructionTunedCardEmbedder(model_name=base_model_name)
    zero_shot_results = evaluate_on_test_set(
        zero_shot_embedder,
        test_set_path,
        instruction_type=task_type,
    )
    results["models"]["zero_shot"] = zero_shot_results
    # Evaluate fine-tuned model if available
    if fine_tuned_path:
        logger.info(f"Evaluating fine-tuned model: {fine_tuned_path}")
        try:
            fine_tuned_embedder = InstructionTunedCardEmbedder(model_name=str(fine_tuned_path))
            fine_tuned_results = evaluate_on_test_set(
                fine_tuned_embedder,
                test_set_path,
                instruction_type=task_type,
            )
            results["models"]["fine_tuned"] = fine_tuned_results
            # Calculate improvement
            p10_improvement = fine_tuned_results["p_at_10"] - zero_shot_results["p_at_10"]
            mrr_improvement = fine_tuned_results["mrr"] - zero_shot_results["mrr"]
            results["improvement"] = {
                "p_at_10_delta": p10_improvement,
                "p_at_10_percent": (p10_improvement / zero_shot_results["p_at_10"] * 100)
                if zero_shot_results["p_at_10"] > 0
                else 0.0,
                "mrr_delta": mrr_improvement,
                "mrr_percent": (mrr_improvement / zero_shot_results["mrr"] * 100)
                if zero_shot_results["mrr"] > 0
                else 0.0,
            }
        except Exception as e:
            raise RuntimeError(f"Fine-tuned model evaluation failed: {e}") from e
    return results


def main() -> int:
    """Evaluate instruction embeddings."""
    parser = argparse.ArgumentParser(description="Evaluate instruction-tuned embeddings")
    parser.add_argument(
        "--base-model", type=str, default="intfloat/e5-base-v2", help="Base model name"
    )
    parser.add_argument("--fine-tuned", type=Path, help="Path to fine-tuned model directory")
    parser.add_argument("--test-set", type=Path, help="Test set JSON")
    parser.add_argument(
        "--task-type", type=str, default="substitution", help="Task type to evaluate"
    )
    parser.add_argument("--output", type=Path, help="Output JSON file")
    args = parser.parse_args()
    # Default test set
    if not args.test_set:
        test_candidates = [
            PATHS.test_magic if hasattr(PATHS, "test_magic") else None,
            Path("experiments/test_set_unified_magic.json"),
        ]
        for cand in test_candidates:
            if cand and isinstance(cand, Path) and cand.exists():
                args.test_set = cand
                break
    if not args.test_set or not args.test_set.exists():
        logger.error("Test set not found. Please provide --test-set")
        return 1
    try:
        results = compare_models(
            base_model_name=args.base_model,
            fine_tuned_path=args.fine_tuned,
            test_set_path=args.test_set,
            task_type=args.task_type,
        )
        # Print results
        logger.info("\n" + "=" * 70)
        logger.info("EVALUATION RESULTS")
        logger.info("=" * 70)
        if "zero_shot" in results["models"]:
            zs = results["models"]["zero_shot"]
            logger.info(f"Zero-shot ({args.base_model}):")
            logger.info(f" P@10: {zs['p_at_10']:.4f}")
            logger.info(f" MRR: {zs['mrr']:.4f}")
        if "fine_tuned" in results["models"]:
            ft = results["models"]["fine_tuned"]
            logger.info(f"Fine-tuned ({args.fine_tuned}):")
            logger.info(f" P@10: {ft['p_at_10']:.4f}")
            logger.info(f" MRR: {ft['mrr']:.4f}")
        if "improvement" in results:
            imp = results["improvement"]
            logger.info(f"Improvement:")
            logger.info(f" P@10: {imp['p_at_10_delta']:+.4f} ({imp['p_at_10_percent']:+.2f}%)")
            logger.info(f" MRR: {imp['mrr_delta']:+.4f} ({imp['mrr_percent']:+.2f}%)")
        # Save results
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2)
            logger.info(f"\n Results saved to {args.output}")
        return 0
    except Exception as e:
        logger.error(f"Error: Evaluation failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit(main())
