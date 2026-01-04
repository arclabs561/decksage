#!/usr/bin/env python3
"""
LLM-as-Judge for Batch Evaluation

Judges similarity predictions at scale without human annotation.
Enables large-scale evaluation of model performance.

Usage:
 python -m src.ml.annotation.llm_judge_batch \
 --test-set experiments/test_set_canonical_magic.json \
 --predictions predictions.json \
 --output judgments.json \
 --top-k 20
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

try:
 from dotenv import load_dotenv

 load_dotenv()
except Exception:
 pass

try:
 from pydantic import BaseModel, Field
 from pydantic_ai import Agent

 HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    print("Install pydantic-ai: pip install pydantic-ai")

from ..utils.paths import PATHS


class SimilarityJudgment(BaseModel):
 """LLM judgment of card similarity (expanded with synergy strength and combo piece identification)."""

 query: str
 candidate: str
 relevance: int = Field(ge=0, le=4, description="0-4 relevance score")
 reasoning: str = Field(description="Why this score?")
 confidence: float = Field(ge=0.0, le=1.0, description="Confidence in judgment")
 similarity_type: str = Field(
 description="substitute|synergy|archetype|unrelated"
 )
 synergy_strength: int | None = Field(
 None, ge=0, le=4,
 description="0-4: If cards appear together, rate synergy strength (0=no synergy, 4=combo piece)"
 )
 combo_piece_identification: int | None = Field(
 None, ge=0, le=4,
 description="0-4: If combo-related, rate how essential this is as a combo piece (0=not combo, 4=essential combo piece)"
 )


class BatchJudgment(BaseModel):
 """Batch of judgments for a query."""

 query: str
 judgments: list[SimilarityJudgment]


def make_judge_agent() -> "Agent[SimilarityJudgment]":
    """Create LLM agent for similarity judgment."""
    if not HAS_PYDANTIC_AI:
        raise ImportError("pydantic-ai required: pip install pydantic-ai")

    from ..utils.pydantic_ai_helpers import make_agent as _make

    # Use frontier models from leaderboard (claude-opus-4-5 is top quality)
    model = os.getenv("ANNOTATOR_MODEL_JUDGE") or os.getenv("ANNOTATOR_MODEL_BEST") or "anthropic/claude-opus-4.5"

    # Use improved prompt (based on meta-evaluation)
    try:
        from ..evaluation.improved_judge_prompts import SIMILARITY_JUDGE_PROMPT
        system = SIMILARITY_JUDGE_PROMPT
    except ImportError:  # Fallback to original if improved prompts not available
        system = (
            "You are an expert TCG judge evaluating card similarity.\n"
            "Given a query card and candidate card, judge similarity on 0-4 scale:\n"
            "4: Extremely similar (near substitutes, same function)\n"
            "3: Very similar (often seen together, similar role)\n"
            "2: Somewhat similar (related function or archetype)\n"
            "1: Marginally similar (loose connection)\n"
            "0: Irrelevant (different function, color, or archetype)\n"
            "Be consistent and provide clear reasoning."
        )
    
    return _make(model, SimilarityJudgment, system)


def judge_predictions(
    test_set: dict[str, Any],
    predictions: dict[str, list[tuple[str, float]]],
    top_k: int = 20,
    max_queries: int | None = None,
    verbose: bool = True,
    retry_on_failure: bool = True,
    max_retries: int = 2,
) -> list[BatchJudgment]:
    """
    Judge similarity predictions using LLM.
    
    Args:
    test_set: Test set with queries
    predictions: Dict mapping query -> list of (card, score) tuples
    top_k: Number of top predictions to judge per query
    max_queries: Limit number of queries (for testing)
    verbose: Print progress
    retry_on_failure: Retry failed judgments
    max_retries: Maximum retry attempts
    
    Returns:
    List of BatchJudgment objects
    """
    if not HAS_PYDANTIC_AI:
        raise ImportError("pydantic-ai required")

    agent = make_judge_agent()
    judgments = []

    queries = list(test_set.get("queries", test_set).keys())
    if max_queries:
        queries = queries[:max_queries]

    for i, query in enumerate(queries, 1):
        if verbose:
            print(f"Judging query {i}/{len(queries)}: {query}")

        query_predictions = predictions.get(query, [])
        if not query_predictions:
            continue

        # Take top k predictions
        top_predictions = query_predictions[:top_k]

        batch_judgments = []
        for candidate, score in top_predictions:
            # Use system prompt from agent, only provide query/candidate in user message
            prompt = (
 f"Query card: {query}\n"
 f"Candidate card: {candidate}\n"
 f"Model predicted similarity score: {score:.3f}\n\n"
 "Evaluate the similarity between these cards using the criteria provided. "
                "Consider functional similarity, substitutability, and distinguish similarity from synergy."
            )
            
            # Retry logic for failed judgments
            judgment = None
            for attempt in range(max_retries + 1):
                try:
                    result = agent.run_sync(prompt)
                    
                    # Validate result structure
                    if not hasattr(result, 'output'):
                        if verbose and attempt == max_retries:
                            print(f" Warning: Invalid result structure for {candidate}: {result}")
                        continue
                    
                    judgment = result.output
                    
                    # Validate judgment object
                    if not isinstance(judgment, SimilarityJudgment):
                        if verbose and attempt == max_retries:
                            print(f" Warning: Invalid judgment type for {candidate}: {type(judgment)}")
                        continue
                    
                    # Ensure required fields are set
                    judgment.query = query
                    judgment.candidate = candidate
                    
                    # Validate relevance score
                    if not (0 <= judgment.relevance <= 4):
                        if verbose and attempt == max_retries:
                            print(f" Warning: Invalid relevance score for {candidate}: {judgment.relevance}")
                        continue
                    
                    # Success - break retry loop
                    break
                    
                except Exception as e:
                    if attempt < max_retries and retry_on_failure:
                        if verbose:
                            print(f" Warning: Attempt {attempt + 1} failed for {candidate}, retrying...")
                        continue
                    else:
                        if verbose:
                            import traceback
                            print(f" Warning: Judgment failed for {candidate} after {attempt + 1} attempts: {e}")
                            if verbose:
                                traceback.print_exc()
                        judgment = None
                        break
            
            if judgment is not None:
                batch_judgments.append(judgment)
            elif verbose:
                print(f" Error: Failed to get judgment for {candidate} after all retries")

        if batch_judgments:
            judgments.append(
                BatchJudgment(query=query, judgments=batch_judgments)
            )

    return judgments


def convert_judgments_to_test_set(
    judgments: list[BatchJudgment],
) -> dict[str, Any]:
    """Convert LLM judgments to test set format."""
    test_set = {
        "version": "llm_judge_v1",
        "description": "LLM-judged similarity predictions",
        "queries": {},
    }

    for batch in judgments:
        labels = {
            "highly_relevant": [],
            "relevant": [],
            "somewhat_relevant": [],
            "marginally_relevant": [],
            "irrelevant": [],
        }

        for judgment in batch.judgments:
            card = judgment.candidate
            relevance = judgment.relevance

            if relevance == 4:
                labels["highly_relevant"].append(card)
            elif relevance == 3:
                labels["relevant"].append(card)
            elif relevance == 2:
                labels["somewhat_relevant"].append(card)
            elif relevance == 1:
                labels["marginally_relevant"].append(card)
            else:
                labels["irrelevant"].append(card)

        test_set["queries"][batch.query] = labels

    test_set["num_queries"] = len(test_set["queries"])
    return test_set


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM-as-Judge for batch evaluation")
    parser.add_argument("--test-set", type=str, required=True, help="Test set JSON file")
    parser.add_argument(
        "--predictions",
        type=str,
        required=True,
        help="Predictions JSON file (query -> list of (card, score))",
    )
    parser.add_argument("--output", type=str, help="Output judgments JSON file")
    parser.add_argument("--top-k", type=int, default=20, help="Top K to judge per query")
    parser.add_argument(
        "--max-queries", type=int, help="Limit number of queries (for testing)"
    )
    parser.add_argument(
        "--format",
        choices=["judgments", "test_set"],
        default="judgments",
        help="Output format",
    )
    parser.add_argument(
        "--verbose", action="store_true", default=True, help="Print progress"
    )
    parser.add_argument(
        "--no-retry", action="store_true", help="Disable retry on failure"
    )
    parser.add_argument(
        "--max-retries", type=int, default=2, help="Maximum retry attempts"
    )

    args = parser.parse_args()

    if not HAS_PYDANTIC_AI:
        print("Error: pydantic-ai not installed")
        return 1
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Error: OPENROUTER_API_KEY not set")
        return 1

    # Load test set
    with open(args.test_set) as f:
        test_set = json.load(f)

    # Load predictions
    with open(args.predictions) as f:
        predictions = json.load(f)

    # Judge predictions
    judgments = judge_predictions(
        test_set, 
        predictions, 
        args.top_k, 
        args.max_queries,
        verbose=args.verbose,
        retry_on_failure=not args.no_retry,
        max_retries=args.max_retries,
    )

    # Output
    output_path = args.output or "judgments.json"
    if args.format == "test_set":
        test_set_output = convert_judgments_to_test_set(judgments)
        with open(output_path, "w") as f:
            json.dump(test_set_output, f, indent=2)
        print(f"\n✓ Converted to test set format: {output_path}")
    else:
        # Output raw judgments
        output_data = {
            "version": "llm_judge_v1",
            "num_queries": len(judgments),
            "judgments": [j.model_dump() for j in judgments],
        }
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\n✓ Saved judgments: {output_path}")

    return 0


if __name__ == "__main__":
 import sys

 sys.exit(main())

