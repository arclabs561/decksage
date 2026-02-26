#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pydantic-ai", "pydantic", "python-dotenv"]
# ///
"""
Meta-critique of multi-judge annotation batches.

Analyzes per-judge behavior, identifies systematic biases, and suggests
prompt improvements. Can optionally run an LLM meta-critic to review
the judges' collective performance.

Usage:
  PYTHONPATH=src uv run scripts/annotation/critique_judges.py \
    data/annotations/magic_smart_200.json

  # With LLM meta-critic (uses OpenRouter)
  PYTHONPATH=src uv run scripts/annotation/critique_judges.py \
    data/annotations/magic_smart_200.json --llm-critique
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median, stdev

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def load_batch(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def analyze_judges(data: dict) -> dict:
    """Compute per-judge statistics and identify systematic biases."""
    labels = data.get("labels", [])
    if not labels:
        return {"error": "No labels found"}

    # Collect per-judge data
    judge_scores: dict[str, list[float]] = defaultdict(list)
    judge_types: dict[str, list[str]] = defaultdict(list)
    judge_substitutes: dict[str, list[bool]] = defaultdict(list)
    judge_functional: dict[str, list[float]] = defaultdict(list)
    judge_synergy: dict[str, list[float]] = defaultdict(list)
    judge_reasoning_len: dict[str, list[int]] = defaultdict(list)
    judge_participation: dict[str, int] = defaultdict(int)
    judge_key_sim_count: dict[str, list[int]] = defaultdict(list)
    judge_key_diff_count: dict[str, list[int]] = defaultdict(list)

    # Per-pair disagreement tracking
    pair_score_spreads: list[float] = []
    disagreement_pairs: list[dict] = []
    total_pairs = len(labels)

    for label in labels:
        per_judge = label.get("per_judge", {})
        if not per_judge:
            continue

        scores_this_pair = []
        for judge_name, jdata in per_judge.items():
            judge_participation[judge_name] += 1
            score = jdata.get("similarity_score", 0)
            judge_scores[judge_name].append(score)
            scores_this_pair.append(score)

            if jdata.get("similarity_type"):
                judge_types[judge_name].append(jdata["similarity_type"])
            if jdata.get("is_substitute") is not None:
                judge_substitutes[judge_name].append(jdata["is_substitute"])
            if jdata.get("functional_score") is not None:
                judge_functional[judge_name].append(jdata["functional_score"])
            if jdata.get("synergy_score") is not None:
                judge_synergy[judge_name].append(jdata["synergy_score"])
            if jdata.get("reasoning"):
                judge_reasoning_len[judge_name].append(len(jdata["reasoning"]))
            if jdata.get("key_similarities"):
                judge_key_sim_count[judge_name].append(len(jdata["key_similarities"]))
            if jdata.get("key_differences"):
                judge_key_diff_count[judge_name].append(len(jdata["key_differences"]))

        if len(scores_this_pair) >= 2:
            spread = max(scores_this_pair) - min(scores_this_pair)
            pair_score_spreads.append(spread)
            if spread > 0.3:
                disagreement_pairs.append({
                    "card1": label["card1"],
                    "card2": label["card2"],
                    "scores": {k: v.get("similarity_score") for k, v in per_judge.items()},
                    "spread": spread,
                })

    # Compute per-judge stats
    judge_stats = {}
    for judge_name in sorted(judge_scores.keys()):
        scores = judge_scores[judge_name]
        stats = {
            "participation": f"{judge_participation[judge_name]}/{total_pairs} ({100*judge_participation[judge_name]/total_pairs:.0f}%)",
            "score_mean": round(mean(scores), 3),
            "score_median": round(median(scores), 3),
            "score_std": round(stdev(scores), 3) if len(scores) > 1 else 0,
            "score_min": round(min(scores), 2),
            "score_max": round(max(scores), 2),
        }

        # Score distribution (quintiles)
        bins = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        for s in scores:
            if s < 0.2: bins["0.0-0.2"] += 1
            elif s < 0.4: bins["0.2-0.4"] += 1
            elif s < 0.6: bins["0.4-0.6"] += 1
            elif s < 0.8: bins["0.6-0.8"] += 1
            else: bins["0.8-1.0"] += 1
        stats["score_distribution"] = {k: f"{v} ({100*v/len(scores):.0f}%)" for k, v in bins.items()}

        # Type distribution
        types = judge_types.get(judge_name, [])
        if types:
            type_counts = Counter(types)
            stats["type_distribution"] = {k: f"{v} ({100*v/len(types):.0f}%)" for k, v in type_counts.most_common()}

        # Substitute rate
        subs = judge_substitutes.get(judge_name, [])
        if subs:
            stats["substitute_rate"] = f"{sum(subs)}/{len(subs)} ({100*sum(subs)/len(subs):.0f}%)"

        # Functional and synergy scores
        func = judge_functional.get(judge_name, [])
        if func:
            stats["functional_score_mean"] = round(mean(func), 3)
        syn = judge_synergy.get(judge_name, [])
        if syn:
            stats["synergy_score_mean"] = round(mean(syn), 3)

        # Reasoning quality
        r_lens = judge_reasoning_len.get(judge_name, [])
        if r_lens:
            stats["reasoning_length_mean"] = round(mean(r_lens))
            stats["reasoning_length_min"] = min(r_lens)

        # Structured output completeness
        ks = judge_key_sim_count.get(judge_name, [])
        kd = judge_key_diff_count.get(judge_name, [])
        if ks:
            stats["key_similarities_mean"] = round(mean(ks), 1)
        if kd:
            stats["key_differences_mean"] = round(mean(kd), 1)

        judge_stats[judge_name] = stats

    # Identify biases
    biases = []
    all_means = {j: mean(judge_scores[j]) for j in judge_scores}
    global_mean = mean(s for scores in judge_scores.values() for s in scores)

    for judge_name, judge_mean in all_means.items():
        delta = judge_mean - global_mean
        if abs(delta) > 0.05:
            direction = "higher" if delta > 0 else "lower"
            biases.append(f"{judge_name} scores systematically {direction} than average (delta={delta:+.3f})")

        # Check score range utilization
        scores = judge_scores[judge_name]
        score_range = max(scores) - min(scores)
        if score_range < 0.3:
            biases.append(f"{judge_name} has narrow score range ({score_range:.2f}) -- may be clustering")

        # Check if judge never uses high scores
        if max(scores) < 0.5:
            biases.append(f"{judge_name} never scores above 0.5 -- may be too conservative")

    # Cross-judge disagreement patterns
    disagreement_stats = {}
    if pair_score_spreads:
        disagreement_stats = {
            "mean_spread": round(mean(pair_score_spreads), 3),
            "median_spread": round(median(pair_score_spreads), 3),
            "high_disagreement_pairs": len([s for s in pair_score_spreads if s > 0.3]),
            "high_disagreement_pct": f"{100*len([s for s in pair_score_spreads if s > 0.3])/len(pair_score_spreads):.0f}%",
        }

    # Worst disagreements
    worst_disagreements = sorted(disagreement_pairs, key=lambda x: x["spread"], reverse=True)[:10]

    return {
        "total_pairs": total_pairs,
        "global_score_mean": round(global_mean, 3),
        "judge_stats": judge_stats,
        "biases": biases,
        "disagreement_stats": disagreement_stats,
        "worst_disagreements": worst_disagreements,
    }


def print_report(analysis: dict) -> None:
    """Pretty-print the judge critique report."""
    print(f"\n{'='*70}")
    print(f"JUDGE CRITIQUE REPORT")
    print(f"{'='*70}")
    print(f"Total pairs: {analysis['total_pairs']}")
    print(f"Global score mean: {analysis['global_score_mean']}")

    print(f"\n{'─'*70}")
    print("PER-JUDGE STATISTICS")
    print(f"{'─'*70}")
    for judge, stats in analysis["judge_stats"].items():
        print(f"\n  {judge}:")
        print(f"    Participation: {stats['participation']}")
        print(f"    Score: mean={stats['score_mean']}, median={stats['score_median']}, std={stats['score_std']}, range=[{stats['score_min']}, {stats['score_max']}]")
        if "score_distribution" in stats:
            dist = stats["score_distribution"]
            print(f"    Distribution: {' | '.join(f'{k}: {v}' for k, v in dist.items())}")
        if "type_distribution" in stats:
            print(f"    Types: {stats['type_distribution']}")
        if "substitute_rate" in stats:
            print(f"    Substitute rate: {stats['substitute_rate']}")
        if "functional_score_mean" in stats:
            print(f"    Functional score mean: {stats['functional_score_mean']}")
        if "synergy_score_mean" in stats:
            print(f"    Synergy score mean: {stats['synergy_score_mean']}")
        if "reasoning_length_mean" in stats:
            print(f"    Reasoning: mean={stats['reasoning_length_mean']} chars, min={stats['reasoning_length_min']}")
        if "key_similarities_mean" in stats:
            print(f"    Key similarities: {stats['key_similarities_mean']} avg per pair")
        if "key_differences_mean" in stats:
            print(f"    Key differences: {stats['key_differences_mean']} avg per pair")

    if analysis["biases"]:
        print(f"\n{'─'*70}")
        print("IDENTIFIED BIASES")
        print(f"{'─'*70}")
        for bias in analysis["biases"]:
            print(f"  - {bias}")

    if analysis.get("disagreement_stats"):
        ds = analysis["disagreement_stats"]
        print(f"\n{'─'*70}")
        print("CROSS-JUDGE DISAGREEMENT")
        print(f"{'─'*70}")
        print(f"  Mean score spread: {ds['mean_spread']}")
        print(f"  Median score spread: {ds['median_spread']}")
        print(f"  High disagreement (>0.3 spread): {ds['high_disagreement_pairs']} ({ds['high_disagreement_pct']})")

    if analysis.get("worst_disagreements"):
        print(f"\n{'─'*70}")
        print("WORST DISAGREEMENTS (top 10)")
        print(f"{'─'*70}")
        for d in analysis["worst_disagreements"]:
            scores_str = ", ".join(f"{k}: {v:.2f}" for k, v in d["scores"].items() if v is not None)
            print(f"  {d['card1']} <-> {d['card2']}: spread={d['spread']:.2f} ({scores_str})")

    print(f"\n{'='*70}\n")


def llm_critique(data: dict, analysis: dict) -> str:
    """Use an LLM to meta-critique the judges and suggest prompt improvements."""
    import asyncio
    import os

    from pydantic import BaseModel, Field
    from pydantic_ai import Agent

    class JudgeCritique(BaseModel):
        """LLM meta-critique of multi-judge annotation quality."""
        overall_quality: float = Field(ge=0.0, le=1.0, description="Overall annotation quality (0-1)")
        judge_rankings: list[str] = Field(description="Judges ranked by quality, best first")
        systematic_issues: list[str] = Field(description="Systematic problems observed across judges")
        prompt_improvements: list[str] = Field(description="Concrete prompt changes to improve quality")
        calibration_issues: list[str] = Field(description="Score calibration problems")
        per_judge_feedback: dict[str, str] = Field(description="Specific feedback per judge")

    # Build context
    sample_labels = data.get("labels", [])[:10]
    sample_text = json.dumps(sample_labels, indent=2)[:8000]

    prompt = f"""You are a meta-reviewer evaluating a multi-judge annotation system for TCG card similarity.

ANALYSIS SUMMARY:
{json.dumps(analysis, indent=2)[:4000]}

SAMPLE ANNOTATIONS (first 10):
{sample_text}

Based on this data:
1. Rank the judges by annotation quality (reasoning depth, score accuracy, structured output completeness)
2. Identify systematic issues (score clustering, reasoning quality, missing fields)
3. Suggest concrete prompt improvements to fix the issues you find
4. Identify calibration problems (are judges too generous/conservative? do they agree on the right things?)
5. Give specific per-judge feedback

Be concrete and actionable. Reference specific pairs and scores where possible."""

    provider = os.getenv("LLM_PROVIDER", "openrouter")
    model = os.getenv("META_CRITIC_MODEL", "anthropic/claude-sonnet-4-6")
    agent = Agent(
        f"{provider}:{model}",
        output_type=JudgeCritique,
        system_prompt="You are an expert at evaluating annotation quality and LLM judge performance.",
    )

    async def _run():
        result = await agent.run(prompt)
        return result.output

    critique = asyncio.run(_run())

    lines = [
        f"\n{'='*70}",
        "LLM META-CRITIQUE",
        f"{'='*70}",
        f"Overall quality: {critique.overall_quality}",
        f"\nJudge rankings (best first): {', '.join(critique.judge_rankings)}",
    ]
    if critique.systematic_issues:
        lines.append("\nSystematic issues:")
        for issue in critique.systematic_issues:
            lines.append(f"  - {issue}")
    if critique.calibration_issues:
        lines.append("\nCalibration issues:")
        for issue in critique.calibration_issues:
            lines.append(f"  - {issue}")
    if critique.prompt_improvements:
        lines.append("\nPrompt improvements:")
        for imp in critique.prompt_improvements:
            lines.append(f"  - {imp}")
    if critique.per_judge_feedback:
        lines.append("\nPer-judge feedback:")
        for judge, feedback in critique.per_judge_feedback.items():
            lines.append(f"  {judge}: {feedback}")
    lines.append(f"\n{'='*70}\n")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Meta-critique of multi-judge annotation batches")
    parser.add_argument("input", type=Path, help="Annotation batch JSON file")
    parser.add_argument("--llm-critique", action="store_true", help="Run LLM meta-critic (costs API credits)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON analysis")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        return 1

    data = load_batch(args.input)
    analysis = analyze_judges(data)

    if args.json:
        print(json.dumps(analysis, indent=2))
    else:
        print_report(analysis)

    if args.llm_critique:
        critique_text = llm_critique(data, analysis)
        print(critique_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
