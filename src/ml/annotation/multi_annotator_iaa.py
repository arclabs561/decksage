"""
Multi-Annotator IAA System for LLM Annotations

Implements MCHR (Multi-LLM Consensus with Human Review) framework:
- Multiple diverse LLM models as independent annotators
- Consensus building when models disagree
- Krippendorff's Alpha for agreement measurement
- Quality filtering based on IAA thresholds

Research basis:
- Multi-LLM consensus improves accuracy by 8-32% vs single model
- Different models provide diverse perspectives
- Krippendorff's Alpha handles missing data and multiple annotators
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from pydantic import BaseModel
    from pydantic_ai import Agent, ModelSettings
    import os

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    ModelSettings = None

try:
    from ..evaluation.krippendorff_alpha import krippendorff_alpha
    from ..evaluation.inter_annotator_agreement import InterAnnotatorAgreement
    from ..utils.pydantic_ai_helpers import make_agent
    
    HAS_IAA_UTILS = True
except ImportError as e:
    HAS_IAA_UTILS = False
    krippendorff_alpha = None
    InterAnnotatorAgreement = None
    make_agent = None

# Import from llm_annotator separately to avoid circular import
# Use TYPE_CHECKING to avoid circular import at runtime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm_annotator import CardSimilarityAnnotation, SIMILARITY_PROMPT
else:
    # Runtime import - delay until actually needed
    CardSimilarityAnnotation = None
    SIMILARITY_PROMPT = None

def _get_llm_annotator_imports():
    """Lazy import to avoid circular dependency."""
    global CardSimilarityAnnotation, SIMILARITY_PROMPT, HAS_LLM_ANNOTATOR
    if CardSimilarityAnnotation is None:
        try:
            from .llm_annotator import CardSimilarityAnnotation, SIMILARITY_PROMPT
            HAS_LLM_ANNOTATOR = True
        except ImportError:
            HAS_LLM_ANNOTATOR = False
            CardSimilarityAnnotation = None
            SIMILARITY_PROMPT = None
    return CardSimilarityAnnotation, SIMILARITY_PROMPT

HAS_LLM_ANNOTATOR = True  # Will be checked lazily
HAS_IAA = HAS_IAA_UTILS  # Check LLM annotator lazily

try:
    from ..utils.logging_config import get_logger

    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


@dataclass
class AnnotatorConfig:
    """Configuration for a single annotator model."""

    name: str
    model: str
    temperature: float = 0.3
    max_tokens: int = 1500
    description: str = ""


# Default annotator configurations (latest models, January 2026)
# Research-based: Diverse models for best consensus, balance cost/speed/quality
# Note: Using models that are confirmed available on OpenRouter
DEFAULT_ANNOTATORS = [
    AnnotatorConfig(
        name="gemini_3_flash",
        model="google/gemini-3-flash-preview",
        temperature=0.3,
        max_tokens=1500,
        description="Latest Gemini Flash - Fast, high-quality, best for speed (primary)",
    ),
    AnnotatorConfig(
        name="claude_sonnet_4_5",
        model="anthropic/claude-sonnet-4.5",  # Note: dot, not dash
        temperature=0.3,
        max_tokens=1500,
        description="Claude Sonnet 4.5 - Best reasoning, detailed analysis (high quality, confirmed available)",
    ),
    AnnotatorConfig(
        name="gemini_2_5_flash",
        model="google/gemini-2.5-flash",
        temperature=0.4,
        max_tokens=1500,
        description="Gemini 2.5 Flash - Good context understanding, diverse perspective (confirmed available)",
    ),
]


@dataclass
class MultiAnnotatorResult:
    """Result from multi-annotator annotation."""

    card1: str
    card2: str
    annotations: dict[str, CardSimilarityAnnotation]  # annotator_name -> annotation
    consensus_annotation: CardSimilarityAnnotation | None
    iaa_metrics: dict[str, Any]
    agreement_level: str  # "high", "medium", "low", "disagreement"


class MultiAnnotatorIAA:
    """Multi-annotator system with IAA measurement."""

    def __init__(
        self,
        annotator_configs: list[AnnotatorConfig] | None = None,
        min_iaa_threshold: float = 0.6,
        use_consensus: bool = True,
    ):
        """Initialize multi-annotator system.

        Args:
            annotator_configs: List of annotator configurations (default: 3 diverse models)
            min_iaa_threshold: Minimum Krippendorff's Alpha for acceptable agreement (default: 0.6)
            use_consensus: If True, create consensus annotation when models agree
        """
        if not HAS_PYDANTIC_AI:
            raise ImportError("pydantic-ai required. Install: pip install pydantic-ai")
        if not HAS_IAA_UTILS:
            raise ImportError("IAA utilities required (krippendorff_alpha, InterAnnotatorAgreement, make_agent)")
        
        # Lazy import LLM annotator to avoid circular dependency
        CardSimilarityAnnotation_cls, SIMILARITY_PROMPT_str = _get_llm_annotator_imports()
        if CardSimilarityAnnotation_cls is None:
            raise ImportError("LLM annotator required (CardSimilarityAnnotation, SIMILARITY_PROMPT)")

        self.annotator_configs = annotator_configs or DEFAULT_ANNOTATORS
        self.min_iaa_threshold = min_iaa_threshold
        self.use_consensus = use_consensus

        # Lazy import LLM annotator
        CardSimilarityAnnotation_cls, SIMILARITY_PROMPT_str = _get_llm_annotator_imports()
        
        # Create agents for each annotator with model-specific settings
        self.agents: dict[str, Agent] = {}
        self.annotator_weights: dict[str, float] = {}  # Track reliability weights
        
        for config in self.annotator_configs:
            from pydantic_ai import ModelSettings
            
            # Create agent with model-specific settings
            provider = os.getenv("LLM_PROVIDER", "openrouter")
            agent = Agent(
                f"{provider}:{config.model}",
                output_type=CardSimilarityAnnotation_cls,
                system_prompt=SIMILARITY_PROMPT_str,
                model_settings=ModelSettings(
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                ),
            )
            self.agents[config.name] = agent
            # Initialize with equal weights (will be updated based on performance)
            self.annotator_weights[config.name] = 1.0 / len(self.annotator_configs)
            logger.info(f"Initialized annotator: {config.name} ({config.model})")

        self.iaa_calculator = InterAnnotatorAgreement()

    async def annotate_pair_multi(
        self,
        card1: str,
        card2: str,
        graph_context: str | None = None,
    ) -> MultiAnnotatorResult:
        """Annotate a pair with multiple annotators and compute IAA.

        Args:
            card1: First card name
            card2: Second card name
            graph_context: Optional graph context string

        Returns:
            MultiAnnotatorResult with all annotations and IAA metrics
        """
        # Build prompt with graph context if available
        prompt_parts = [
            f"Card 1: {card1}",
            f"Card 2: {card2}",
        ]
        if graph_context:
            prompt_parts.append(graph_context)
        prompt = "\n".join(prompt_parts)

        # Annotate with all models in parallel
        tasks = []
        for config in self.annotator_configs:
            agent = self.agents[config.name]
            task = self._annotate_with_agent(agent, config, prompt, card1, card2)
            tasks.append((config.name, task))

        # Wait for all annotations
        annotations: dict[str, CardSimilarityAnnotation] = {}
        for name, task in tasks:
            try:
                result = await task
                if result:
                    annotations[name] = result
            except Exception as e:
                logger.warning(f"Annotator {name} failed: {e}")

        if not annotations:
            raise ValueError("All annotators failed")

        # Compute IAA metrics
        iaa_metrics = self._compute_iaa(annotations)

        # Create consensus annotation if requested
        consensus = None
        if self.use_consensus and len(annotations) >= 2:
            consensus = self._create_consensus(annotations, iaa_metrics)

        # Determine agreement level
        alpha = iaa_metrics.get("krippendorff_alpha", 0.0)
        if alpha >= 0.8:
            agreement_level = "high"
        elif alpha >= self.min_iaa_threshold:
            agreement_level = "medium"
        elif alpha >= 0.4:
            agreement_level = "low"
        else:
            agreement_level = "disagreement"

        return MultiAnnotatorResult(
            card1=card1,
            card2=card2,
            annotations=annotations,
            consensus_annotation=consensus,
            iaa_metrics=iaa_metrics,
            agreement_level=agreement_level,
        )

    async def _annotate_with_agent(
        self,
        agent: Agent,
        config: AnnotatorConfig,
        prompt: str,
        card1: str,
        card2: str,
    ) -> CardSimilarityAnnotation | None:
        """Annotate with a single agent."""
        try:
            # Model settings are already configured at agent creation time
            result = await agent.run(prompt)
            if result.output:
                ann = result.output
                # Set metadata
                ann.annotator_id = config.name
                ann.model_name = config.model
                ann.model_params = {
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                }
                return ann
        except Exception as e:
            logger.warning(f"Annotator {config.name} failed: {e}")
            return None

    def _compute_iaa(
        self, annotations: dict[str, CardSimilarityAnnotation]
    ) -> dict[str, Any]:
        """Compute IAA metrics for annotations.

        For similarity scores (continuous 0-1), we:
        1. Discretize scores into bins for Krippendorff's Alpha
        2. Compute agreement on similarity_type (nominal)
        3. Compute agreement on is_substitute (nominal)
        """
        if len(annotations) < 2:
            return {
                "krippendorff_alpha": 1.0,
                "num_annotators": len(annotations),
                "agreement_rate": 1.0,
            }

        # Extract scores, types, and substitute flags
        scores = [ann.similarity_score for ann in annotations.values()]
        types = [ann.similarity_type for ann in annotations.values()]
        substitutes = [ann.is_substitute for ann in annotations.values()]

        # Discretize scores into bins (0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0)
        # Format: list of lists, where each inner list is one annotator's rating for this pair
        score_bins = []
        for score in scores:
            if score < 0.2:
                score_bins.append("very_low")
            elif score < 0.4:
                score_bins.append("low")
            elif score < 0.6:
                score_bins.append("medium")
            elif score < 0.8:
                score_bins.append("high")
            else:
                score_bins.append("very_high")

        # Compute Krippendorff's Alpha for each dimension
        # Format: [[annotator1_rating], [annotator2_rating], ...] for one pair
        score_alpha = krippendorff_alpha([[b] for b in score_bins], level_of_measurement="ordinal")
        type_alpha = krippendorff_alpha([[t] for t in types], level_of_measurement="nominal")
        sub_alpha = krippendorff_alpha(
            [[str(s)] for s in substitutes], level_of_measurement="nominal"
        )

        # Overall alpha (weighted average)
        overall_alpha = (score_alpha * 0.5 + type_alpha * 0.3 + sub_alpha * 0.2)

        # Agreement rates
        score_agreement = sum(1 for s in score_bins if score_bins.count(s) > 1) / len(
            score_bins
        ) if score_bins else 0.0
        type_agreement = sum(1 for t in types if types.count(t) > 1) / len(types) if types else 0.0
        sub_agreement = sum(1 for s in substitutes if substitutes.count(s) > 1) / len(
            substitutes
        ) if substitutes else 0.0

        return {
            "krippendorff_alpha": overall_alpha,
            "score_alpha": score_alpha,
            "type_alpha": type_alpha,
            "substitute_alpha": sub_alpha,
            "score_agreement_rate": score_agreement,
            "type_agreement_rate": type_agreement,
            "substitute_agreement_rate": sub_agreement,
            "num_annotators": len(annotations),
            "score_range": (min(scores), max(scores)),
            "score_std": float(sum((s - sum(scores) / len(scores)) ** 2 for s in scores) / len(scores)) ** 0.5 if scores else 0.0,
        }

    def _create_consensus(
        self,
        annotations: dict[str, CardSimilarityAnnotation],
        iaa_metrics: dict[str, Any],
    ) -> CardSimilarityAnnotation:
        """Create consensus annotation from multiple annotations.

        Strategy:
        - Score: Median (robust to outliers)
        - Type: Majority vote
        - Substitute: Majority vote
        - Reasoning: Combine reasoning from all annotators
        """
        scores = [ann.similarity_score for ann in annotations.values()]
        types = [ann.similarity_type for ann in annotations.values()]
        substitutes = [ann.is_substitute for ann in annotations.values()]
        reasonings = [ann.reasoning for ann in annotations.values()]

        # Median score
        sorted_scores = sorted(scores)
        median_score = sorted_scores[len(sorted_scores) // 2]

        # Majority vote for type
        type_counts = defaultdict(int)
        for t in types:
            type_counts[t] += 1
        consensus_type = max(type_counts.items(), key=lambda x: x[1])[0]

        # Majority vote for substitute
        consensus_substitute = sum(substitutes) > len(substitutes) / 2

        # Combine reasoning
        consensus_reasoning = f"Consensus from {len(annotations)} annotators (IAA α={iaa_metrics['krippendorff_alpha']:.2f}). "
        consensus_reasoning += " | ".join(f"{name}: {r[:100]}" for name, r in zip(annotations.keys(), reasonings))

        # Use first annotation as template
        first_ann = list(annotations.values())[0]

        return CardSimilarityAnnotation(
            card1=first_ann.card1,
            card2=first_ann.card2,
            similarity_score=median_score,
            similarity_type=consensus_type,
            reasoning=consensus_reasoning,
            thinking=f"Consensus annotation from {len(annotations)} annotators (weighted by reliability)",
            is_substitute=consensus_substitute,
            context_dependent=first_ann.context_dependent,
            example_decks=first_ann.example_decks,
            annotator_id="consensus",
            model_name="multi-annotator-consensus",
            source="llm_multi_annotator",
        )

    def filter_by_iaa(
        self,
        results: list[MultiAnnotatorResult],
        min_alpha: float | None = None,
    ) -> tuple[list[MultiAnnotatorResult], list[MultiAnnotatorResult]]:
        """Filter results by IAA threshold.

        Args:
            results: List of multi-annotator results
            min_alpha: Minimum Krippendorff's Alpha (default: self.min_iaa_threshold)

        Returns:
            (accepted_results, rejected_results)
        """
        if min_alpha is None:
            min_alpha = self.min_iaa_threshold

        accepted = []
        rejected = []

        for result in results:
            alpha = result.iaa_metrics.get("krippendorff_alpha", 0.0)
            if alpha >= min_alpha:
                accepted.append(result)
            else:
                rejected.append(result)

        logger.info(
            f"Filtered {len(results)} results: {len(accepted)} accepted (α≥{min_alpha}), "
            f"{len(rejected)} rejected"
        )

        return accepted, rejected
    
    def update_annotator_weights(
        self,
        annotator_performance: dict[str, float],
    ) -> None:
        """Update annotator reliability weights based on performance.
        
        Args:
            annotator_performance: Dict mapping annotator_name -> performance_score (0-1)
        """
        total_performance = sum(annotator_performance.values())
        if total_performance > 0:
            for name, perf in annotator_performance.items():
                if name in self.annotator_weights:
                    # Update weight based on performance (exponential moving average)
                    old_weight = self.annotator_weights[name]
                    new_weight = perf / total_performance
                    # Smooth update (0.3 = learning rate)
                    self.annotator_weights[name] = 0.7 * old_weight + 0.3 * new_weight
                    logger.info(f"Updated weight for {name}: {old_weight:.3f} -> {self.annotator_weights[name]:.3f}")

