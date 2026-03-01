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

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any


try:
    import os

    from pydantic_ai import Agent, ModelSettings

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    ModelSettings = None

try:
    from ..evaluation.inter_annotator_agreement import InterAnnotatorAgreement
    from ..evaluation.krippendorff_alpha import krippendorff_alpha
    from ..utils.pydantic_ai_helpers import make_agent

    HAS_IAA_UTILS = True
except ImportError:
    HAS_IAA_UTILS = False
    krippendorff_alpha = None
    InterAnnotatorAgreement = None
    make_agent = None

# Import from llm_annotator separately to avoid circular import
# Use TYPE_CHECKING to avoid circular import at runtime
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .llm_annotator import SIMILARITY_PROMPT, CardSimilarityAnnotation
else:
    # Runtime import - delay until actually needed
    CardSimilarityAnnotation = None
    SIMILARITY_PROMPT = None


def _get_llm_annotator_imports():
    """Lazy import to avoid circular dependency."""
    global CardSimilarityAnnotation, SIMILARITY_PROMPT, HAS_LLM_ANNOTATOR
    if CardSimilarityAnnotation is None:
        try:
            from .llm_annotator import SIMILARITY_PROMPT, CardSimilarityAnnotation

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


# Default annotator configurations (February 2026)
# Research-based: Diverse model architectures for best consensus.
# Key principle: different architectures at moderate temperature >> single model at high temperature.
# If 3+ different architectures agree, the signal is much stronger than self-agreement.
#
# Selection rationale (v3, 6 judges):
#   - 6 architectures from 5 providers for diversity
#   - Removed Haiku 4.5 (30% validation failure rate), Gemini 3 Flash (+0.08 score inflation)
#   - Removed DeepSeek V3.x (73% timeout rate -- OpenRouter routing unreliable)
#   - Prompt v5.0: tighter calibration anchors to reduce inter-judge scale mismatch
#   - Per-pair co-occurrence stats injected as factual context (not scoring guidance)
#
# Note: Using models confirmed available on OpenRouter with [S] structured_outputs
DEFAULT_ANNOTATORS = [
    # -- Tier 1: Frontier reasoning (anchor judges) --
    AnnotatorConfig(
        name="claude_sonnet_4_6",
        model="anthropic/claude-sonnet-4-6",
        temperature=0.3,
        max_tokens=2500,
        description="Claude Sonnet 4.6 - Frontier reasoning, strong structured output (Anthropic) $3.00/$15.00",
    ),
    AnnotatorConfig(
        name="gpt_5_2",
        model="openai/gpt-5.2",
        temperature=0.3,
        max_tokens=2500,
        description="GPT 5.2 - Adaptive reasoning, reduced hallucination (OpenAI) $1.75/$14.00",
    ),
    AnnotatorConfig(
        name="gemini_2_5_flash",
        model="google/gemini-2.5-flash",
        temperature=0.3,
        max_tokens=2500,
        description="Gemini 2.5 Flash - Fast, thinking, 1M context, reliable struct output (Google) $0.30/$2.50",
    ),
    # -- Tier 2: Strong mid-range (diverse architectures) --
    # DeepSeek V3.x removed: 73% timeout rate at 45s (V3.2) and V3.1 also times out.
    # OpenRouter routing to DeepSeek endpoints is unreliable for structured output.
    AnnotatorConfig(
        name="mistral_large_3",
        model="mistralai/mistral-large-2512",
        temperature=0.3,
        max_tokens=2500,
        description="Mistral Large 3 - 675B MoE, strong structured output (Mistral) $0.50/$1.50",
    ),
    AnnotatorConfig(
        name="qwen3_235b",
        model="qwen/qwen3-235b-a22b-2507",
        temperature=0.3,
        max_tokens=2500,
        description="Qwen3 235B A22B (Jul 2025) - MoE, confirmed tool_choice support (Alibaba) $0.071/$0.10",
    ),
    # -- Tier 3: Fast/cheap tiebreaker --
    AnnotatorConfig(
        name="grok_4_1_fast",
        model="x-ai/grok-4.1-fast",
        temperature=0.3,
        max_tokens=2500,
        description="Grok 4.1 Fast - 2M context, very cheap, fast (xAI) $0.20/$0.50",
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
    usage_by_judge: dict[str, dict] | None = None  # judge_name -> {input_tokens, output_tokens, requests}


class MultiAnnotatorIAA:
    """Multi-annotator system with IAA measurement."""

    def __init__(
        self,
        annotator_configs: list[AnnotatorConfig] | None = None,
        min_iaa_threshold: float = 0.6,
        use_consensus: bool = True,
        game: str | None = None,
        game_knowledge: dict[str, Any] | None = None,
    ):
        """Initialize multi-annotator system.

        Args:
            annotator_configs: List of annotator configurations (default: 3 diverse models)
            min_iaa_threshold: Minimum Krippendorff's Alpha for acceptable agreement (default: 0.6)
            use_consensus: If True, create consensus annotation when models agree
            game: Game name for game-specific system prompt (magic, pokemon, yugioh)
            game_knowledge: Optional dict from data/game_knowledge/{game}.json with
                           formats, archetypes, ban_lists, temporal_context, etc.
        """
        if not HAS_PYDANTIC_AI:
            raise ImportError("pydantic-ai required. Install: pip install pydantic-ai")
        if not HAS_IAA_UTILS:
            raise ImportError(
                "IAA utilities required (krippendorff_alpha, InterAnnotatorAgreement, make_agent)"
            )

        # Lazy import LLM annotator to avoid circular dependency
        card_similarity_annotation_cls, similarity_prompt_str = _get_llm_annotator_imports()
        if card_similarity_annotation_cls is None:
            raise ImportError(
                "LLM annotator required (CardSimilarityAnnotation, SIMILARITY_PROMPT)"
            )

        self.annotator_configs = annotator_configs or DEFAULT_ANNOTATORS
        self.min_iaa_threshold = min_iaa_threshold
        self.use_consensus = use_consensus
        self.game = game
        self.game_knowledge = game_knowledge

        # Use game-specific prompt if game is specified
        if game:
            try:
                from .llm_annotator import get_similarity_prompt
                similarity_prompt_str = get_similarity_prompt(game)
            except ImportError:
                pass  # Fall back to base prompt

        # Append game knowledge context (ban lists, format meta, archetypes)
        if game_knowledge:
            knowledge_lines = ["\n\n**GAME KNOWLEDGE (dynamic context):**"]
            # Ban lists by format
            for fmt in game_knowledge.get("formats", []):
                ban_list = fmt.get("ban_list", [])
                if ban_list and isinstance(ban_list, list) and len(ban_list) > 0:
                    knowledge_lines.append(
                        f"- {fmt['name']} ban list: {', '.join(ban_list[:20])}"
                        + (f" (+{len(ban_list)-20} more)" if len(ban_list) > 20 else "")
                    )
            # Temporal context (current meta)
            temporal = game_knowledge.get("temporal_context", {})
            if temporal.get("current_meta"):
                knowledge_lines.append(f"- Current meta: {temporal['current_meta'][:200]}")
            if temporal.get("recent_bans"):
                knowledge_lines.append(f"- Recent bans: {temporal['recent_bans'][:200]}")
            # Top archetypes
            for arch in game_knowledge.get("archetypes", [])[:3]:
                knowledge_lines.append(
                    f"- Archetype: {arch['name']} ({arch.get('meta_position', 'unknown tier')}) - "
                    f"{arch.get('strategy', '')[:100]}"
                )
            if len(knowledge_lines) > 1:
                similarity_prompt_str += "\n".join(knowledge_lines)
                logger.info(f"Injected {len(knowledge_lines)-1} game knowledge items into system prompt")

        # Create agents for each annotator with model-specific settings
        self.agents: dict[str, Agent] = {}
        self.annotator_weights: dict[str, float] = {}  # Track reliability weights

        for config in self.annotator_configs:
            from pydantic_ai import ModelSettings

            # Create agent with model-specific settings
            provider = os.getenv("LLM_PROVIDER", "openrouter")
            agent = Agent(
                f"{provider}:{config.model}",
                output_type=card_similarity_annotation_cls,
                system_prompt=similarity_prompt_str,
                model_settings=ModelSettings(
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                ),
                retries=0,  # No pydantic-ai validation retries -- skip judge on failure instead of re-prompting (halves latency)
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
        card_context: dict[str, dict[str, Any]] | None = None,
        message_history: dict[str, list] | None = None,
    ) -> MultiAnnotatorResult:
        """Annotate a pair with multiple annotators and compute IAA.

        Args:
            card1: First card name
            card2: Second card name
            graph_context: Optional graph context string
            card_context: Optional dict mapping card name -> attribute dict
                          (oracle_text, type_line, mana_cost, etc.)

        Returns:
            MultiAnnotatorResult with all annotations and IAA metrics
        """
        # Build prompt with card-level and graph context
        prompt_parts = [
            f"Card 1: {card1}",
            f"Card 2: {card2}",
        ]

        # Inject dynamic card context (oracle text, attributes)
        if card_context:
            for card_name, label in [(card1, "Card 1"), (card2, "Card 2")]:
                attrs = card_context.get(card_name, {})
                if attrs:
                    lines = [f"\n**{label} Details:**"]
                    if attrs.get("type_line"):
                        lines.append(f"  Type: {attrs['type_line']}")
                    if attrs.get("mana_cost"):
                        lines.append(f"  Mana Cost: {attrs['mana_cost']}")
                    if attrs.get("oracle_text"):
                        lines.append(f"  Text: {attrs['oracle_text']}")
                    if attrs.get("keywords"):
                        kw = attrs["keywords"]
                        if isinstance(kw, list):
                            kw = ", ".join(kw)
                        lines.append(f"  Keywords: {kw}")
                    if attrs.get("power") is not None and attrs.get("toughness") is not None:
                        lines.append(f"  P/T: {attrs['power']}/{attrs['toughness']}")
                    if attrs.get("color_identity"):
                        ci = attrs["color_identity"]
                        if isinstance(ci, list):
                            ci = "".join(ci)
                        lines.append(f"  Color Identity: {ci}")
                    prompt_parts.append("\n".join(lines))

        if graph_context:
            prompt_parts.append(graph_context)
        prompt = "\n".join(prompt_parts)

        # Run all judges in parallel with per-judge hard timeout.
        # Each judge is wrapped in asyncio.wait_for so TimeoutError completes
        # the coroutine from the caller's perspective. The underlying httpx
        # connection may linger as a zombie, but os._exit(0) at batch end
        # cleans those up.
        import asyncio as _aio

        JUDGE_TIMEOUT = 45.0  # per-judge hard timeout (most complete in <15s)

        async def _run_judge(config):
            agent = self.agents[config.name]
            annotator_history = message_history.get(config.name, []) if message_history else None
            try:
                result = await _aio.wait_for(
                    self._annotate_with_agent(
                        agent, config, prompt, card1, card2, annotator_history,
                    ),
                    timeout=JUDGE_TIMEOUT,
                )
                return config.name, result
            except TimeoutError:
                logger.warning(f"Judge {config.name} timed out after {JUDGE_TIMEOUT}s")
                return config.name, (None, None)
            except _aio.CancelledError:
                logger.warning(f"Judge {config.name} cancelled")
                return config.name, (None, None)
            except Exception as e:
                logger.warning(f"Judge {config.name} error: {e}")
                return config.name, (None, None)

        judge_results = await _aio.gather(
            *[_run_judge(c) for c in self.annotator_configs],
            return_exceptions=True,
        )

        annotations: dict[str, CardSimilarityAnnotation] = {}
        usage_by_judge: dict[str, dict] = {}
        for item in judge_results:
            if isinstance(item, Exception):
                logger.warning(f"Judge failed: {item}")
                continue
            name, (result, usage) = item
            if result:
                annotations[name] = result
            if usage:
                usage_by_judge[name] = usage

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
            usage_by_judge=usage_by_judge if usage_by_judge else None,
        )

    async def _annotate_with_agent(
        self,
        agent: Agent,
        config: AnnotatorConfig,
        prompt: str,
        card1: str,
        card2: str,
        message_history: list | None = None,
    ) -> tuple[CardSimilarityAnnotation | None, dict | None]:
        """Annotate with a single agent, with usage tracking.

        Timeout is handled by the caller via anyio cancel scope.

        Returns:
            (annotation, usage_dict) where usage_dict has input_tokens, output_tokens, requests.
            Returns (None, None) on failure.
        """
        # Resolve prompt version (lazy import to avoid circular dep)
        try:
            from .llm_annotator import SIMILARITY_PROMPT_VERSION
        except ImportError:
            SIMILARITY_PROMPT_VERSION = None

        try:
            result = (
                await agent.run(prompt, message_history=message_history)
                if message_history
                else await agent.run(prompt)
            )
            if result.output:
                ann = result.output
                # Provenance fingerprint
                ann.annotator_id = config.name
                ann.model_name = config.model
                ann.model_params = {
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                }
                ann.timestamp = datetime.utcnow().isoformat() + "Z"
                ann.prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
                if SIMILARITY_PROMPT_VERSION:
                    ann.prompt_version = SIMILARITY_PROMPT_VERSION
                # Extract usage -- result.usage() is a method in pydantic-ai >= 1.x
                usage = None
                try:
                    u = result.usage()
                    usage = {
                        "input_tokens": getattr(u, "input_tokens", 0),
                        "output_tokens": getattr(u, "output_tokens", 0),
                        "cache_write_tokens": getattr(u, "cache_write_tokens", 0),
                        "cache_read_tokens": getattr(u, "cache_read_tokens", 0),
                        "requests": getattr(u, "requests", 0),
                    }
                except Exception:
                    pass
                return ann, usage
        except Exception as e:
            logger.warning(f"Annotator {config.name} failed: {e}")
        return None, None

    def _compute_iaa(self, annotations: dict[str, CardSimilarityAnnotation]) -> dict[str, Any]:
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

        # Discretize scores into 3 wide bins that match the prompt's calibration scale:
        #   low (<0.35): unrelated to weak connections
        #   mid (0.35-0.65): moderate similarity (same function or co-occurrence)
        #   high (>0.65): strong similarity to substitutes
        # Wider bins tolerate ~0.15 inter-judge spread without crossing boundaries.
        score_bins = []
        for score in scores:
            if score < 0.35:
                score_bins.append("low")
            elif score < 0.65:
                score_bins.append("mid")
            else:
                score_bins.append("high")

        # Compute Krippendorff's Alpha for each dimension
        # Format: [[annotator1_rating], [annotator2_rating], ...] for one pair
        score_alpha = krippendorff_alpha([[b] for b in score_bins], level_of_measurement="ordinal")
        type_alpha = krippendorff_alpha([[t] for t in types], level_of_measurement="nominal")
        sub_alpha = krippendorff_alpha(
            [[str(s)] for s in substitutes], level_of_measurement="nominal"
        )

        # Overall alpha (weighted average)
        overall_alpha = score_alpha * 0.5 + type_alpha * 0.3 + sub_alpha * 0.2

        # Agreement rates
        score_agreement = (
            sum(1 for s in score_bins if score_bins.count(s) > 1) / len(score_bins)
            if score_bins
            else 0.0
        )
        type_agreement = sum(1 for t in types if types.count(t) > 1) / len(types) if types else 0.0
        sub_agreement = (
            sum(1 for s in substitutes if substitutes.count(s) > 1) / len(substitutes)
            if substitutes
            else 0.0
        )

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
            "score_std": float(
                sum((s - sum(scores) / len(scores)) ** 2 for s in scores) / len(scores)
            )
            ** 0.5
            if scores
            else 0.0,
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
        consensus_reasoning = f"Consensus from {len(annotations)} annotators (IAA alpha={iaa_metrics['krippendorff_alpha']:.2f}). "
        consensus_reasoning += " | ".join(
            f"{name}: {r[:100]}" for name, r in zip(annotations.keys(), reasonings, strict=True)
        )

        # Use first annotation as template
        first_ann = next(iter(annotations.values()))

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
            f"Filtered {len(results)} results: {len(accepted)} accepted (alpha>={min_alpha}), "
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
                    logger.info(
                        f"Updated weight for {name}: {old_weight:.3f} -> {self.annotator_weights[name]:.3f}"
                    )
