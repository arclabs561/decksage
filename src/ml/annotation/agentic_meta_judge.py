#!/usr/bin/env python3
"""
Agentic Meta-Judge with Multi-Round Conversation and IAA Moderation

Implements a sophisticated meta-judge system that:
1. Acts as an IAA moderator in multi-round conversations
2. Dynamically injects feedback via chat history (not just static prompts)
3. Uses multi-round voting/consensus scheme
4. Maintains conversation state across rounds

This replaces hard rules with agentic, context-aware feedback loops.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any


try:
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent, ModelMessage

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    BaseModel = object

    def _field(default=None, **_kwargs):
        """Fallback Field for when pydantic is not available."""
        return default

    Field = _field


# Avoid circular import - use TYPE_CHECKING for forward reference
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .llm_annotator import CardSimilarityAnnotation
else:
    # At runtime, import will be deferred
    CardSimilarityAnnotation = None

# Only import make_agent if pydantic-ai is available
if HAS_PYDANTIC_AI:
    from ..utils.pydantic_ai_helpers import make_agent
else:
    make_agent = None  # type: ignore

logger = logging.getLogger(__name__)


class MetaJudgeFeedback(BaseModel):
    """Feedback from meta-judge for a single annotation."""

    quality_score: float = Field(
        ge=0.0, le=1.0, description="Quality score for this annotation (0.0-1.0)"
    )
    issues: list[str] = Field(default_factory=list, description="Specific issues identified")
    suggestions: list[str] = Field(
        default_factory=list, description="Specific suggestions for improvement"
    )
    should_revise: bool = Field(description="Whether the annotator should revise this annotation")
    revision_guidance: str | None = Field(
        None, description="Specific guidance for revision if should_revise=True"
    )


class ConsensusDecision(BaseModel):
    """Meta-judge decision on whether consensus is reached."""

    consensus_reached: bool = Field(
        description="Whether annotators have reached sufficient consensus"
    )
    consensus_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Consensus strength (1.0 = perfect agreement, 0.0 = no agreement)",
    )
    quality_acceptable: bool = Field(description="Whether the annotation quality is acceptable")
    feedback_for_round: str = Field(description="Feedback to provide to annotators for next round")
    recommended_action: str = Field(
        description="Action to take: 'accept', 'revise', 'reject', 'continue_rounds'"
    )


@dataclass
class AnnotationRound:
    """Represents one round of annotation with feedback."""

    round_number: int
    annotations: dict[str, CardSimilarityAnnotation]  # annotator_id -> annotation
    meta_judge_feedback: dict[str, MetaJudgeFeedback] | None = None  # annotator_id -> feedback
    conversation_history: list[ModelMessage] = field(default_factory=list)
    consensus_decision: ConsensusDecision | None = None


class AgenticMetaJudge:
    """Agentic meta-judge that moderates multi-round annotation conversations."""

    def __init__(
        self,
        model: str | None = None,
        max_rounds: int = 3,
        min_consensus_threshold: float = 0.7,
        min_quality_threshold: float = 0.6,
    ):
        """Initialize agentic meta-judge.

        Args:
            model: Model to use for meta-judge (default: Claude Sonnet for reasoning)
            max_rounds: Maximum number of revision rounds
            min_consensus_threshold: Minimum consensus score to accept (0.0-1.0)
            min_quality_threshold: Minimum quality score to accept (0.0-1.0)
        """
        if not HAS_PYDANTIC_AI:
            raise ImportError("pydantic-ai required: pip install pydantic-ai")

        self.max_rounds = max_rounds
        self.min_consensus_threshold = min_consensus_threshold
        self.min_quality_threshold = min_quality_threshold

        # Create meta-judge agent for individual annotation feedback
        self.feedback_agent = self._create_feedback_agent(model)

        # Create consensus agent for multi-round moderation
        self.consensus_agent = self._create_consensus_agent(model)

    def _create_feedback_agent(self, model: str | None) -> Agent:
        """Create agent for providing feedback on individual annotations."""
        if model is None:
            model = "anthropic/claude-sonnet-4.5"  # Best for reasoning

        system_prompt = """You are an expert annotation quality moderator for trading card game similarity annotations.

Your role is to:
1. Review individual annotations for quality and consistency
2. Identify specific issues (score calibration, reasoning gaps, graph evidence misuse)
3. Provide actionable feedback for improvement
4. Decide if revision is needed

**Evaluation Criteria:**
- Score calibration: Does the score match the reasoning and evidence?
- Graph evidence usage: Is graph evidence (Jaccard, co-occurrence) properly considered?
- Reasoning quality: Is the reasoning clear, specific, and justified?
- Consistency: Does this annotation align with similar annotations?

**Feedback Style:**
- Be specific and actionable
- Point to exact issues (e.g., "Score 0.2 seems low given Jaccard 0.4 and same function")
- Provide concrete suggestions (e.g., "Consider raising to 0.5-0.6 given graph evidence")
- Distinguish between synergy (cards work together) and similarity (cards can replace each other)

**Revision Guidance:**
- Only suggest revision if there are clear, fixable issues
- Provide specific guidance on what to change
- Consider if the issue is a matter of judgment vs. error"""

        return make_agent(
            model,
            MetaJudgeFeedback,
            system_prompt,
            model_settings={"temperature": 0.3, "max_tokens": 1000},
        )

    def _create_consensus_agent(self, model: str | None) -> Agent:
        """Create agent for consensus moderation across rounds."""
        if model is None:
            model = "anthropic/claude-sonnet-4.5"

        system_prompt = """You are an IAA (Inter-Annotator Agreement) moderator for multi-round annotation consensus.

Your role is to:
1. Evaluate consensus across multiple annotators
2. Assess overall annotation quality
3. Decide whether to accept, revise, or continue rounds
4. Provide feedback for the next round if needed

**Consensus Evaluation:**
- High consensus (0.8+): Annotators agree closely → Accept
- Medium consensus (0.6-0.8): Some disagreement but acceptable → Accept or continue
- Low consensus (<0.6): Significant disagreement → Revise or continue rounds

**Quality Assessment:**
- Consider both individual annotation quality and consensus
- High quality + high consensus → Accept
- High quality + low consensus → Continue rounds (let annotators converge)
- Low quality → Revise regardless of consensus

**Decision Logic:**
- Accept: High consensus (≥0.7) AND acceptable quality (≥0.6)
- Continue rounds: Medium consensus (0.5-0.7) AND quality improving
- Revise: Low consensus (<0.5) OR quality below threshold
- Reject: Multiple rounds failed to improve

**Feedback for Next Round:**
- Be specific about what needs to converge
- Point to specific disagreements (e.g., "Annotators disagree on score range: 0.3 vs 0.7")
- Provide guidance on how to resolve (e.g., "Consider graph evidence more strongly")
- Encourage annotators to explain their reasoning more clearly"""

        return make_agent(
            model,
            ConsensusDecision,
            system_prompt,
            model_settings={"temperature": 0.3, "max_tokens": 1500},
        )

    async def moderate_annotation_round(
        self,
        round_data: AnnotationRound,
        previous_rounds: list[AnnotationRound] | None = None,
    ) -> AnnotationRound:
        """Moderate one round of annotations with feedback.

        Args:
            round_data: Current round's annotations
            previous_rounds: Previous rounds for context

        Returns:
            Updated round_data with feedback and consensus decision
        """
        # Step 1: Get feedback for each annotation
        feedback_tasks = []
        for annotator_id, annotation in round_data.annotations.items():
            task = self._get_annotation_feedback(
                annotation,
                annotator_id,
                round_data.round_number,
                round_data.conversation_history,
            )
            feedback_tasks.append((annotator_id, task))

        # Collect feedback
        feedback_results: dict[str, MetaJudgeFeedback] = {}
        for annotator_id, task in feedback_tasks:
            try:
                feedback = await task
                feedback_results[annotator_id] = feedback
            except Exception as e:
                logger.warning(f"Meta-judge feedback failed for {annotator_id}: {e}")
                # Create default feedback
                feedback_results[annotator_id] = MetaJudgeFeedback(
                    quality_score=0.5,
                    should_revise=False,
                    issues=["Feedback generation failed"],
                )

        round_data.meta_judge_feedback = feedback_results

        # Step 2: Evaluate consensus and make decision
        consensus_decision = await self._evaluate_consensus(
            round_data,
            previous_rounds or [],
        )
        round_data.consensus_decision = consensus_decision

        # Step 3: Update conversation history with feedback
        feedback_messages = self._create_feedback_messages(feedback_results, consensus_decision)
        round_data.conversation_history.extend(feedback_messages)

        return round_data

    async def _get_annotation_feedback(
        self,
        annotation: CardSimilarityAnnotation,
        annotator_id: str,
        round_number: int,
        conversation_history: list[ModelMessage],
    ) -> MetaJudgeFeedback:
        """Get feedback for a single annotation."""
        # Build prompt with annotation details
        prompt = f"""Review this annotation from Round {round_number}:

**Annotator**: {annotator_id}
**Card 1**: {annotation.card1}
**Card 2**: {annotation.card2}
**Similarity Score**: {annotation.similarity_score}
**Similarity Type**: {annotation.similarity_type}
**Reasoning**: {annotation.reasoning}
**Thinking**: {annotation.thinking if hasattr(annotation, "thinking") else "N/A"}

**Graph Features** (if available):
{self._format_graph_features(annotation)}

Evaluate this annotation and provide SPECIFIC, ACTIONABLE feedback. Consider:
1. Does the score match the reasoning and evidence? (Be specific: "Score 0.2 but reasoning suggests 0.5")
2. Is graph evidence properly considered? (Point to specific graph metrics: "Jaccard 0.4 suggests score >= 0.6")
3. Is the reasoning clear and justified? (Identify gaps: "Missing function analysis")
4. Are there any calibration issues? (Be specific: "Scores clustered in 0.2-0.3 range, not using full 0-1 scale")

**Provide:**
- SPECIFIC issues with examples
- CONCRETE suggestions for improvement
- TARGETED guidance for this annotator
- EXAMPLES of what good annotations look like
"""

        # Run with conversation history for context
        result = await self.feedback_agent.run(
            prompt,
            message_history=conversation_history,
        )

        return result.output

    async def _evaluate_consensus(
        self,
        current_round: AnnotationRound,
        previous_rounds: list[AnnotationRound],
    ) -> ConsensusDecision:
        """Evaluate consensus across annotators and make decision."""
        # Build prompt with all annotations and history
        prompt_parts = [
            f"**Round {current_round.round_number} Annotations:**",
        ]

        for annotator_id, annotation in current_round.annotations.items():
            feedback = (
                current_round.meta_judge_feedback.get(annotator_id)
                if current_round.meta_judge_feedback
                else None
            )
            prompt_parts.append(
                f"\n**{annotator_id}**:\n"
                f"  Score: {annotation.similarity_score}\n"
                f"  Reasoning: {annotation.reasoning[:200]}...\n"
                f"  Quality: {feedback.quality_score if feedback else 'N/A'}\n"
                f"  Issues: {', '.join(feedback.issues) if feedback and feedback.issues else 'None'}"
            )

        if previous_rounds:
            prompt_parts.append(f"\n**Previous Rounds**: {len(previous_rounds)} rounds completed")
            for prev_round in previous_rounds[-2:]:  # Last 2 rounds for context
                prompt_parts.append(
                    f"  Round {prev_round.round_number}: "
                    f"Consensus={prev_round.consensus_decision.consensus_score if prev_round.consensus_decision else 'N/A'}"
                )

        prompt_parts.append(
            f"\n**Context**:\n"
            f"  Max rounds: {self.max_rounds}\n"
            f"  Min consensus threshold: {self.min_consensus_threshold}\n"
            f"  Min quality threshold: {self.min_quality_threshold}\n"
            f"  Current round: {current_round.round_number}"
        )

        prompt_parts.append(
            "\nEvaluate consensus and decide: accept, revise, continue rounds, or reject?"
        )

        prompt = "\n".join(prompt_parts)

        # Use conversation history from previous rounds
        all_history: list[ModelMessage] = []
        for prev_round in previous_rounds:
            all_history.extend(prev_round.conversation_history)

        result = await self.consensus_agent.run(
            prompt,
            message_history=all_history,
        )

        return result.output

    def _format_graph_features(
        self, annotation: Any
    ) -> str:  # CardSimilarityAnnotation (avoid circular import)
        """Format graph features for feedback prompt."""
        # Extract graph features from annotation if available
        # This would need to be adapted based on how graph features are stored
        graph_features = getattr(annotation, "graph_features", None)
        if graph_features and isinstance(graph_features, dict):
            jaccard = graph_features.get("jaccard_similarity", "N/A")
            cooccur = graph_features.get("cooccurrence_count", "N/A")
            return f"Jaccard: {jaccard}, Co-occurrence: {cooccur}"
        return "No graph features available"

    def _create_feedback_messages(
        self,
        feedback: dict[str, MetaJudgeFeedback],
        consensus: ConsensusDecision,
    ) -> list[ModelMessage]:
        """Create conversation messages from feedback for next round."""
        # Create feedback summary for conversation history
        feedback_summary = f"""**Meta-Judge Feedback Summary (Round {consensus.round_number if hasattr(consensus, "round_number") else "N/A"})**:

**Consensus Decision**: {consensus.recommended_action}
**Consensus Score**: {consensus.consensus_score:.2f}
**Quality Acceptable**: {consensus.quality_acceptable}

**Feedback for Next Round**:
{consensus.feedback_for_round}

**Individual Annotator Feedback**:
"""
        for annotator_id, fb in feedback.items():
            feedback_summary += f"\n**{annotator_id}**:\n"
            feedback_summary += f"  Quality: {fb.quality_score:.2f}\n"
            if fb.issues:
                feedback_summary += f"  Issues: {', '.join(fb.issues)}\n"
            if fb.suggestions:
                feedback_summary += f"  Suggestions: {', '.join(fb.suggestions)}\n"
            if fb.should_revise and fb.revision_guidance:
                feedback_summary += f"  Revision Guidance: {fb.revision_guidance}\n"

        # Create message history for conversation (pydantic-ai accepts dict format)
        # Using user message type to represent feedback (will be seen by annotators in next round)
        # pydantic-ai's message_history expects a list of dicts with 'role' and 'content'
        return [{"role": "user", "content": feedback_summary}]

    async def moderate_multi_round(
        self,
        initial_annotations: dict[str, Any],  # CardSimilarityAnnotation (avoid circular import)
        multi_annotator: Any | None = None,
        card1: str | None = None,
        card2: str | None = None,
        graph_context: str | None = None,
    ) -> tuple[AnnotationRound, list[AnnotationRound]]:
        """Moderate multi-round annotation process until consensus or max rounds.

        Args:
            initial_annotations: Initial annotations from multiple annotators
            multi_annotator: MultiAnnotatorIAA instance for revision calls (optional)
            card1: First card name (required for revisions)
            card2: Second card name (required for revisions)
            graph_context: Graph context string (optional, for revisions)

        Returns:
            Final round and all rounds (for analysis)
        """
        all_rounds: list[AnnotationRound] = []
        current_annotations = initial_annotations

        for round_num in range(1, self.max_rounds + 1):
            # Create round
            round_data = AnnotationRound(
                round_number=round_num,
                annotations=current_annotations,
            )

            # Moderate this round
            round_data = await self.moderate_annotation_round(round_data, all_rounds)
            all_rounds.append(round_data)

            # Check if we should stop
            if (
                round_data.consensus_decision
                and round_data.consensus_decision.recommended_action
                in [
                    "accept",
                    "reject",
                ]
            ):
                logger.info(
                    f"Round {round_num}: Stopping early - {round_data.consensus_decision.recommended_action}"
                )
                return round_data, all_rounds

            # If continuing and we have annotator access, call for revisions
            if (
                round_data.consensus_decision
                and round_data.consensus_decision.recommended_action == "revise"
                and multi_annotator is not None
                and card1 is not None
                and card2 is not None
            ):
                logger.info(f"Round {round_num}: Calling annotators for revision...")
                # Get revised annotations with feedback
                revised_annotations = await self._revise_annotations(
                    multi_annotator=multi_annotator,
                    card1=card1,
                    card2=card2,
                    graph_context=graph_context,
                    previous_round=round_data,
                    all_previous_rounds=all_rounds,
                )
                if revised_annotations:
                    logger.info(
                        f"Round {round_num}: Received {len(revised_annotations)} revised annotations"
                    )
                    current_annotations = revised_annotations
                else:
                    # Revision failed, return current round
                    logger.warning("Revision failed, returning current round")
                    return round_data, all_rounds
            elif (
                round_data.consensus_decision
                and round_data.consensus_decision.recommended_action == "revise"
            ):
                logger.warning(
                    f"Round {round_num}: Revision requested but missing requirements "
                    f"(multi_annotator={multi_annotator is not None}, "
                    f"card1={card1 is not None}, card2={card2 is not None})"
                )

            # Max rounds reached
            if round_num >= self.max_rounds:
                logger.info(f"Round {round_num}: Max rounds reached")
                return round_data, all_rounds

        return all_rounds[-1], all_rounds

    async def _revise_annotations(
        self,
        multi_annotator: Any,  # MultiAnnotatorIAA
        card1: str,
        card2: str,
        graph_context: str | None,
        previous_round: AnnotationRound,
        all_previous_rounds: list[AnnotationRound],
    ) -> dict[str, Any] | None:  # CardSimilarityAnnotation (avoid circular import)
        """Call annotators again with feedback for revision.

        Args:
            multi_annotator: MultiAnnotatorIAA instance
            card1: First card name
            card2: Second card name
            graph_context: Graph context string
            previous_round: Previous round data with feedback
            all_previous_rounds: All previous rounds for context

        Returns:
            Revised annotations or None if revision failed
        """
        try:
            # Build conversation history from all previous rounds
            message_history: dict[str, list[ModelMessage]] = {}

            # Collect conversation history per annotator
            for prev_round in all_previous_rounds:
                if prev_round.conversation_history:
                    # Distribute feedback to each annotator's history
                    for annotator_id in prev_round.annotations:
                        if annotator_id not in message_history:
                            message_history[annotator_id] = []
                        # Add feedback messages to each annotator's history
                        message_history[annotator_id].extend(prev_round.conversation_history)

            # Enhance graph context with feedback summary
            enhanced_graph_context = graph_context or ""
            if previous_round.consensus_decision:
                feedback_summary = f"""
**Previous Round Feedback**:
{previous_round.consensus_decision.feedback_for_round}

**Revision Guidance**:
- Consensus score: {previous_round.consensus_decision.consensus_score:.2f}
- Recommended action: {previous_round.consensus_decision.recommended_action}
"""
                enhanced_graph_context = f"{graph_context or ''}\n{feedback_summary}".strip()

            # Call annotators again with conversation history
            # This will use message_history to inject feedback
            multi_result = await multi_annotator.annotate_pair_multi(
                card1=card1,
                card2=card2,
                graph_context=enhanced_graph_context,
                message_history=message_history,
            )

            # Return revised annotations
            if multi_result.annotations:
                return multi_result.annotations
            else:
                logger.warning("Revision returned no annotations")
                return None

        except Exception as e:
            logger.error(f"Revision failed: {e}", exc_info=True)
            return None
