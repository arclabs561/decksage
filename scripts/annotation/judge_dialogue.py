#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic-ai", "pydantic", "python-dotenv", "gensim", "anyio"]
# ///
"""
Interactive judge dialogue for annotation expansion.

Two-phase annotation loop:
1. SUGGEST phase: Show a judge a card + its top-K embedding neighbors.
   The judge returns candidates it thinks are interesting to label -- both from
   the neighbor list (hard negatives, near-misses) and from its own knowledge
   (hidden substitutes, missing synergies). Each suggestion includes a reason
   and an expected similarity bucket.
2. LABEL phase: All suggested candidates (de-duplicated across judges) are
   sent through the standard multi-judge annotation pipeline.

This produces high-value annotations: every pair is either a model output that
needs ground truth (pool-based) or a judge-nominated confusable that the model
is likely missing. Coverage of the recommendation space is much better than
random sampling.

Usage:
    PYTHONPATH=src .venv/bin/python scripts/annotation/judge_dialogue.py \
        --game yugioh \
        --embeddings data/embeddings/yugioh_enriched.wv \
        --output data/annotations/dialogue_yugioh.jsonl \
        --num-queries 30 --top-k 20 --concurrency 8
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

try:
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent, ModelSettings
except ImportError:
    print("Error: pydantic-ai required")
    sys.exit(1)

from gensim.models import KeyedVectors  # noqa: E402

from ml.annotation.multi_annotator_iaa import MultiAnnotatorIAA  # noqa: E402


# ── Suggest phase: structured output ──

class CandidateSuggestion(BaseModel):
    """A single candidate suggested by a judge."""
    card_name: str = Field(description="Exact card name")
    reason: str = Field(description="Why this card is interesting to evaluate against the focus card")
    category: str = Field(description="One of: hard_negative, hidden_substitute, near_miss, model_confirm")
    expected_similarity: float = Field(
        ge=0.0, le=1.0,
        description="Expected true similarity (0.0=unrelated, 1.0=identical role)",
    )
    from_model_output: bool = Field(
        description="True if this card was in the model's top-K, False if judge-nominated",
    )


class SuggestionSet(BaseModel):
    """Set of candidates suggested by a judge for one focus card."""
    candidates: list[CandidateSuggestion] = Field(
        min_length=3, max_length=10,
        description="3-10 candidate cards to label",
    )
    model_assessment: str = Field(
        description="Brief assessment of the model's top-K quality for this card",
    )


SUGGEST_PROMPT = """You are a {game} trading card game expert reviewing an embedding model's
similarity recommendations. Your job is to identify the MOST VALUABLE cards to label
for improving this model.

Given a focus card and the model's top similar cards, suggest 3-10 candidates to annotate.
Mix these categories:

1. **model_confirm** (from model output): Cards in the top-K that genuinely look correct.
   Pick 2-3 that span different similarity levels (one very similar, one borderline).
   Expected similarity: match your honest assessment.

2. **hard_negative** (from model output): Cards in the top-K that the model ranks highly
   but are NOT actually good substitutes/synergies. The model is WRONG about these.
   Expected similarity: 0.05-0.25

3. **hidden_substitute** (your own knowledge): Cards NOT in the model's output that
   SHOULD be highly ranked. Name specific {game} cards the model is missing.
   Expected similarity: 0.60-0.90

4. **near_miss** (either source): Cards that are almost interchangeable except for one
   key strategic difference. Expected similarity: 0.35-0.60

IMPORTANT:
- Use exact card names as they appear in the game
- Every suggestion must include a concrete reason
- For hidden_substitute, name real cards -- don't describe hypothetical ones
- Prioritize DIVERSE suggestions: different archetypes, roles, eras
- Your model_assessment should note patterns: is the model biased toward archetype?
  Does it miss cross-archetype synergies? Does it confuse similar names?
"""


async def suggest_candidates(
    focus_card: str,
    similar_cards: list[tuple[str, float]],
    game: str,
    suggest_agents: list[tuple[str, Agent]],
    sem: asyncio.Semaphore,
) -> list[dict]:
    """Run suggest phase: multiple judges suggest candidates for one focus card."""
    similar_str = "\n".join(
        f"  {i+1}. {name} (model score: {score:.3f})"
        for i, (name, score) in enumerate(similar_cards)
    )
    prompt = f"""Focus card: {focus_card}

Model's top similar cards:
{similar_str}

Suggest 3-10 candidates to annotate against {focus_card}. Include a mix of
model confirmations, hard negatives, hidden substitutes, and near-misses."""

    all_suggestions = []

    async def run_one_judge(judge_name: str, agent: Agent):
        async with sem:
            try:
                result = await agent.run(prompt)
                output = result.output
                for cand in output.candidates:
                    all_suggestions.append({
                        "card_name": cand.card_name,
                        "reason": cand.reason,
                        "category": cand.category,
                        "expected_similarity": cand.expected_similarity,
                        "from_model_output": cand.from_model_output,
                        "suggested_by": judge_name,
                        "model_assessment": output.model_assessment,
                    })
            except Exception as e:
                print(f"    Suggest error ({judge_name} for {focus_card}): {e}")

    await asyncio.gather(*(run_one_judge(name, agent) for name, agent in suggest_agents))
    return all_suggestions


def deduplicate_suggestions(
    suggestions: list[dict],
    focus_card: str,
    vocab_set: set[str],
) -> list[dict]:
    """Deduplicate suggestions, preferring those from model output (verifiable names)."""
    seen: dict[str, dict] = {}
    for s in suggestions:
        name = s["card_name"]
        if name == focus_card:
            continue
        if name in seen:
            # Keep the one with more extreme expected_similarity (more informative)
            existing = seen[name]
            if abs(s["expected_similarity"] - 0.5) > abs(existing["expected_similarity"] - 0.5):
                seen[name] = s
        else:
            seen[name] = s

    # Split into verifiable (in vocab) and unverifiable (judge-nominated, may not exist)
    verified = []
    unverified = []
    for name, s in seen.items():
        if name in vocab_set:
            verified.append(s)
        else:
            unverified.append(s)

    # Prioritize verified names, cap unverified to avoid waste
    result = verified + unverified[:5]
    return result


def serialize_result(result, query: str, card: str, game: str, suggestion: dict | None = None) -> dict:
    """Convert MultiAnnotatorResult to serializable dict."""
    entry = {
        "card1": result.card1,
        "card2": result.card2,
        "query_card": query,
        "game": game,
        "timestamp": datetime.now().isoformat(),
        "agreement_level": result.agreement_level,
        "iaa_metrics": result.iaa_metrics,
        "consensus": {
            "similarity_score": result.consensus_annotation.similarity_score,
            "similarity_type": result.consensus_annotation.similarity_type,
            "is_substitute": result.consensus_annotation.is_substitute,
            "reasoning": result.consensus_annotation.reasoning,
        } if result.consensus_annotation else None,
        "per_judge": {
            name: {
                "similarity_score": ann.similarity_score,
                "similarity_type": ann.similarity_type,
                "is_substitute": ann.is_substitute,
                "reasoning": ann.reasoning,
            }
            for name, ann in result.annotations.items()
        },
    }
    if result.usage_by_judge:
        entry["usage"] = result.usage_by_judge
    if suggestion:
        entry["suggestion_metadata"] = {
            "category": suggestion.get("category"),
            "expected_similarity": suggestion.get("expected_similarity"),
            "suggested_by": suggestion.get("suggested_by"),
            "reason": suggestion.get("reason"),
            "from_model_output": suggestion.get("from_model_output"),
        }
    return entry


async def run_dialogue(args):
    """Two-phase annotation dialogue: suggest then label."""
    # Load embeddings
    print(f"Loading embeddings from {args.embeddings}...")
    wv = KeyedVectors.load(str(args.embeddings))
    vocab = list(wv.key_to_index.keys())
    vocab_set = set(vocab)
    print(f"  {len(vocab)} cards")

    # Select focus cards
    rng = random.Random(args.seed)
    focus_cards = rng.sample(vocab, min(args.num_queries, len(vocab)))
    print(f"  Selected {len(focus_cards)} focus cards")

    # Load game knowledge
    game_knowledge_path = Path(f"data/game_knowledge/{args.game}.json")
    game_knowledge = None
    if game_knowledge_path.exists():
        with open(game_knowledge_path) as f:
            game_knowledge = json.load(f)

    # Initialize suggest agents (2 diverse models for suggestion diversity)
    provider = os.getenv("LLM_PROVIDER", "openrouter")
    suggest_models = [
        ("claude_sonnet", f"{provider}:anthropic/claude-sonnet-4-6"),
        ("gemini_flash", f"{provider}:google/gemini-2.5-flash"),
    ]
    suggest_agents = []
    for name, model_id in suggest_models:
        agent = Agent(
            model_id,
            output_type=SuggestionSet,
            instructions=SUGGEST_PROMPT.format(game=args.game),
            model_settings=ModelSettings(temperature=0.5, max_tokens=3000),
        )
        suggest_agents.append((name, agent))
    print(f"  Suggest agents: {[n for n, _ in suggest_agents]}")

    # Initialize label annotator
    annotator = MultiAnnotatorIAA(game=args.game, game_knowledge=game_knowledge)
    judges = [c.name for c in annotator.annotator_configs]
    print(f"  Label judges: {judges}")

    # Checkpoint setup
    checkpoint_path = args.output.with_suffix(".checkpoint.jsonl")
    completed_pairs: set[tuple[str, str]] = set()
    if args.resume and checkpoint_path.exists():
        with open(checkpoint_path) as f:
            for line in f:
                d = json.loads(line)
                completed_pairs.add((d["card1"], d["card2"]))
        print(f"  Resumed: {len(completed_pairs)} pairs already completed")

    # Phase tracking
    args.output.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    total_suggestions = 0
    total_labeled = 0
    suggest_sem = asyncio.Semaphore(args.concurrency)
    label_sem = asyncio.Semaphore(args.concurrency)

    for batch_start in range(0, len(focus_cards), args.batch_size):
        batch = focus_cards[batch_start:batch_start + args.batch_size]
        batch_idx = batch_start // args.batch_size + 1
        total_batches = (len(focus_cards) + args.batch_size - 1) // args.batch_size
        print(f"\n--- Batch {batch_idx}/{total_batches} ({len(batch)} focus cards) ---")

        # Phase 1: SUGGEST
        print("  Phase 1: Suggesting candidates...")
        all_pairs_to_label: list[tuple[str, str, dict]] = []  # (focus, candidate, suggestion)

        suggest_tasks = []
        for card in batch:
            try:
                similar = wv.most_similar(card, topn=args.top_k)
            except KeyError:
                continue
            suggest_tasks.append((card, similar))

        suggest_results = await asyncio.gather(*(
            suggest_candidates(card, similar, args.game, suggest_agents, suggest_sem)
            for card, similar in suggest_tasks
        ))

        for (card, _similar), suggestions in zip(suggest_tasks, suggest_results):
            deduped = deduplicate_suggestions(suggestions, card, vocab_set)
            total_suggestions += len(deduped)
            for s in deduped:
                pair = (card, s["card_name"])
                if pair not in completed_pairs and (pair[1], pair[0]) not in completed_pairs:
                    all_pairs_to_label.append((card, s["card_name"], s))

        print(f"  Phase 1 done: {total_suggestions} suggestions, {len(all_pairs_to_label)} new pairs to label")

        # Phase 2: LABEL
        if not all_pairs_to_label:
            print("  Phase 2: No new pairs to label")
            continue

        print(f"  Phase 2: Labeling {len(all_pairs_to_label)} pairs...")
        batch_completed = 0

        async def label_one(focus: str, candidate: str, suggestion: dict):
            nonlocal batch_completed, total_labeled
            async with label_sem:
                try:
                    result = await annotator.annotate_pair_multi(focus, candidate)
                    entry = serialize_result(result, focus, candidate, args.game, suggestion)

                    with open(checkpoint_path, "a") as f:
                        f.write(json.dumps(entry) + "\n")

                    completed_pairs.add((focus, candidate))
                    batch_completed += 1
                    total_labeled += 1

                    if batch_completed % 5 == 0 or batch_completed == len(all_pairs_to_label):
                        elapsed = time.time() - t0
                        print(f"    [{total_labeled} total] batch {batch_completed}/{len(all_pairs_to_label)} "
                              f"| {elapsed:.0f}s elapsed")

                except Exception as e:
                    print(f"    Label error: {focus} <-> {candidate}: {e}")

        await asyncio.gather(*(label_one(f, c, s) for f, c, s in all_pairs_to_label))

    # Finalize
    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"Dialogue complete: {total_labeled} pairs labeled from {total_suggestions} suggestions")
    print(f"Elapsed: {elapsed:.0f}s ({elapsed/max(total_labeled,1):.1f}s/pair)")

    # Build output (same format as annotate_model_output.py)
    if not checkpoint_path.exists():
        print("No results to finalize.")
        return

    labels = []
    with open(checkpoint_path) as f:
        for line in f:
            labels.append(json.loads(line))

    from collections import defaultdict
    queries: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    category_counts = defaultdict(int)

    for label in labels:
        query = label.get("query_card", label["card1"])
        consensus = label.get("consensus")
        if not consensus:
            continue
        score = consensus["similarity_score"]

        if score >= 0.65:
            grade = "highly_relevant"
        elif score >= 0.45:
            grade = "relevant"
        elif score >= 0.30:
            grade = "somewhat_relevant"
        elif score >= 0.15:
            grade = "marginally_relevant"
        else:
            grade = "irrelevant"

        other = label["card2"] if label["card1"] == query else label["card1"]
        queries[query][grade].append(other)

        meta = label.get("suggestion_metadata", {})
        category_counts[meta.get("category", "unknown")] += 1

    test_set = {
        "version": "dialogue_annotated_v1",
        "game": args.game,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "num_queries": len(queries),
        "num_pairs": len(labels),
        "model_source": str(args.embeddings),
        "top_k": args.top_k,
        "method": "judge_dialogue",
        "category_distribution": dict(category_counts),
        "queries": {q: dict(grades) for q, grades in queries.items()},
    }

    with open(args.output, "w") as f:
        json.dump(test_set, f, indent=2)

    # Summary
    grade_counts = defaultdict(int)
    for q_grades in queries.values():
        for grade, cards in q_grades.items():
            grade_counts[grade] += len(cards)

    print(f"\nTest set written to {args.output}")
    print(f"  {len(queries)} queries, {len(labels)} annotated pairs")
    print(f"  Grade distribution:")
    for grade in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant", "irrelevant"]:
        print(f"    {grade}: {grade_counts[grade]}")
    print(f"  Suggestion category distribution:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Interactive judge dialogue: suggest candidates then label them",
    )
    parser.add_argument("--game", required=True, choices=["magic", "pokemon", "yugioh"])
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--num-queries", type=int, default=30,
                        help="Number of focus cards to process (default: 30)")
    parser.add_argument("--top-k", type=int, default=20,
                        help="Number of model neighbors to show judges (default: 20)")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="Focus cards per suggest-then-label batch (default: 5)")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if not args.embeddings.exists():
        print(f"Error: embeddings not found: {args.embeddings}")
        return 1

    asyncio.run(run_dialogue(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
