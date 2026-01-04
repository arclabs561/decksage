#!/usr/bin/env python3
"""
Multi-Perspective LLM Judge with Temporal Weighting

Generates diverse annotations from different perspectives:
- Competitive player
- Budget player
- Casual player
- Rules expert
- Meta analyst

Aggregates with temporal decay: recent judgments > old judgments
Outputs structured JSON directly (no text parsing)
"""

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv


load_dotenv()


PERSPECTIVES = {
    "competitive": {
        "persona": "You are a competitive Magic tournament player focused on optimal play and tournament viability.",
        "focus": "power level, format legality, tournament usage",
        "weight": 1.0,
    },
    "budget": {
        "persona": "You are a budget-conscious MTG player looking for affordable alternatives.",
        "focus": "price, accessibility, budget substitutes",
        "weight": 0.8,  # Slightly less weight for general similarity
    },
    "casual": {
        "persona": "You are a casual MTG player who values fun interactions and thematic consistency.",
        "focus": "flavor, fun factor, thematic similarity",
        "weight": 0.6,
    },
    "rules": {
        "persona": "You are an MTG rules expert focused on mechanical similarities.",
        "focus": "rules text, mechanical function, interactions",
        "weight": 1.0,
    },
    "meta": {
        "persona": "You are a metagame analyst tracking tournament trends.",
        "focus": "current meta usage, popularity, deck positioning",
        "weight": 0.9,
    },
}


class MultiPerspectiveJudge:
    """Generate annotations from multiple LLM perspectives"""

    def __init__(self, api_key: str | None = None, model: str = "anthropic/claude-4.5-sonnet"):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    def judge_from_perspective(
        self, query_card: str, candidates: list[str], perspective: str = "competitive"
    ) -> dict:
        """
        Get structured judgment from specific perspective.
        Returns JSON directly, no text parsing.
        """

        perspective_config = PERSPECTIVES[perspective]

        prompt = f"""{perspective_config["persona"]}

Evaluate similarity between query card and candidates.
Focus on: {perspective_config["focus"]}

QUERY CARD: {query_card}

CANDIDATES: {json.dumps(candidates)}

For each candidate, assign:
- relevance: 0-4 (0=irrelevant, 4=substitute)
- confidence: 0.0-1.0 (how certain are you)
- reasoning: brief explanation

Output ONLY valid JSON in this exact format:
{{
  "perspective": "{perspective}",
  "evaluations": [
    {{"card": "Card Name", "relevance": 3, "confidence": 0.8, "reasoning": "brief explanation"}},
    ...
  ]
}}
"""

        try:
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,  # Consistent judgments
                    "response_format": {"type": "json_object"},
                },
                timeout=30,
            )

            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # Parse JSON (already structured)
            judgment = json.loads(content)

            # Add metadata
            judgment["timestamp"] = datetime.now().isoformat()
            judgment["model"] = self.model
            judgment["perspective_weight"] = perspective_config["weight"]

            return judgment

        except Exception as e:
            print(f"  Error in {perspective} perspective: {e}")
            return {
                "perspective": perspective,
                "evaluations": [],
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def judge_multi_perspective(
        self, query_card: str, candidates: list[str], perspectives: list[str] | None = None
    ) -> dict:
        """Get judgments from multiple perspectives"""

        if perspectives is None:
            perspectives = ["competitive", "rules", "meta"]

        print(f"Judging '{query_card}' from {len(perspectives)} perspectives...")

        judgments = []
        for perspective in perspectives:
            print(f"  {perspective}...", end=" ", flush=True)
            judgment = self.judge_from_perspective(query_card, candidates, perspective)
            judgments.append(judgment)
            print("✓")

        return {
            "query_card": query_card,
            "candidates": candidates,
            "judgments": judgments,
            "aggregation_timestamp": datetime.now().isoformat(),
        }

    def aggregate_with_temporal_weight(
        self, all_judgments: list[dict], decay_days: float = 30.0
    ) -> dict:
        """
        Aggregate judgments with temporal decay.

        Recent judgments get more weight: w = exp(-days_old / decay_days)
        """

        now = datetime.now()

        # Group by query and card
        aggregated = defaultdict(lambda: defaultdict(list))

        for judgment_set in all_judgments:
            query = judgment_set["query_card"]

            for judgment in judgment_set["judgments"]:
                timestamp = datetime.fromisoformat(judgment["timestamp"])
                days_old = (now - timestamp).total_seconds() / 86400

                # Temporal weight: exponential decay
                temporal_weight = np.exp(-days_old / decay_days)

                # Perspective weight
                perspective_weight = judgment.get("perspective_weight", 1.0)

                # Combined weight
                total_weight = temporal_weight * perspective_weight

                for eval_item in judgment.get("evaluations", []):
                    card = eval_item["card"]
                    relevance = eval_item["relevance"]
                    confidence = eval_item.get("confidence", 1.0)

                    aggregated[query][card].append(
                        {
                            "relevance": relevance,
                            "weight": total_weight * confidence,
                            "perspective": judgment["perspective"],
                            "timestamp": judgment["timestamp"],
                        }
                    )

        # Compute weighted average for each card
        final_aggregated = {}
        for query, cards in aggregated.items():
            final_aggregated[query] = {}

            for card, judgments in cards.items():
                # Weighted average relevance
                total_weight = sum(j["weight"] for j in judgments)
                if total_weight > 0:
                    avg_relevance = (
                        sum(j["relevance"] * j["weight"] for j in judgments) / total_weight
                    )
                else:
                    avg_relevance = 0

                final_aggregated[query][card] = {
                    "relevance": avg_relevance,
                    "num_judgments": len(judgments),
                    "perspectives": list({j["perspective"] for j in judgments}),
                    "latest_timestamp": max(j["timestamp"] for j in judgments),
                }

        return final_aggregated

    def save_judgment_batch(
        self, judgment_data: dict, output_dir="../../annotations/llm_judgments"
    ):
        """Save judgment batch as JSON (structured, not parsed text)"""

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = output_path / f"judgment_{timestamp}.json"

        # Add provenance
        judgment_data["provenance"] = {
            "generated_by": "multi_perspective_judge.py",
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
            "num_perspectives": len(judgment_data.get("judgments", [])),
        }

        with open(filename, "w") as f:
            json.dump(judgment_data, f, indent=2)

        print(f"💾 Saved judgment batch: {filename}")
        return filename


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Multi-perspective LLM judge")
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--candidates", nargs="+", required=True)
    parser.add_argument(
        "--perspectives",
        nargs="+",
        choices=list(PERSPECTIVES.keys()),
        default=["competitive", "rules"],
    )
    parser.add_argument("--output-dir", type=str, default="../../annotations/llm_judgments")

    args = parser.parse_args()

    judge = MultiPerspectiveJudge()

    # Get multi-perspective judgment
    result = judge.judge_multi_perspective(args.query, args.candidates, args.perspectives)

    # Save
    judge.save_judgment_batch(result, args.output_dir)

    # Display summary
    print(f"\nSummary for '{args.query}':")
    for judgment in result["judgments"]:
        if judgment.get("evaluations"):
            avg_rel = np.mean([e["relevance"] for e in judgment["evaluations"]])
            print(f"  {judgment['perspective']:15s} - Avg relevance: {avg_rel:.2f}")


if __name__ == "__main__":
    import sys

    sys.exit(main())
