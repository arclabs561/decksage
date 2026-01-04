#!/usr/bin/env python3
"""
LLM Bootstrap for Annotation Batch 002

Generates a schema-aligned YAML file with LLM-proposed candidates and draft
relevance/notes for human verification.

Outputs: annotations/batch_002_expansion.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

try:
 from dotenv import load_dotenv # type: ignore

 load_dotenv()
except Exception:
 pass

try:
 from pydantic import BaseModel, Field
 from pydantic_ai import Agent

 HAS_PYDANTIC_AI = True
except Exception:
 HAS_PYDANTIC_AI = False

from .utils.paths import PATHS


class CandidateDraft(BaseModel):
 card: str
 similarity_type: str = Field(description="substitute|synergy|upgrade|downgrade|archetype|unrelated")
 relevance: int = Field(ge=0, le=4, description="0-4 relevance (draft)")
 notes: str = Field(description="Short rationale")


class QueryDraft(BaseModel):
 query: str
 candidates: List[CandidateDraft]


def make_agent() -> "Agent[QueryDraft]":
    if not HAS_PYDANTIC_AI:
        raise ImportError("pydantic-ai required: pip install pydantic-ai")

    from .utils.pydantic_ai_helpers import make_agent as _make

    model = os.getenv("ANNOTATOR_MODEL_BOOTSTRAP", "anthropic/claude-4.5-sonnet")

    system = (
        "You are an expert TCG annotator (Magic-first).\n"
        "Given a query card, propose 12-24 candidate similar cards with a relevance draft (0-4).\n"
        "Balance functional substitutes (priority) and synergies; include 1-2 obvious irrelevants for calibration.\n"
        "Keep notes concise; prefer functional equivalents."
    )

    return _make(model, QueryDraft, system)


def sample_queries_from_test_set(game: str, num: int) -> List[str]:
    path = getattr(PATHS, f"test_{game}")
    with open(path) as f:
        data = json.load(f)
    queries = list((data.get("queries") or data).keys())
    random.shuffle(queries)
    return queries[:num]


def write_batch_yaml(output_path: Path, drafts: List[QueryDraft]) -> None:
    import yaml  # Local import to avoid test dependency when unused

    # Schema-aligned with extra draft fields
    batch = {
        "batch_metadata": {
            "batch_id": "002",
            "created_date": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d"),
            "status": "draft",
            "num_queries": len(drafts),
            "annotators": ["llm_draft"],
            "notes": "LLM-bootstrapped candidates; human verification required",
        },
        "annotations": [],
    }

    for d in drafts:
        items = []
        for c in d.candidates:
            items.append(
                {
                    "card": c.card,
                    "similarity_type": c.similarity_type,
                    "relevance": None,  # Human to fill
                    "llm_relevance_draft": int(c.relevance),
                    "llm_notes": c.notes,
                }
            )

        batch["annotations"].append(
            {
                "query_id": f"q_{d.query.replace(' ', '_')[:24]}",
                "query_card": d.query,
                "annotator": "llm_bootstrap",
                "annotation_date": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d"),
                "candidates": items,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.safe_dump(batch, f, sort_keys=False, default_flow_style=False)

    print(f"\n📝 Wrote LLM-bootstrapped batch: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM bootstrap for annotation batch_002")
    parser.add_argument("--game", choices=["magic", "pokemon", "yugioh"], default="magic")
    parser.add_argument("--num", type=int, default=20, help="Number of queries to bootstrap")
    parser.add_argument(
        "--output",
 type=str,
 default=str(Path(__file__).parent.parent.parent / "annotations" / "batch_002_expansion.yaml"),
 )

    args = parser.parse_args()

    if not HAS_PYDANTIC_AI:
        print("Error: pydantic-ai not installed")
        return 1
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Error: OPENROUTER_API_KEY not set in environment")
        return 1

    agent = make_agent()

    # Pick queries (start from canonical set for quality)
    queries = sample_queries_from_test_set(args.game, args.num)

    drafts: List[QueryDraft] = []
    for q in queries:
        prompt = (
            f"Query card: {q}\n"
            "Return 16 candidates with relevance draft (0-4) and a short note."
        )
        try:
            result = agent.run_sync(prompt)
            drafts.append(result.output)
        except Exception as e:
            print(f" Warning: LLM draft failed for {q}: {e}")
            continue

    if not drafts:
        print("No drafts generated")
        return 1

    write_batch_yaml(Path(args.output), drafts)
    return 0


if __name__ == "__main__":
 import sys

 sys.exit(main())





