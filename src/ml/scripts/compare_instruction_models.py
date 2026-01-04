#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sentence-transformers",
# ]
# ///
"""
Compare instruction-tuned embedding models (E5-base-v2 vs E5-Mistral vs BGE-M3).

Tests zero-shot performance on card substitution tasks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
from ..utils.logging_config import log_exception, setup_script_logging
from ..utils.paths import PATHS


logger = setup_script_logging()


def compare_instruction_models(
    test_set_path: Path,
    output_path: Path | None = None,
    models: list[str] | None = None,
    sample_size: int | None = None,
) -> dict[str, Any]:
    """
    Compare multiple instruction-tuned embedding models.

    Args:
        test_set_path: Path to test set with queries and labels
        output_path: Path to save comparison results
        models: List of model names to compare
        sample_size: Optional limit on number of test queries

    Returns:
        Dictionary with comparison results
    """
    if models is None:
        models = [
            "intfloat/e5-base-v2",
            "intfloat/e5-mistral-7b-instruct",
            "BAAI/bge-m3",
        ]

    logger.info("=" * 70)
    logger.info("INSTRUCTION-TUNED MODEL COMPARISON")
    logger.info("=" * 70)
    logger.info(f"Models to compare: {models}")
    logger.info("")

    # Load test set
    logger.info(f"Loading test set from {test_set_path}...")
    with open(test_set_path) as f:
        test_data = json.load(f)

    test_set = test_data.get("queries", test_data)
    if sample_size:
        test_set = dict(list(test_set.items())[:sample_size])

    logger.info(f"Loaded {len(test_set)} test queries")
    logger.info("")

    results = {
        "models": models,
        "test_set_size": len(test_set),
        "results": {},
    }

    for model_name in models:
        logger.info(f"\n{'=' * 70}")
        logger.info(f"Testing {model_name}")
        logger.info(f"{'=' * 70}")

        try:
            # Initialize embedder
            logger.info(f"Loading model {model_name}...")
            embedder = InstructionTunedCardEmbedder(model_name=model_name)
            logger.info("✓ Model loaded")

            # Test on sample queries
            model_results = {
                "model_name": model_name,
                "loaded": True,
                "tested_queries": 0,
                "correct_predictions": 0,
                "similarities": [],
            }

            logger.info("Testing on sample queries...")
            for query, labels in list(test_set.items())[:10]:  # Sample first 10
                if not isinstance(labels, dict):
                    labels = {"labels": labels if isinstance(labels, list) else [labels]}

                label_list = labels.get("labels", [])
                if not label_list:
                    continue

                # Get similarity to first label
                candidate = label_list[0]
                try:
                    sim = embedder.similarity(query, candidate, instruction_type="substitution")
                    model_results["similarities"].append(
                        {
                            "query": query,
                            "candidate": candidate,
                            "similarity": float(sim),
                        }
                    )
                    model_results["tested_queries"] += 1

                    if sim > 0.7:  # Threshold for "correct"
                        model_results["correct_predictions"] += 1
                except Exception as e:
                    logger.warning(f"Error testing {query} -> {candidate}: {e}")

            if model_results["tested_queries"] > 0:
                model_results["accuracy"] = (
                    model_results["correct_predictions"] / model_results["tested_queries"]
                )
                avg_sim = sum(s["similarity"] for s in model_results["similarities"]) / len(
                    model_results["similarities"]
                )
                model_results["avg_similarity"] = avg_sim
            else:
                model_results["accuracy"] = 0.0
                model_results["avg_similarity"] = 0.0

            results["results"][model_name] = model_results
            logger.info(
                f"✓ {model_name} tested: {model_results['tested_queries']} queries, accuracy: {model_results['accuracy']:.2%}"
            )

        except Exception as e:
            log_exception(logger, f"{model_name} failed", e, include_context=True)
            results["results"][model_name] = {
                "model_name": model_name,
                "loaded": False,
                "error": str(e),
            }

    # Save results
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"\n✓ Comparison results saved to {output_path}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare instruction-tuned embedding models")
    parser.add_argument(
        "--test-set",
        type=Path,
        default=PATHS.test_magic,
        help="Path to test set",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PATHS.experiments / "instruction_model_comparison.json",
        help="Path to save comparison results",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["intfloat/e5-base-v2", "intfloat/e5-mistral-7b-instruct"],
        help="Models to compare",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        help="Limit number of test queries",
    )
    args = parser.parse_args()

    try:
        results = compare_instruction_models(
            args.test_set,
            args.output,
            args.models,
            args.sample_size,
        )

        logger.info("\n" + "=" * 70)
        logger.info("COMPARISON SUMMARY")
        logger.info("=" * 70)
        for model_name, model_results in results["results"].items():
            if model_results.get("loaded"):
                acc = model_results.get("accuracy", 0.0)
                avg_sim = model_results.get("avg_similarity", 0.0)
                logger.info(f"✓ {model_name}: Accuracy {acc:.2%}, Avg Similarity {avg_sim:.4f}")
            else:
                logger.info(f"✗ {model_name}: Failed to load")

        return 0

    except Exception as e:
        log_exception(logger, "Comparison failed", e, include_context=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
