#!/usr/bin/env python3
"""
Meta-Judge for Annotation Quality Control

Acts as a "keel" for the annotation system by:
1. Evaluating annotation quality and consistency
2. Identifying issues (score clustering, missing reasoning, etc.)
3. Providing feedback that can be injected back into the annotation process
4. Tracking quality trends over time

This meta-judge reviews batches of annotations and provides context-aware feedback
that can improve future annotation generation.
"""

from __future__ import annotations

import json
import os
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
    BaseModel = None
    Field = None

from ..utils.pydantic_ai_helpers import make_agent


class AnnotationQualityMetrics(BaseModel):
    """Quantitative metrics for annotation quality."""

    score_diversity: float = Field(
        ge=0.0,
        le=1.0,
        description="How well scores are distributed (1.0 = perfect diversity, 0.0 = all same)",
    )
    score_range_utilization: float = Field(
        ge=0.0,
        le=1.0,
        description="How much of the 0.0-1.0 range is used (1.0 = full range, 0.0 = single value)",
    )
    reasoning_quality: float = Field(
        ge=0.0,
        le=1.0,
        description="Average quality of reasoning (based on length, specificity, detail)",
    )
    consistency_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Internal consistency of annotations (similar pairs get similar scores)",
    )
    completeness: float = Field(
        ge=0.0,
        le=1.0,
        description="Percentage of annotations with all required fields",
    )


class AnnotationIssue(BaseModel):
    """Identified issue in annotation batch."""

    issue_type: str = Field(
        description="Type of issue: score_clustering, missing_reasoning, inconsistent_scoring, low_diversity, etc."
    )
    severity: int = Field(
        ge=0, le=4, description="Severity: 0=minor, 1=noticeable, 2=moderate, 3=serious, 4=critical"
    )
    description: str = Field(description="Human-readable description of the issue")
    affected_count: int = Field(description="Number of annotations affected")
    examples: list[str] = Field(
        default_factory=list, description="Example annotation IDs or card pairs"
    )
    suggested_fix: str | None = Field(None, description="Suggested fix or improvement")


class MetaJudgment(BaseModel):
    """Meta-judge evaluation of annotation batch."""

    overall_quality: float = Field(ge=0.0, le=1.0, description="Overall quality score (0.0-1.0)")
    metrics: AnnotationQualityMetrics
    issues: list[AnnotationIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list, description="What's working well")
    feedback: str = Field(description="Detailed feedback for improving annotation generation")
    context_injections: dict[str, Any] = Field(
        default_factory=dict,
        description="Context to inject back into annotation process (prompt improvements, examples, etc.)",
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Actionable recommendations"
    )


META_JUDGE_PROMPT = """You are a meta-judge evaluating the quality of card similarity annotations.

Your role is to act as a "keel" - providing stability and guidance to the annotation system by:
1. Identifying quality issues (score clustering, missing reasoning, inconsistencies)
2. Providing actionable feedback
3. Suggesting context that can be injected back to improve future annotations

**Evaluation Criteria:**

1. **Score Diversity** (Critical):
   - Are scores using the full 0.0-1.0 range?
   - Is there clustering around 0.5 or other values?
   - Are similar pairs getting appropriately similar scores?

2. **Reasoning Quality**:
   - Is reasoning detailed and specific?
   - Does it reference concrete card attributes?
   - Does it explain WHY the score was chosen (not just what it is)?

3. **Consistency**:
   - Are functionally similar pairs getting similar scores?
   - Is the scoring logic consistent across the batch?

4. **Completeness**:
   - Do all annotations have required fields?
   - Are graph features and card comparisons present?

5. **Context Awareness**:
   - Are annotations considering game-specific context?
   - Are graph features being used appropriately?

**Output Format:**
- Provide overall quality score (0.0-1.0)
- List specific issues with severity and examples
- Identify strengths (what's working)
- Provide detailed feedback
- Suggest context injections (prompt improvements, examples, etc.)
- Give actionable recommendations

**Context Injection Examples:**
- "Add example showing high similarity (0.9+) to prompt"
- "Emphasize score diversity in prompt - current batch clusters at 0.5"
- "Include graph Jaccard threshold guidance: Jaccard > 0.3 should correlate with similarity > 0.6"

Be specific, actionable, and focused on improving the annotation system."""


def make_meta_judge_agent() -> Agent[MetaJudgment]:
    """Create meta-judge agent for evaluating annotation quality."""
    if not HAS_PYDANTIC_AI:
        raise ImportError("pydantic-ai required: pip install pydantic-ai")

    # Use Claude 3.5 Sonnet for meta-judging (better for sustained reasoning and analysis)
    # Fallback to Gemini 3 Flash if Claude not available
    model = (
        os.getenv("META_JUDGE_MODEL")
        or os.getenv("ANNOTATOR_MODEL_VALIDATOR")
        or "anthropic/claude-3.5-sonnet"  # Claude 3.5 Sonnet (reliable model ID for OpenRouter)
    )

    # Use openrouter provider for model
    provider = os.getenv("LLM_PROVIDER", "openrouter")
    agent = make_agent(
        model,
        MetaJudgment,
        META_JUDGE_PROMPT,
        provider=provider,
    )
    # Note: temperature and max_tokens would need to be set via ModelSettings
    # if pydantic-ai supports it, but make_agent doesn't accept these directly
    return agent


def compute_quality_metrics(annotations: list[dict[str, Any]]) -> AnnotationQualityMetrics:
    """Compute quantitative quality metrics from annotations."""
    if not annotations:
        return AnnotationQualityMetrics(
            score_diversity=0.0,
            score_range_utilization=0.0,
            reasoning_quality=0.0,
            consistency_score=0.0,
            completeness=0.0,
        )

    # Extract scores
    scores = [
        float(ann.get("similarity_score", 0.5))
        for ann in annotations
        if ann.get("similarity_score") is not None
    ]

    # Score diversity: measure of how well distributed scores are
    if len(scores) > 1:
        # Use standard deviation normalized by range
        score_std = (sum((s - sum(scores) / len(scores)) ** 2 for s in scores) / len(scores)) ** 0.5
        score_diversity = min(1.0, score_std * 2.0)  # Normalize (std of 0.5 = perfect diversity)
    else:
        score_diversity = 0.0

    # Score range utilization: how much of 0.0-1.0 is used
    if scores:
        score_range = max(scores) - min(scores)
        score_range_utilization = score_range  # Direct: 1.0 = full range used
    else:
        score_range_utilization = 0.0

    # Reasoning quality: based on length and presence of key terms
    reasoning_scores = []
    for ann in annotations:
        reasoning = ann.get("reasoning", "")
        if not reasoning:
            reasoning_scores.append(0.0)
            continue

        # Score based on length and specificity
        length_score = min(1.0, len(reasoning) / 500.0)  # 500 chars = full score

        # Check for specificity indicators
        specificity_indicators = [
            "function",
            "power",
            "mana",
            "archetype",
            "format",
            "context",
            "because",
            "why",
        ]
        specificity_score = sum(
            1 for term in specificity_indicators if term.lower() in reasoning.lower()
        ) / len(specificity_indicators)

        reasoning_scores.append((length_score + specificity_score) / 2.0)

    reasoning_quality = sum(reasoning_scores) / len(reasoning_scores) if reasoning_scores else 0.0

    # Consistency: check if similar pairs get similar scores
    # (Simplified: check if scores are reasonably distributed)
    consistency_score = score_diversity  # Use diversity as proxy for consistency

    # Completeness: check required fields
    required_fields = ["card1", "card2", "similarity_score", "reasoning", "source", "game"]
    complete_count = sum(
        1
        for ann in annotations
        if all(field in ann and ann[field] is not None for field in required_fields)
    )
    completeness = complete_count / len(annotations) if annotations else 0.0

    return AnnotationQualityMetrics(
        score_diversity=score_diversity,
        score_range_utilization=score_range_utilization,
        reasoning_quality=reasoning_quality,
        consistency_score=consistency_score,
        completeness=completeness,
    )


def _get_stratified_samples(annotations: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    """Get stratified sample of annotations (high, medium, low scores)."""
    if len(annotations) <= n:
        return annotations

    # Sort by score
    sorted_anns = sorted(annotations, key=lambda a: a.get("similarity_score", 0.5))

    # Sample from different regions
    samples = []
    if n >= 3:
        # High score
        samples.append(sorted_anns[-1])
        # Low score
        samples.append(sorted_anns[0])
        # Medium scores
        mid_start = len(sorted_anns) // 3
        mid_end = 2 * len(sorted_anns) // 3
        for i in range(mid_start, mid_end, max(1, (mid_end - mid_start) // (n - 2))):
            if len(samples) < n:
                samples.append(sorted_anns[i])
    else:
        # Just take evenly spaced
        for i in range(0, len(sorted_anns), len(sorted_anns) // n):
            if len(samples) < n:
                samples.append(sorted_anns[i])

    return samples[:n]


async def meta_judge_annotations(
    annotations: list[dict[str, Any]],
    game: str | None = None,
    batch_id: str | None = None,
) -> MetaJudgment:
    """
    Meta-judge a batch of annotations.

    Args:
        annotations: List of annotation dicts
        game: Game name for context
        batch_id: Optional batch identifier

    Returns:
        MetaJudgment with quality evaluation and feedback
    """
    if not HAS_PYDANTIC_AI:
        raise ImportError("pydantic-ai required")

    # Compute quantitative metrics
    metrics = compute_quality_metrics(annotations)

    # Quantitative validation: Check card attributes presence
    has_card_comparison = sum(1 for a in annotations if a.get("card_comparison"))
    card_comparison_coverage = has_card_comparison / len(annotations) if annotations else 0.0

    # Check if card_comparison has actual data (not just empty dict)
    has_meaningful_card_data = sum(
        1
        for a in annotations
        if a.get("card_comparison")
        and a.get("card_comparison", {}).get("card1_attrs")
        and a.get("card_comparison", {}).get("card2_attrs")
    )
    meaningful_data_coverage = has_meaningful_card_data / len(annotations) if annotations else 0.0

    # Prepare context for LLM meta-judge
    context = {
        "num_annotations": len(annotations),
        "game": game or "unknown",
        "batch_id": batch_id,
        "metrics": metrics.model_dump(),
        "score_distribution": {
            "min": min((a.get("similarity_score", 0.5) for a in annotations), default=0.5),
            "max": max((a.get("similarity_score", 0.5) for a in annotations), default=0.5),
            "mean": sum(a.get("similarity_score", 0.5) for a in annotations) / len(annotations)
            if annotations
            else 0.5,
        },
        "card_attributes_coverage": {
            "has_card_comparison": has_card_comparison,
            "coverage": card_comparison_coverage,
            "meaningful_data": has_meaningful_card_data,
            "meaningful_coverage": meaningful_data_coverage,
        },
        # Use stratified sampling: include high, medium, low scores
        "sample_annotations": _get_stratified_samples(annotations, n=5),
    }

    # Build prompt for meta-judge with game-specific guidance
    game_guidance = ""
    if game:
        game_lower = game.lower()
        if game_lower in ["magic", "mtg"]:
            game_guidance = """
**GAME-SPECIFIC EVALUATION FOR MAGIC:**
- Magic cards often cluster in low scores (0.0-0.2) when pairs are genuinely dissimilar
- However, functionally similar cards (both removal, both draw) should score >= 0.4 even with weak graph evidence
- Pay special attention to: same function + similar attributes → should be 0.5-0.7, not 0.1-0.2
- Examples of correct high scores: Lightning Bolt vs Shock (0.7), Path vs Swords (0.8)
"""
        elif game_lower in ["pokemon", "pkm"]:
            game_guidance = """
**GAME-SPECIFIC EVALUATION FOR POKEMON:**
- Pokemon cards should use type and evolution line for scoring
- Same type (Fire, Water, etc.) → should score >= 0.4
- Same evolution line → should score >= 0.5-0.7
- Pay attention to: type similarity, evolution relationships, function similarity
"""
        elif game_lower in ["yugioh", "ygo"]:
            game_guidance = """
**GAME-SPECIFIC EVALUATION FOR YU-GI-OH:**
- Yu-Gi-Oh cards should use archetype and type for scoring
- Same archetype → should score >= 0.5-0.7
- Same type (Dragon, Warrior, etc.) → should score >= 0.4-0.6
- Pay attention to: archetype relationships, type similarity, function similarity
"""

    # Build prompt for meta-judge
    prompt = f"""Evaluate this batch of {len(annotations)} card similarity annotations for {game or "unknown game"}.
{game_guidance}
**Quantitative Metrics:**
- Score diversity: {metrics.score_diversity:.2f}
- Score range utilization: {metrics.score_range_utilization:.2f}
- Reasoning quality: {metrics.reasoning_quality:.2f}
- Consistency: {metrics.consistency_score:.2f}
- Completeness: {metrics.completeness:.2f}

**Score Distribution:**
- Range: {context["score_distribution"]["min"]:.2f} - {context["score_distribution"]["max"]:.2f}
- Mean: {context["score_distribution"]["mean"]:.2f}

**Card Attributes Coverage (QUANTITATIVE):**
- Annotations with card_comparison field: {context["card_attributes_coverage"]["has_card_comparison"]}/{len(annotations)} ({context["card_attributes_coverage"]["coverage"]:.1%})
- Annotations with meaningful card data: {context["card_attributes_coverage"]["meaningful_data"]}/{len(annotations)} ({context["card_attributes_coverage"]["meaningful_coverage"]:.1%})
- **NOTE**: card_comparison field contains card1_attrs and card2_attrs with actual card data. Check this field, not a separate "card_attributes" field.

**Sample Annotations (stratified by score):**
{json.dumps(context["sample_annotations"], indent=2, ensure_ascii=False)}

**Important Notes:**
- Check if annotations have 'card_comparison' field - this contains card attributes
- card_comparison.card1_attrs and card_comparison.card2_attrs contain the actual card data
- If card_comparison exists but has empty/minimal data, that's a problem
- If card_comparison is missing entirely, that's also a problem

**Your Task:**
1. Evaluate overall quality (0.0-1.0)
2. Identify specific issues with severity and examples
3. Note strengths
4. Provide detailed feedback
5. Suggest context injections (prompt improvements, examples, thresholds)
6. Give actionable recommendations

Focus on actionable feedback that can improve future annotation generation."""

    # Run meta-judge
    agent = make_meta_judge_agent()
    result = await agent.run(prompt)
    judgment = result.output

    # Ensure metrics are included
    judgment.metrics = metrics

    return judgment


def inject_context_into_annotator(
    judgment: MetaJudgment,
    annotator: Any,  # LLMAnnotator
) -> None:
    """
    Inject meta-judge feedback back into the annotation system.

    This acts as the "keel" - providing stability by updating prompts,
    thresholds, or other context based on quality feedback.

    **Game-Specific Context Injection**: Feedback is stored per-game to avoid
    cross-contamination (e.g., Magic-specific advice shouldn't affect Pokemon).

    Args:
        judgment: Meta-judgment with feedback
        annotator: LLMAnnotator instance to update
    """
    # Store judgment for potential future use
    if not hasattr(annotator, "meta_judgments"):
        annotator.meta_judgments = []
    annotator.meta_judgments.append(judgment)

    # Get game from annotator (for game-specific feedback storage)
    game = getattr(annotator, "game", None)
    game_key = (game or "unknown").lower()

    # Extract actionable feedback from issues and recommendations
    # Store as structured data, organized by game (not unioned)
    if not hasattr(annotator, "meta_judge_feedback_by_game"):
        annotator.meta_judge_feedback_by_game = {}

    # Initialize game-specific feedback structure
    if game_key not in annotator.meta_judge_feedback_by_game:
        annotator.meta_judge_feedback_by_game[game_key] = {
            "critical": [],  # High-priority feedback (goes at top of prompt)
            "important": [],  # Medium-priority feedback
            "suggestions": [],  # Lower-priority suggestions
        }

    # Get game-specific feedback structure
    game_feedback = annotator.meta_judge_feedback_by_game[game_key]

    # Backward compatibility: also maintain global feedback (for non-game-specific use)
    if not hasattr(annotator, "meta_judge_feedback"):
        annotator.meta_judge_feedback = {
            "critical": [],
            "important": [],
            "suggestions": [],
        }

    # Process issues for context injection - prioritize by severity
    # Store in game-specific feedback (not unioned across games)
    for issue in judgment.issues:
        if issue.suggested_fix:
            feedback_item = {
                "type": issue.issue_type,
                "fix": issue.suggested_fix,
                "severity": getattr(issue, "severity", 3),
                "game": game_key,  # Tag with game for filtering
            }
            # Categorize by severity (4-5 = critical, 3 = important, 1-2 = suggestions)
            severity = getattr(issue, "severity", 3)
            if isinstance(severity, int):
                if severity >= 4:
                    game_feedback["critical"].append(feedback_item)
                    # Also add to global for backward compatibility
                    annotator.meta_judge_feedback["critical"].append(feedback_item)
                elif severity >= 3:
                    game_feedback["important"].append(feedback_item)
                    annotator.meta_judge_feedback["important"].append(feedback_item)
                else:
                    game_feedback["suggestions"].append(feedback_item)
                    annotator.meta_judge_feedback["suggestions"].append(feedback_item)
            else:
                game_feedback["important"].append(feedback_item)
                annotator.meta_judge_feedback["important"].append(feedback_item)

    # Process recommendations - store game-specifically
    for rec in judgment.recommendations:
        rec_item = {"type": "recommendation", "fix": rec, "game": game_key}
        game_feedback["suggestions"].append(rec_item)
        annotator.meta_judge_feedback["suggestions"].append(rec_item)

    # Also maintain backward-compatible text list for prompt injection
    if not hasattr(annotator, "meta_judge_prompt_additions"):
        annotator.meta_judge_prompt_additions = []

    # Add critical feedback to prompt additions (will be injected at top)
    # Use game-specific feedback if available, fall back to global
    feedback_to_use = (
        game_feedback
        if game_key in annotator.meta_judge_feedback_by_game
        else annotator.meta_judge_feedback
    )

    for item in feedback_to_use["critical"][-3:]:  # Last 3 critical items
        if isinstance(item, dict):
            annotator.meta_judge_prompt_additions.append(
                f"CRITICAL: {item.get('type', 'issue')} - {item.get('fix', '')}"
            )
        else:
            annotator.meta_judge_prompt_additions.append(f"CRITICAL: {item}")

    # Add important feedback
    for item in feedback_to_use["important"][-2:]:  # Last 2 important items
        if isinstance(item, dict):
            annotator.meta_judge_prompt_additions.append(
                f"IMPORTANT: {item.get('type', 'issue')} - {item.get('fix', '')}"
            )
        else:
            annotator.meta_judge_prompt_additions.append(f"IMPORTANT: {item}")

    # Inject context from judgment (dynamic prompt updates)
    if judgment.context_injections:
        # Inject prompt improvements
        if "prompt_additions" in judgment.context_injections:
            additions = judgment.context_injections["prompt_additions"]
            if isinstance(additions, str):
                additions = [additions]
            print(f"  Meta-judge context injection: {len(additions)} prompt additions")
            # Store for dynamic prompt updates
            if not hasattr(annotator, "meta_judge_prompt_additions"):
                annotator.meta_judge_prompt_additions = []
            annotator.meta_judge_prompt_additions.extend(additions)

        # Inject example updates
        if "examples" in judgment.context_injections:
            examples = judgment.context_injections["examples"]
            if isinstance(examples, list):
                print(f"  Meta-judge context injection: {len(examples)} example updates")
                if not hasattr(annotator, "meta_judge_examples"):
                    annotator.meta_judge_examples = []
                annotator.meta_judge_examples.extend(examples)

        # Inject threshold updates
        if "thresholds" in judgment.context_injections:
            thresholds = judgment.context_injections["thresholds"]
            print("  Meta-judge context injection: threshold updates")
            if not hasattr(annotator, "meta_judge_thresholds"):
                annotator.meta_judge_thresholds = {}
            annotator.meta_judge_thresholds.update(thresholds)

    # Extract actionable feedback from recommendations and issues
    # Convert to prompt additions for dynamic injection
    for rec in judgment.recommendations:
        if "score" in rec.lower() or "calibration" in rec.lower() or "example" in rec.lower():
            if not hasattr(annotator, "meta_judge_prompt_additions"):
                annotator.meta_judge_prompt_additions = []
            # Add as prompt addition if it's about scoring/calibration
            annotator.meta_judge_prompt_additions.append(rec)

    for issue in judgment.issues:
        if issue.suggested_fix and (
            "score" in issue.suggested_fix.lower() or "example" in issue.suggested_fix.lower()
        ):
            if not hasattr(annotator, "meta_judge_prompt_additions"):
                annotator.meta_judge_prompt_additions = []
            annotator.meta_judge_prompt_additions.append(issue.suggested_fix)

    # Log actionable feedback
    if actionable_feedback:
        print("  Meta-judge actionable feedback:")
        for feedback in actionable_feedback[:5]:  # Show top 5
            print(f"    → {feedback}")


if __name__ == "__main__":
    import asyncio

    # Test meta-judge
    async def test():
        test_annotations = [
            {
                "card1": "Lightning Bolt",
                "card2": "Chain Lightning",
                "similarity_score": 0.92,
                "reasoning": "Both are 1-mana red instant burn spells dealing 3 damage. Functionally identical.",
                "source": "llm",
                "game": "magic",
            },
            {
                "card1": "Brainstorm",
                "card2": "Ponder",
                "similarity_score": 0.88,
                "reasoning": "Both are blue card selection spells. Brainstorm is instant, Ponder is sorcery.",
                "source": "llm",
                "game": "magic",
            },
        ]

        judgment = await meta_judge_annotations(test_annotations, game="magic")
        print("Meta-Judgment:")
        print(f"  Overall Quality: {judgment.overall_quality:.2f}")
        print(f"  Issues: {len(judgment.issues)}")
        print(f"  Recommendations: {len(judgment.recommendations)}")
        print(f"\nFeedback:\n{judgment.feedback}")

    asyncio.run(test())
