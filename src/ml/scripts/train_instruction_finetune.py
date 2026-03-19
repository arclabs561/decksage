#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "sentence-transformers>=2.2.0",
#     "torch>=2.0.0",
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "datasets>=2.0.0",
#     "accelerate>=1.1.0",
# ]
# ///
"""
Fine-tune instruction-tuned embeddings (E5/BGE) on card similarity tasks.

Multi-task training with mode-aware pair selection:
- Each annotation has a mode (substitution/synergy/meta) and graded scores
- Pairs are routed to the correct instruction prefix based on mode
- Graph edges (co-occurrence) are used ONLY for synergy/completion tasks
- Graded similarity scores are used as labels (not binary 1.0/0.0)

Usage:
    # Multi-task (recommended): trains all tasks with correct instructions
    uv run src/ml/scripts/train_instruction_finetune.py \\
        --base-model intfloat/e5-base-v2 \\
        --output data/embeddings/e5_finetuned_magic \\
        --test-set data/test_sets/annotated_magic_v2.json \\
        --multi-task --epochs 3

    # Single task (mode-filtered):
    uv run src/ml/scripts/train_instruction_finetune.py \\
        --base-model intfloat/e5-base-v2 \\
        --output data/embeddings/e5_finetuned_magic_sub \\
        --test-set data/test_sets/annotated_magic_v2.json \\
        --task-type substitution --epochs 3
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path
from typing import Any

try:
    from sentence_transformers import SentenceTransformer, InputExample, losses, evaluation
    from torch.utils.data import DataLoader
    import torch

    HAS_DEPS = True
except ImportError as e:
    HAS_DEPS = False
    print(f"Missing dependencies: {e}")

import sys

_script_file = Path(__file__).resolve()
_src_dir = _script_file.parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from ml.similarity.instruction_tuned_embeddings import InstructionTunedCardEmbedder
from ml.utils.paths import PATHS
from ml.utils.path_resolution import resolve_path

try:
    from ml.utils.logging_config import setup_script_logging, log_exception
except ImportError:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    def setup_script_logging():
        return logger

    def log_exception(logger, msg, e, include_context=False):
        logger.error(f"{msg}: {e}", exc_info=True)


logger = setup_script_logging()

# Mode -> annotation score field
MODE_SCORE_FIELD = {
    "substitution": "functional_score",
    "synergy": "synergy_score",
    "meta": "meta_relevance",
}

# Mode -> instruction key
MODE_INSTRUCTION = {
    "substitution": "substitution",
    "synergy": "synergy",
    "meta": "similar",
}


def _get_instruction(task_type: str) -> str:
    return InstructionTunedCardEmbedder.DEFAULT_INSTRUCTIONS.get(
        task_type, f"query: Find {task_type} for"
    )


def load_training_pairs_multitask(
    test_set_path: Path | None = None,
    graph_path: Path | None = None,
    min_score: float = 0.3,
    max_graph_edges: int = 5000,
) -> list[InputExample]:
    """Load training pairs with correct task routing.

    - Annotation pairs are routed by mode to the correct instruction prefix
    - Graded scores are used as labels (not binary)
    - Graph edges are routed to synergy/completion instructions only
    - Negative pairs (low scores) get label=0.0 with same instruction

    Returns:
        List of InputExample with graded labels and mode-specific instructions.
    """
    examples = []

    # 1. Test set annotations (mode-aware, graded labels)
    if test_set_path and test_set_path.exists():
        logger.info(f"Loading annotations from {test_set_path}...")
        with open(test_set_path) as f:
            test_data = json.load(f)

        queries = test_data.get("queries", {})
        mode_counts = {"substitution": 0, "synergy": 0, "meta": 0, "skipped": 0}

        for query_card, labels in queries.items():
            annotations = labels.get("annotations", [])
            for ann in annotations:
                candidate = ann.get("candidate", "")
                mode = ann.get("mode", "unknown")
                if not candidate or mode not in MODE_SCORE_FIELD:
                    mode_counts["skipped"] += 1
                    continue

                # Get the mode-appropriate score as label
                score_field = MODE_SCORE_FIELD[mode]
                score = float(ann.get(score_field, 0.0) or 0.0)

                # Also use substitutability for substitution pairs
                if mode == "substitution":
                    sub_score = float(ann.get("substitutability", 0.0) or 0.0)
                    score = max(score, sub_score)

                instruction = _get_instruction(MODE_INSTRUCTION[mode])
                query_text = f"{instruction} {query_card}"
                target_text = f"{instruction} {candidate}"

                # Use graded score as label
                examples.append(InputExample(texts=[query_text, target_text], label=score))
                mode_counts[mode] += 1

        logger.info(f"  Annotation pairs by mode: {mode_counts}")

    # 2. Graph edges -> synergy + completion instructions ONLY
    if graph_path and graph_path.exists():
        logger.info(f"Loading graph edges from {graph_path} (synergy/completion only)...")
        try:
            from ml.data.incremental_graph import IncrementalCardGraph
        except ImportError:
            from ..data.incremental_graph import IncrementalCardGraph

        use_sqlite = graph_path.suffix == ".db"
        graph = IncrementalCardGraph(graph_path, use_sqlite=use_sqlite)
        edges = graph.query_edges(min_weight=5)  # Higher threshold for quality
        logger.info(f"  Found {len(edges)} edges (min_weight=5)")

        if edges:
            sample_size = min(max_graph_edges, len(edges))
            sampled = random.sample(edges, sample_size) if len(edges) > sample_size else edges

            # Split between synergy and completion instructions
            syn_instruction = _get_instruction("synergy")
            comp_instruction = _get_instruction("completion")

            for i, edge in enumerate(sampled):
                # Normalize weight to [0, 1] for label
                # High co-occurrence = strong synergy signal
                weight = min(edge.weight / 100.0, 1.0)  # cap at 1.0

                if i % 2 == 0:
                    instr = syn_instruction
                else:
                    instr = comp_instruction

                examples.append(
                    InputExample(
                        texts=[f"{instr} {edge.card1}", f"{instr} {edge.card2}"],
                        label=weight,
                    )
                )

            logger.info(f"  Added {len(sampled)} graph edges (synergy + completion)")

    logger.info(f"Total training examples: {len(examples)}")
    return examples


def load_training_pairs_single_task(
    test_set_path: Path | None = None,
    graph_path: Path | None = None,
    task_type: str = "substitution",
    num_negatives_per_positive: int = 3,
    max_graph_edges: int = 5000,
) -> list[InputExample]:
    """Load mode-filtered pairs for a single task.

    Only uses annotations matching the requested task_type.
    Graph edges are ONLY included for synergy/completion tasks.
    """
    examples = []
    instruction = _get_instruction(task_type)

    if test_set_path and test_set_path.exists():
        logger.info(f"Loading {task_type}-filtered pairs from {test_set_path}...")
        with open(test_set_path) as f:
            test_data = json.load(f)

        queries = test_data.get("queries", {})
        n_pos = 0
        n_neg = 0

        # Map task_type to expected modes
        task_to_modes = {
            "substitution": {"substitution"},
            "synergy": {"synergy"},
            "similar": {"substitution", "synergy", "meta"},
            "completion": {"synergy"},
            "upgrade": {"substitution"},
            "downgrade": {"substitution"},
            "budget": {"substitution"},
        }
        allowed_modes = task_to_modes.get(task_type, {task_type})

        for query_card, labels in queries.items():
            annotations = labels.get("annotations", [])
            query_text = f"{instruction} {query_card}"

            positives_for_query = []
            negatives_for_query = []

            for ann in annotations:
                candidate = ann.get("candidate", "")
                mode = ann.get("mode", "unknown")
                if not candidate:
                    continue

                # Get appropriate score
                if task_type in MODE_SCORE_FIELD:
                    score = float(ann.get(MODE_SCORE_FIELD[task_type], 0.0) or 0.0)
                else:
                    score = float(ann.get("similarity_score", 0.0) or 0.0)

                if task_type == "substitution":
                    sub = float(ann.get("substitutability", 0.0) or 0.0)
                    score = max(score, sub)

                target_text = f"{instruction} {candidate}"

                if mode in allowed_modes and score >= 0.3:
                    examples.append(InputExample(texts=[query_text, target_text], label=score))
                    positives_for_query.append(candidate)
                    n_pos += 1
                elif score < 0.15:
                    negatives_for_query.append(candidate)

            # Add limited negatives
            neg_limit = num_negatives_per_positive * len(positives_for_query)
            for neg_card in negatives_for_query[:neg_limit]:
                neg_text = f"{instruction} {neg_card}"
                examples.append(InputExample(texts=[query_text, neg_text], label=0.0))
                n_neg += 1

        logger.info(f"  {task_type}: {n_pos} positives, {n_neg} negatives (mode-filtered)")

    # Graph edges: ONLY for synergy/completion, NOT substitution
    if task_type in ("substitution", "budget", "upgrade", "downgrade"):
        if graph_path:
            logger.info(
                f"  Skipping graph edges for {task_type} task (co-occurrence != substitution)"
            )
    elif graph_path and graph_path.exists():
        logger.info(f"Loading graph edges for {task_type}...")
        try:
            from ml.data.incremental_graph import IncrementalCardGraph
        except ImportError:
            from ..data.incremental_graph import IncrementalCardGraph

        use_sqlite = graph_path.suffix == ".db"
        graph = IncrementalCardGraph(graph_path, use_sqlite=use_sqlite)
        edges = graph.query_edges(min_weight=5)

        if edges:
            sample_size = min(max_graph_edges, len(edges))
            sampled = random.sample(edges, sample_size) if len(edges) > sample_size else edges
            for edge in sampled:
                weight = min(edge.weight / 100.0, 1.0)
                examples.append(
                    InputExample(
                        texts=[f"{instruction} {edge.card1}", f"{instruction} {edge.card2}"],
                        label=weight,
                    )
                )
            logger.info(f"  Added {len(sampled)} graph edges")

    logger.info(f"Total: {len(examples)} examples for task '{task_type}'")
    return examples


def fine_tune_instruction_embeddings(
    base_model_name: str = "intfloat/e5-base-v2",
    output_path: Path | None = None,
    test_set_path: Path | None = None,
    graph_path: Path | None = None,
    task_type: str = "substitution",
    multi_task: bool = False,
    epochs: int = 3,
    batch_size: int = 16,
    learning_rate: float = 2e-5,
    warmup_steps: int = 100,
) -> SentenceTransformer:
    """Fine-tune instruction-tuned embeddings on card similarity tasks."""
    if not HAS_DEPS:
        raise ImportError("sentence-transformers, torch required")

    logger.info("=" * 70)
    logger.info("FINE-TUNING INSTRUCTION EMBEDDINGS")
    logger.info("=" * 70)
    logger.info(f"Base model: {base_model_name}")
    logger.info(f"Mode: {'multi-task' if multi_task else task_type}")
    logger.info(f"Epochs: {epochs}, Batch size: {batch_size}, LR: {learning_rate}")
    logger.info("")

    # Load base model
    logger.info(f"Loading base model: {base_model_name}...")
    model = SentenceTransformer(base_model_name)
    logger.info("Model loaded")

    # Load training data
    if multi_task:
        examples = load_training_pairs_multitask(
            test_set_path=test_set_path,
            graph_path=graph_path,
        )
    else:
        examples = load_training_pairs_single_task(
            test_set_path=test_set_path,
            graph_path=graph_path,
            task_type=task_type,
        )

    if not examples:
        raise ValueError("No training examples found")

    # Create data loader
    train_dataloader = DataLoader(examples, shuffle=True, batch_size=batch_size)

    # CosineSimilarityLoss works with graded labels in [0, 1]
    train_loss = losses.CosineSimilarityLoss(model)

    # Fine-tune
    logger.info("Starting fine-tuning...")
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=epochs,
        warmup_steps=warmup_steps,
        optimizer_params={"lr": learning_rate},
        output_path=str(output_path) if output_path else None,
        show_progress_bar=True,
    )
    logger.info("Fine-tuning complete")

    # Save model
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        model.save(str(output_path))
        logger.info(f"Saved fine-tuned model to {output_path}")

    return model


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fine-tune instruction-tuned embeddings on card similarity tasks"
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="intfloat/e5-base-v2",
        help="Base model to fine-tune",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output directory")
    parser.add_argument("--test-set", type=Path, help="Annotated test set JSON")
    parser.add_argument("--graph", type=Path, help="Graph DB (synergy/completion only)")
    parser.add_argument(
        "--task-type",
        type=str,
        default="substitution",
        choices=[
            "substitution",
            "completion",
            "budget",
            "format",
            "archetype",
            "similar",
            "synergy",
            "upgrade",
            "downgrade",
        ],
        help="Task type (ignored if --multi-task)",
    )
    parser.add_argument(
        "--multi-task",
        action="store_true",
        help="Train all tasks jointly with mode-aware instruction routing",
    )
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size")
    parser.add_argument("--learning-rate", type=float, default=2e-5, help="Learning rate")
    parser.add_argument("--warmup-steps", type=int, default=100, help="Warmup steps")
    args = parser.parse_args()

    if not HAS_DEPS:
        logger.error("Missing dependencies: sentence-transformers, torch")
        return 1

    # Resolve paths
    test_set_path = resolve_path(args.test_set) if args.test_set else None
    if isinstance(test_set_path, str):
        test_set_path = Path(test_set_path)
    graph_path = resolve_path(args.graph) if args.graph else None
    if isinstance(graph_path, str):
        graph_path = Path(graph_path)

    try:
        fine_tune_instruction_embeddings(
            base_model_name=args.base_model,
            output_path=args.output,
            test_set_path=test_set_path,
            graph_path=graph_path,
            task_type=args.task_type,
            multi_task=args.multi_task,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            warmup_steps=args.warmup_steps,
        )
        logger.info("Fine-tuning complete!")
        return 0
    except Exception as e:
        log_exception(logger, "Fine-tuning failed", e, include_context=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
