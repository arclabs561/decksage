#!/usr/bin/env python3
"""
Agent Topology for Annotation System

Implements a hierarchical agent topology using pydantic-ai:
- Supervisor Agent: Orchestrates the annotation workflow
- Game Specialist Agents: Game-specific annotation logic (Magic, Pokemon, Yu-Gi-Oh)
- Quality Validator Agent: Validates annotation quality
- Meta-Judge Agent: Provides feedback and consensus
- Router Agent: Routes to appropriate specialist based on game

This topology enables:
- Specialized agents for each game (no cross-contamination)
- Hierarchical coordination (supervisor → specialists → validators)
- Agent-to-agent communication (agents can call other agents as tools)
- Game-specific context injection at the agent level
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any


try:
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent, tool

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    BaseModel = object
    Agent = None

    def tool(func):
        return func


from ..utils.pydantic_ai_helpers import get_default_model, make_agent


# Import for game-specific prompts
try:
    from .llm_annotator import SIMILARITY_PROMPT_BASE, get_similarity_prompt
except ImportError:
    get_similarity_prompt = None
    SIMILARITY_PROMPT_BASE = None

logger = logging.getLogger(__name__)

# Forward reference to avoid circular import
if HAS_PYDANTIC_AI:
    from .llm_annotator import CardSimilarityAnnotation
else:
    CardSimilarityAnnotation = None


# ============================================================================
# Agent Output Models
# ============================================================================


class AnnotationTask(BaseModel):
    """Task specification for annotation."""

    card1: str = Field(description="First card name")
    card2: str = Field(description="Second card name")
    game: str = Field(description="Game name (magic, pokemon, yugioh)")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context (graph features, etc.)"
    )


class RoutingDecision(BaseModel):
    """Decision from router agent on which specialist to use."""

    specialist: str = Field(
        description="Which specialist to use: magic, pokemon, yugioh, or generic"
    )
    reasoning: str = Field(description="Why this specialist was chosen")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in routing decision")


class ValidationResult(BaseModel):
    """Result from quality validator agent."""

    is_valid: bool = Field(description="Whether annotation passes validation")
    quality_score: float = Field(ge=0.0, le=1.0, description="Overall quality score")
    issues: list[str] = Field(default_factory=list, description="List of issues found")
    suggestions: list[str] = Field(default_factory=list, description="Suggestions for improvement")


class SupervisorDecision(BaseModel):
    """Decision from supervisor agent on next steps."""

    action: str = Field(description="Action: accept, revise, reject, or continue")
    reasoning: str = Field(description="Reasoning for the decision")
    feedback: str | None = Field(None, description="Feedback for revision if needed")


# ============================================================================
# Agent Topology
# ============================================================================


class AnnotationAgentTopology:
    """Hierarchical agent topology for annotation system."""

    def __init__(
        self,
        game: str | None = None,
        use_specialists: bool = True,
        use_validator: bool = True,
        use_supervisor: bool = True,
    ):
        """Initialize agent topology.

        Args:
            game: Default game (if None, router will decide)
            use_specialists: Use game-specific specialist agents
            use_validator: Use quality validator agent
            use_supervisor: Use supervisor agent for coordination
        """
        if not HAS_PYDANTIC_AI:
            raise ImportError("pydantic-ai required: uv add pydantic-ai")

        self.game = game
        self.use_specialists = use_specialists
        self.use_validator = use_validator
        self.use_supervisor = use_supervisor

        # Create agents
        self.router_agent = self._create_router_agent() if use_specialists else None
        self.specialist_agents: dict[str, Agent] = {}
        if use_specialists:
            self.specialist_agents = {
                "magic": self._create_magic_specialist(),
                "pokemon": self._create_pokemon_specialist(),
                "yugioh": self._create_yugioh_specialist(),
                "generic": self._create_generic_specialist(),
            }
        self.validator_agent = self._create_validator_agent() if use_validator else None
        self.supervisor_agent = self._create_supervisor_agent() if use_supervisor else None

        logger.info(
            f"Initialized agent topology (game={game}, specialists={use_specialists}, validator={use_validator}, supervisor={use_supervisor})"
        )

    def _create_router_agent(self) -> Agent[RoutingDecision]:
        """Create router agent that decides which specialist to use."""
        system_prompt = """You are a routing agent for card similarity annotations.

Your role is to analyze an annotation task and decide which specialist agent should handle it.

**Available Specialists:**
- magic: Magic: The Gathering specialist (function-based scoring, mana costs, colors)
- pokemon: Pokémon TCG specialist (type-based scoring, evolution lines)
- yugioh: Yu-Gi-Oh! specialist (archetype-based scoring, types, attributes)
- generic: Generic specialist (for unknown games or fallback)

**Routing Logic:**
- If game is explicitly "magic" or "mtg" → magic specialist
- If game is explicitly "pokemon" or "pkm" → pokemon specialist
- If game is explicitly "yugioh" or "ygo" → yugioh specialist
- If game is unknown or ambiguous → generic specialist
- Consider card names if game is ambiguous (e.g., "Lightning Bolt" suggests Magic)

**Output:**
- specialist: Which specialist to route to
- reasoning: Why this specialist was chosen
- confidence: Confidence in routing decision (0.0-1.0)
"""
        return make_agent(
            get_default_model("general"),
            RoutingDecision,
            system_prompt,
            model_settings={"temperature": 0.1, "max_tokens": 500},
        )

    def _create_magic_specialist(self) -> Agent[CardSimilarityAnnotation]:
        """Create Magic: The Gathering specialist agent."""
        _lazy_import_prompts()
        if not get_similarity_prompt:
            raise ImportError("Cannot import get_similarity_prompt")

        prompt = get_similarity_prompt("magic")
        return make_agent(
            get_default_model("annotator"),
            CardSimilarityAnnotation,
            prompt,
            model_settings={"temperature": 0.7, "max_tokens": 2000},
        )

    def _create_pokemon_specialist(self) -> Agent[CardSimilarityAnnotation]:
        """Create Pokémon TCG specialist agent."""
        _lazy_import_prompts()
        if not get_similarity_prompt:
            raise ImportError("Cannot import get_similarity_prompt")

        prompt = get_similarity_prompt("pokemon")
        return make_agent(
            get_default_model("annotator"),
            CardSimilarityAnnotation,
            prompt,
            model_settings={"temperature": 0.7, "max_tokens": 2000},
        )

    def _create_yugioh_specialist(self) -> Agent[CardSimilarityAnnotation]:
        """Create Yu-Gi-Oh! specialist agent."""
        _lazy_import_prompts()
        if not get_similarity_prompt:
            raise ImportError("Cannot import get_similarity_prompt")

        prompt = get_similarity_prompt("yugioh")
        return make_agent(
            get_default_model("annotator"),
            CardSimilarityAnnotation,
            prompt,
            model_settings={"temperature": 0.7, "max_tokens": 2000},
        )

    def _create_generic_specialist(self) -> Agent[CardSimilarityAnnotation]:
        """Create generic specialist agent (for unknown games)."""
        _lazy_import_prompts()
        if not SIMILARITY_PROMPT_BASE:
            raise ImportError("Cannot import SIMILARITY_PROMPT_BASE")

        return make_agent(
            get_default_model("annotator"),
            CardSimilarityAnnotation,
            SIMILARITY_PROMPT_BASE,
            model_settings={"temperature": 0.7, "max_tokens": 2000},
        )

    def _create_validator_agent(self) -> Agent[ValidationResult]:
        """Create quality validator agent."""
        system_prompt = """You are a quality validator for card similarity annotations.

Your role is to validate annotation quality and identify issues.

**Validation Criteria:**
1. **Score Calibration**: Does score match reasoning and evidence?
2. **Graph Evidence**: Is graph evidence (Jaccard, co-occurrence) properly considered?
3. **Reasoning Quality**: Is reasoning clear, specific, and justified?
4. **Completeness**: Are all required fields present and meaningful?
5. **Consistency**: Does annotation align with similar annotations?

**Output:**
- is_valid: Whether annotation passes validation
- quality_score: Overall quality (0.0-1.0)
- issues: List of specific issues found
- suggestions: Suggestions for improvement

Be specific and actionable in your feedback."""

        return make_agent(
            get_default_model("validator"),
            ValidationResult,
            system_prompt,
            model_settings={"temperature": 0.3, "max_tokens": 1000},
        )

    def _create_supervisor_agent(self) -> Agent[SupervisorDecision]:
        """Create supervisor agent that coordinates the workflow."""
        # Create tools for supervisor to call other agents
        topology_instance = self

        @tool
        async def validate_annotation(annotation: dict[str, Any]) -> dict[str, Any]:
            """Validate an annotation using the validator agent."""
            if not topology_instance.validator_agent:
                return {"is_valid": True, "quality_score": 0.5, "issues": [], "suggestions": []}

            result = await topology_instance.validator_agent.run(
                f"Validate this annotation: {annotation}"
            )
            return result.output.model_dump() if hasattr(result, "output") else {}

        system_prompt = """You are a supervisor agent coordinating the annotation workflow.

Your role is to:
1. Coordinate annotation tasks across specialist agents
2. Validate annotation quality
3. Make decisions on acceptance, revision, or rejection
4. Provide feedback for improvement

**Workflow:**
1. Receive annotation task
2. Route to appropriate specialist (or use default if game is known)
3. Validate annotation quality
4. Make decision: accept, revise, reject, or continue

**Decision Logic:**
- Accept: High quality (≥0.7) and valid
- Revise: Medium quality (0.4-0.7) with fixable issues
- Reject: Low quality (<0.4) or unfixable issues
- Continue: Quality improving but not yet acceptable

**Tools Available:**
- validate_annotation: Validate annotation quality

Be decisive and provide clear feedback."""

        return make_agent(
            get_default_model("judge"),
            SupervisorDecision,
            system_prompt,
            model_settings={"temperature": 0.3, "max_tokens": 1500},
            tools=[validate_annotation],
        )

    async def annotate(
        self,
        card1: str,
        card2: str,
        game: str | None = None,
        context: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> CardSimilarityAnnotation:
        """Annotate a card pair using the agent topology.

        Args:
            card1: First card name
            card2: Second card name
            game: Game name (if None, uses self.game or routes)
            context: Additional context (graph features, etc.)
            timeout: Maximum time to wait for annotation (seconds)

        Returns:
            CardSimilarityAnnotation

        Raises:
            ValueError: If annotation fails after all fallbacks
            asyncio.TimeoutError: If annotation exceeds timeout
        """
        game = game or self.game or "unknown"
        context = context or {}

        # Step 1: Route to specialist (if routing enabled) - with timeout
        specialist_name = game.lower() if game and game != "unknown" else "generic"
        if self.use_specialists and self.router_agent and (not game or game == "unknown"):
            # Route if game is unknown or not provided
            try:
                routing_result = await asyncio.wait_for(
                    self.router_agent.run(
                        f"Route this annotation task: card1={card1}, card2={card2}, game={game or 'unknown'}"
                    ),
                    timeout=self.router_timeout,
                )
                if hasattr(routing_result, "output") and routing_result.output:
                    routing = routing_result.output
                    specialist_name = routing.specialist
                    logger.info(
                        f"Router selected {specialist_name} specialist: {routing.reasoning} (confidence: {routing.confidence:.2f})"
                    )
            except TimeoutError:
                logger.warning("Router timeout, using generic specialist")
                specialist_name = "generic"
            except Exception as e:
                logger.warning(f"Router failed, using generic specialist: {e}")
                specialist_name = "generic"

        # Step 2: Get specialist agent with fallback
        specialist = self.specialist_agents.get(specialist_name)
        if not specialist:
            # Fallback to generic if specialist not found
            specialist = self.specialist_agents.get("generic")
            if not specialist:
                # Last resort: create generic on the fly
                specialist = self._create_generic_specialist()
                logger.warning(f"Specialist {specialist_name} not found, using generic")

        # Step 3: Generate annotation with error handling and timeout
        prompt_parts = [
            f"Card 1: {card1}",
            f"Card 2: {card2}",
        ]
        if context.get("graph_features"):
            graph_feat = context["graph_features"]
            if isinstance(graph_feat, dict):
                # Format graph features nicely
                jaccard = graph_feat.get("jaccard_similarity", 0.0)
                cooccur = graph_feat.get("cooccurrence_count", 0)
                distance = graph_feat.get("graph_distance")
                prompt_parts.append(
                    f"Graph evidence: Jaccard similarity = {jaccard:.3f}, Co-occurrence = {cooccur}"
                )
                if distance is not None:
                    prompt_parts.append(f"Graph distance: {distance}")
            else:
                prompt_parts.append(f"Graph features: {graph_feat}")
        if context.get("archetypes"):
            prompt_parts.append(f"Archetypes: {context.get('archetypes', 'unknown')}")

        prompt = "\n".join(prompt_parts)

        # Generate annotation with timeout
        annotation = None
        try:
            result = await asyncio.wait_for(
                specialist.run(prompt),
                timeout=timeout - 5.0,  # Reserve time for validation/supervisor
            )
            if not hasattr(result, "output") or result.output is None:
                raise ValueError(f"Specialist agent returned no output for {card1} vs {card2}")
            annotation = result.output
        except TimeoutError:
            logger.error(f"Specialist agent timeout for {card1} vs {card2}")
            # Fallback: try generic specialist if not already using it
            if specialist_name != "generic":
                logger.info("Retrying with generic specialist...")
                generic_specialist = self.specialist_agents.get("generic")
                if generic_specialist:
                    try:
                        result = await asyncio.wait_for(
                            generic_specialist.run(prompt),
                            timeout=timeout - 5.0,
                        )
                        if hasattr(result, "output") and result.output:
                            annotation = result.output
                    except Exception as e:
                        raise ValueError(
                            f"All specialists failed (timeout) for {card1} vs {card2}: {e}"
                        )
                else:
                    raise ValueError(
                        f"Specialist timeout and no generic fallback for {card1} vs {card2}"
                    )
            else:
                raise ValueError(f"Specialist agent timeout for {card1} vs {card2}")
        except Exception as e:
            logger.error(f"Specialist agent failed for {card1} vs {card2}: {e}")
            # Fallback: try generic specialist
            if specialist_name != "generic":
                logger.info("Retrying with generic specialist...")
                generic_specialist = self.specialist_agents.get("generic")
                if generic_specialist:
                    try:
                        result = await generic_specialist.run(prompt)
                        if hasattr(result, "output") and result.output:
                            annotation = result.output
                        else:
                            raise ValueError(
                                f"Generic specialist returned no output for {card1} vs {card2}"
                            )
                    except Exception as e2:
                        raise ValueError(
                            f"All specialists failed for {card1} vs {card2}: {e}, {e2}"
                        )
                else:
                    raise ValueError(
                        f"Specialist failed and no generic fallback for {card1} vs {card2}: {e}"
                    )
            else:
                raise ValueError(f"Specialist agent failed for {card1} vs {card2}: {e}")

        if annotation is None:
            raise ValueError(
                f"Failed to generate annotation for {card1} vs {card2} after all fallbacks"
            )

        # Step 4: Validate (if validator enabled) - non-blocking with timeout
        validation_result = None
        if self.use_validator and self.validator_agent:
            try:
                validation_prompt = f"""Validate this annotation:
Card 1: {card1}
Card 2: {card2}
Game: {game}
Score: {annotation.similarity_score}
Reasoning: {annotation.reasoning}
Thinking: {annotation.thinking if hasattr(annotation, "thinking") else "N/A"}
"""
                validation_result = await asyncio.wait_for(
                    self.validator_agent.run(validation_prompt),
                    timeout=self.validator_timeout,
                )
                if hasattr(validation_result, "output") and validation_result.output:
                    validation = validation_result.output
                    if not validation.is_valid and validation.issues:
                        logger.warning(
                            f"Validation issues for {card1} vs {card2}: {validation.issues}"
                        )
                        # Log quality score for monitoring
                        if validation.quality_score < 0.6:
                            logger.warning(
                                f"Low quality annotation ({validation.quality_score:.2f}) for {card1} vs {card2}"
                            )
            except TimeoutError:
                logger.warning(f"Validator timeout (non-blocking) for {card1} vs {card2}")
            except Exception as e:
                logger.warning(f"Validator failed (non-blocking): {e}")
                # Continue without validation - don't block annotation

        # Step 5: Supervisor decision (if supervisor enabled) - non-blocking with timeout
        if self.use_supervisor and self.supervisor_agent:
            try:
                # Format annotation for supervisor (compact format)
                ann_dict = (
                    annotation.model_dump()
                    if hasattr(annotation, "model_dump")
                    else (dict(annotation) if isinstance(annotation, dict) else str(annotation))
                )
                # Include validation result if available
                validation_info = ""
                if (
                    validation_result
                    and hasattr(validation_result, "output")
                    and validation_result.output
                ):
                    val = validation_result.output
                    validation_info = (
                        f"\nValidation: quality={val.quality_score:.2f}, valid={val.is_valid}"
                    )

                supervisor_prompt = f"""Coordinate annotation task:
Card 1: {card1}
Card 2: {card2}
Game: {game}
Score: {annotation.similarity_score}
Type: {annotation.similarity_type}
Reasoning: {annotation.reasoning[:200]}...{validation_info}

Make a decision: accept, revise, or reject this annotation.
"""
                supervisor_result = await asyncio.wait_for(
                    self.supervisor_agent.run(supervisor_prompt),
                    timeout=self.supervisor_timeout,
                )
                if hasattr(supervisor_result, "output") and supervisor_result.output:
                    decision = supervisor_result.output
                    if decision.action == "revise" and decision.feedback:
                        logger.info(
                            f"Supervisor suggests revision for {card1} vs {card2}: {decision.feedback}"
                        )
                        # Store feedback for potential revision (non-blocking)
                        # Could trigger revision here if needed, but for now just log
                    elif decision.action == "accept":
                        logger.debug(f"Supervisor accepted annotation for {card1} vs {card2}")
                    elif decision.action == "reject":
                        logger.warning(
                            f"Supervisor rejected annotation for {card1} vs {card2}: {decision.reasoning}"
                        )
            except TimeoutError:
                logger.warning(f"Supervisor timeout (non-blocking) for {card1} vs {card2}")
            except Exception as e:
                logger.warning(f"Supervisor failed (non-blocking): {e}")
                # Continue without supervisor - don't block annotation

        return annotation


# ============================================================================
# Factory Function
# ============================================================================


def create_annotation_topology(
    game: str | None = None,
    use_specialists: bool = True,
    use_validator: bool = True,
    use_supervisor: bool = True,
) -> AnnotationAgentTopology:
    """Create an annotation agent topology.

    Args:
        game: Default game (if None, router will decide)
        use_specialists: Use game-specific specialist agents
        use_validator: Use quality validator agent
        use_supervisor: Use supervisor agent for coordination

    Returns:
        AnnotationAgentTopology instance
    """
    return AnnotationAgentTopology(
        game=game,
        use_specialists=use_specialists,
        use_validator=use_validator,
        use_supervisor=use_supervisor,
    )
