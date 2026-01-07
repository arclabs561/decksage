#!/usr/bin/env python3
"""
LLM-Powered Annotation System

Creates RICH ANNOTATIONS at scale:
1. Card similarity judgments (ground truth for evaluation)
2. Archetype descriptions (semantic understanding)
3. Card relationships (why cards appear together)
4. Substitution recommendations (functional equivalents)
5. Deck quality assessments (tournament viability)

Uses LLM judges to create training/eval data, not just validate.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


# Auto-load .env for provider keys with minimal config
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

try:
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent, ModelRetry

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    print("Install pydantic-ai: pip install pydantic-ai")

from ..utils.paths import PATHS


# Graph enrichment imports
try:
    from .cluster_based_pair_selection import (
        cluster_cards_with_evoc,
        select_mixed_pairs_from_clusters,
    )
    from .graph_enricher import enrich_annotation_with_graph
    from .lazy_graph_enricher import LazyGraphEnricher
    from .meta_judge import inject_context_into_annotator, meta_judge_annotations
    from .multi_annotator_iaa import DEFAULT_ANNOTATORS, MultiAnnotatorIAA
    from .uncertainty_based_selection import UncertaintyBasedSelector

    HAS_ENRICHMENT = True
except ImportError:
    HAS_ENRICHMENT = False
    LazyGraphEnricher = None  # type: ignore
    enrich_annotation_with_graph = None  # type: ignore
    cluster_cards_with_evoc = None  # type: ignore
    select_mixed_pairs_from_clusters = None  # type: ignore
    meta_judge_annotations = None  # type: ignore
    inject_context_into_annotator = None  # type: ignore
    MultiAnnotatorIAA = None  # type: ignore
    DEFAULT_ANNOTATORS = None  # type: ignore
    UncertaintyBasedSelector = None  # type: ignore

# ============================================================================
# Annotation Models
# ============================================================================


class CardSimilarityAnnotation(BaseModel):
    """LLM judgment of card similarity."""

    card1: str
    card2: str
    similarity_score: float = Field(ge=0.0, le=1.0, description="How similar? 0-1")
    similarity_type: str = Field(description="functional|synergy|manabase|archetype|unrelated")
    reasoning: str = Field(description="Why this score?")
    thinking: str | None = Field(
        default=None,
        description="Explicit step-by-step thinking process showing how you arrived at this score. Include: function analysis, attribute comparison, graph evidence interpretation, score calibration reasoning, and self-validation checks.",
    )
    is_substitute: bool = Field(description="Can card2 replace card1?")
    context_dependent: bool = Field(description="Only similar in specific decks?")
    example_decks: list[str] = Field(default_factory=list, description="Where they work together")

    # Metadata tracking
    model_name: str | None = Field(
        default=None,
        description="LLM model used (e.g., 'anthropic/claude-4.5-sonnet')",
    )
    model_params: dict[str, Any] | None = Field(
        default=None, description="Model parameters (temperature, max_tokens, etc.)"
    )
    prompt_hash: str | None = Field(default=None, description="Hash of prompt template used")
    annotator_id: str | None = Field(
        default=None, description="Annotator/judge ID for multi-judge systems"
    )
    timestamp: str | None = Field(default=None, description="ISO timestamp of annotation")
    game: str | None = Field(default=None, description="Game (magic, pokemon, yugioh, etc.)")
    source: str = Field(default="llm", description="Annotation source")


# ============================================================================
# Annotation Agents
# ============================================================================

if HAS_PYDANTIC_AI:
    from ..utils.pydantic_ai_helpers import make_agent

    # Env-configurable models (bias toward higher quality defaults)
    # Latest model (January 2026): Gemini 3 Flash - best balance of speed/quality/cost
    SIM_MODEL = os.getenv("ANNOTATOR_MODEL_SIMILARITY", "google/gemini-3-flash-preview")

    # Enhanced SIMILARITY_PROMPT with CoT and score diversity
    SIMILARITY_PROMPT_BASE = """You are an expert TCG judge creating similarity annotations.

**CRITICAL: Score Diversity**
You MUST use the FULL 0.0-1.0 range. Do NOT cluster scores around 0.5 or default to low values.
- Use 0.0-0.19 for truly unrelated cards
- Use 0.2-0.39 for weak connections
- Use 0.4-0.59 for moderate similarity (most cards will be here)
- Use 0.6-0.79 for strong similarity
- Use 0.8-1.0 for near-identical substitutes

**Let's think step by step:**

1. **Function Analysis**: What does each card do? Same function = higher score
2. **Attribute Comparison**: Compare mana cost, type, power/toughness, keywords
3. **Graph Evidence**: Consider Jaccard similarity and co-occurrence patterns
4. **Archetype Context**: Do they fit the same archetypes?
5. **Score Calibration**: Map your analysis to the 0.0-1.0 scale
6. **Self-Validation**: Does the score match the reasoning?
7. **Final Check**: Is this score diverse from recent annotations?

**Baseline Rules (MANDATORY - NOT SUGGESTIONS):**
These are REQUIREMENTS based on empirical evidence. You MUST follow them:

- **Graph Evidence Rules (STRICT MINIMUMS):**
  - Jaccard similarity > 0.3 → similarity score MUST be >= 0.6 (enforced minimum, can be higher if function/attributes support it)
  - Jaccard similarity > 0.1 → similarity score MUST be >= 0.3 (enforced minimum, can be higher if function/attributes support it)
  - Jaccard similarity = 0.0 → similarity score can be 0.0-0.6 (no graph connection, but function/attributes can still create similarity)
  - Co-occurrence > 10 decks → similarity score MUST be >= 0.4 (enforced minimum, can be higher)
  - Co-occurrence > 0 decks → similarity score should be >= 0.2 (minimum, can be higher)

- **Attribute/Function Rules (CAN RAISE SCORES ABOVE GRAPH MINIMUM):**
  - Shared attributes (mana cost, type, keywords) → add +0.2-0.3 to graph minimum (e.g., graph 0.3 + attributes → 0.5-0.6)
  - Same function (both removal, both card draw) → add +0.2-0.4 to graph minimum (e.g., graph 0.3 + function → 0.5-0.7)
  - Same archetype → add +0.1-0.2 to graph minimum (e.g., graph 0.2 + archetype → 0.3-0.4)

**SCORING FORMULA**: Final score = max(graph_minimum, function_score, attribute_score, archetype_score)
- Graph evidence sets the FLOOR (minimum)
- Function/attributes/archetype can raise the score ABOVE the floor
- Example: Jaccard 0.05 (floor 0.1) + same function → score 0.4-0.6 (function raises it)
- Example: Jaccard 0.4 (floor 0.6) + same function → score 0.7-0.9 (both high)

**Score Distribution Target:**
- Aim for diverse scores across the full 0.0-1.0 range
- Avoid clustering at 0.5 or defaulting to low values
- Use mid-range (0.4-0.7) for moderate similarities
- Use high range (0.8-1.0) for strong functional matches

**Examples (FULL RANGE):**
- Lightning Bolt (1R, instant, 3 damage) vs Chain Lightning (1R, instant, 3 damage): 0.9 (near-identical)
- Lightning Bolt vs Shock (1R, instant, 2 damage): 0.7 (same function, weaker)
- Lightning Bolt vs Fatal Push (B, instant, removal): 0.5 (same function, different colors)
- Lightning Bolt vs Monastery Swiftspear (R, creature): 0.4 (same archetype, different function)
- Lightning Bolt vs Counterspell (UU, instant): 0.1 (different functions)

**MID-RANGE EXAMPLES (Critical for Calibration):**
- Path to Exile (W, instant, exile creature) vs Swords to Plowshares (W, instant, exile creature): 0.8 (same function, minor differences)
- Brainstorm (U, instant, draw 3) vs Ponder (U, sorcery, card selection): 0.6 (similar function, different timing)
- Counterspell (UU, instant, counter) vs Mana Leak (1U, instant, counter): 0.5 (same function, different efficiency)
- Lightning Bolt vs Lava Spike (R, instant, 3 damage to player): 0.4 (similar but different targets)

**SCORE CALIBRATION GUIDE:**
- 0.9-1.0: Near-identical substitutes (same mana, same effect, minor differences)
- 0.7-0.8: Strong functional similarity (same role, similar power level)
- 0.5-0.6: Moderate similarity (same function, different efficiency/colors)
- 0.3-0.4: Weak similarity (shared archetype or attributes, different function)
- 0.1-0.2: Minimal similarity (loose connection, different functions)
- 0.0-0.1: Unrelated (no meaningful relationship)

**CRITICAL**: Use the FULL range! Don't cluster at 0.5 or default to low values. Match the score to the actual relationship strength.

**SCORE CALIBRATION GUIDE:**
- 0.9-1.0: Near-identical substitutes (same mana, same effect, minor differences)
- 0.7-0.8: Strong functional similarity (same role, similar power level)
- 0.5-0.6: Moderate similarity (same function, different efficiency/colors)
- 0.3-0.4: Weak similarity (shared archetype or attributes, different function)
- 0.1-0.2: Minimal similarity (loose connection, different functions)
- 0.0-0.1: Unrelated (no meaningful relationship)

**CRITICAL**: Use the FULL range! Don't cluster at 0.5 or default to low values. Match the score to the actual relationship strength.

**Output Requirements:**
- Provide `thinking` field with step-by-step reasoning
- Provide `reasoning` field with summary explanation
- Use the FULL score range (0.0-1.0)
- Be specific about why this score was chosen

Your task: Judge how similar two cards are and explain WHY.

Similarity types:
- **functional**: Same role (both are 1-mana removal)
- **synergy**: Work well together (Thassa's Oracle + Demonic Consultation)
- **manabase**: Both require similar mana (UU vs UUU)
- **archetype**: Both fit same strategy (both are Burn cards)
- **unrelated**: No meaningful relationship

**CRITICAL: is_substitute Flag**
You MUST set is_substitute=True when cards can functionally replace each other in MOST decks (not just specific contexts).
Decision criteria for is_substitute=True:
1. **Same primary function**: Both serve the same role (removal, card draw, counter, etc.)
2. **Similar power level**: Comparable effectiveness (not strict upgrade/downgrade)
3. **Broad applicability**: Works in same archetypes/formats, not deck-specific
4. **Similarity score >= 0.7**: High functional similarity is required

Examples of GOOD substitutions (is_substitute=True):
- Lightning Bolt ↔ Chain Lightning (both 1-mana red burn, same role)
- Path to Exile ↔ Swords to Plowshares (both white creature removal)
- Brainstorm ↔ Ponder (both blue card selection, similar power)

Examples of NOT substitutions (is_substitute=False):
- Lightning Bolt ↔ Monastery Swiftspear (different functions: burn vs creature)
- Brainstorm ↔ Force of Will (different functions: card selection vs counter)

**Rule**: If similarity_score >= 0.7 AND similarity_type == "functional", you MUST set is_substitute=True unless there's a clear reason they can't replace each other.
Be precise and justify your score. Default to is_substitute=True when in doubt for functional similarities."""

    def get_similarity_prompt(game: str | None = None) -> str:
        """Get similarity prompt with game-specific context."""
        game_context = ""
        if game:
            game_lower = game.lower()
            if game_lower in ["yugioh", "ygo"]:
                game_context = """
**GAME CONTEXT: Yu-Gi-Oh! Trading Card Game**
- Use Yu-Gi-Oh! terminology: "Monster", "Spell", "Trap", "ATK", "DEF", "Level", "Attribute", "Type"
- Consider: Monster Types (Dragon, Warrior, Spellcaster, etc.), Attributes (DARK, LIGHT, etc.), Levels/Ranks
- Archetypes: Blue-Eyes, Dark Magician, HERO, etc.
- DO NOT use Magic: The Gathering terminology (mana, instant, sorcery, etc.)
"""
            elif game_lower in ["pokemon", "pkm"]:
                game_context = """
**GAME CONTEXT: Pokémon Trading Card Game**
- Use Pokémon TCG terminology: "Pokémon", "Energy", "Trainer", "HP", "Type", "Weakness", "Resistance"
- Consider: Pokémon Types (Fire, Water, Grass, etc.), Evolution lines, Abilities
- DO NOT use Magic: The Gathering terminology
"""
            elif game_lower in ["magic", "mtg"]:
                game_context = """
**GAME CONTEXT: Magic: The Gathering**
- Use Magic terminology: "mana", "instant", "sorcery", "creature", "power", "toughness", "CMC"
- Consider: Colors (WUBRG), card types, mana costs, keywords

**CRITICAL: Score Calibration for Magic**
- **KEY INSIGHT**: Graph evidence sets MINIMUM scores, function/attributes can raise scores higher
- Example: Two red burn spells with Jaccard 0.05 (floor 0.1) + same function → score 0.4-0.6 (function raises above floor)
- Example: Two blue counterspells with Jaccard 0.08 (floor 0.1) + same function → score 0.4-0.5 (function raises above floor)
- Example: Lightning Bolt vs Shock: Jaccard 0.15 (floor 0.3) + same function + similar attributes → score 0.6-0.8
- **SCORING RULES**:
  - If Jaccard < 0.1: Floor is 0.1, but same function can raise to 0.4-0.6, same function + attributes can raise to 0.5-0.7
  - If Jaccard 0.1-0.3: Floor is 0.3, same function can raise to 0.5-0.7
  - If Jaccard > 0.3: Floor is 0.6, same function can raise to 0.7-0.9
- Don't default to very low scores (0.0-0.2) just because graph evidence is weak - use function/attributes!
"""

        return SIMILARITY_PROMPT_BASE + (game_context if game_context else "")

    # Create default similarity agent (will be customized per game in LLMAnnotator)
    similarity_agent = make_agent(
        SIM_MODEL,
        CardSimilarityAnnotation,
        SIMILARITY_PROMPT_BASE,  # Default prompt (no game context)
    )
    # Note: temperature and max_tokens would need to be set via ModelSettings
    # if pydantic-ai supports it, but make_agent doesn't accept these directly

    # Add output validator (non-blocking - only logs warnings, doesn't retry)
    # CRITICAL: Validator MUST return the output, not None!
    @similarity_agent.output_validator
    def validate_annotation(output: CardSimilarityAnnotation) -> CardSimilarityAnnotation:
        """Validate annotation for contradictions (non-blocking warnings only)."""
        # Log warnings but don't retry (to avoid exhausting retries)
        if output.similarity_score < 0.3:
            # Check if reasoning suggests higher similarity
            reasoning_lower = output.reasoning.lower()
            if any(
                kw in reasoning_lower
                for kw in ["same function", "same role", "substitute", "interchangeable"]
            ):
                # Log warning but don't retry - let it through
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Potential contradiction: Reasoning suggests high similarity but score is low "
                    f"({output.similarity_score:.2f}) for {output.card1} vs {output.card2}"
                )

        # Check for shared archetype but very low score
        if output.similarity_score < 0.2 and "archetype" in output.reasoning.lower():
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Potential contradiction: Reasoning mentions shared archetype but score is very low "
                f"({output.similarity_score:.2f}) for {output.card1} vs {output.card2}"
            )

        # CRITICAL: Must return the output!
        return output


# ============================================================================
# Annotation Pipeline
# ============================================================================


class LLMAnnotator:
    """Orchestrates LLM-powered annotation at scale."""

    def __init__(
        self,
        output_dir: Path | None = None,
        game: str | None = None,
        use_graph_enrichment: bool = True,
        use_evoc_clustering: bool = True,
        use_meta_judge: bool = True,
        use_multi_annotator: bool = False,
        use_uncertainty_selection: bool = False,
        use_human_queue: bool = False,
    ):
        if not HAS_PYDANTIC_AI:
            raise ImportError("pydantic-ai required")
        self.output_dir = output_dir or PATHS.experiments / "annotations_llm"
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.game = game
        self.decks = self._load_decks()
        print(f"Loaded {len(self.decks)} decks for annotation")

        # Graph enrichment setup
        self.use_graph_enrichment = use_graph_enrichment and HAS_ENRICHMENT
        self.use_evoc_clustering = use_evoc_clustering and HAS_ENRICHMENT
        self.use_meta_judge = use_meta_judge and HAS_ENRICHMENT
        self.use_multi_annotator = use_multi_annotator and HAS_ENRICHMENT
        self.use_uncertainty_selection = use_uncertainty_selection and HAS_ENRICHMENT
        self.use_human_queue = use_human_queue

        self.graph_enricher: LazyGraphEnricher | None = None
        if self.use_graph_enrichment and LazyGraphEnricher:
            try:
                graph_db = PATHS.incremental_graph_db
                if graph_db.exists():
                    self.graph_enricher = LazyGraphEnricher(graph_db, game=game)
                    print(f"  Graph enrichment enabled (DB: {graph_db})")
                else:
                    print(f"  Warning: Graph DB not found at {graph_db}, disabling enrichment")
                    self.use_graph_enrichment = False
            except Exception as e:
                print(f"  Warning: Failed to initialize graph enricher: {e}")
                self.use_graph_enrichment = False

        # Card embeddings for EVōC clustering (lazy load)
        self.card_embeddings: dict[str, Any] | None = None
        if self.use_evoc_clustering:
            print("  EVōC clustering enabled (will load embeddings on demand)")

        # Uncertainty-based selection (hard mining)
        self.uncertainty_selector: UncertaintyBasedSelector | None = None
        if self.use_uncertainty_selection and UncertaintyBasedSelector:
            try:
                self.uncertainty_selector = UncertaintyBasedSelector(
                    graph_enricher=self.graph_enricher,
                    embedding_models=None,  # Can be added later if needed
                )
                print("  Uncertainty-based selection enabled (hard mining)")
            except Exception as e:
                print(f"  Warning: Failed to initialize uncertainty selector: {e}")
                self.use_uncertainty_selection = False

        # Multi-annotator IAA system
        self.multi_annotator: MultiAnnotatorIAA | None = None
        if self.use_multi_annotator and MultiAnnotatorIAA:
            try:
                self.multi_annotator = MultiAnnotatorIAA(
                    annotator_configs=None,  # Use defaults (3 diverse models)
                    min_iaa_threshold=0.6,  # Research-based: 0.6+ is substantial agreement
                    use_consensus=True,
                )
                print("  Multi-annotator IAA enabled (3 models, consensus building)")
            except Exception as e:
                print(f"  Warning: Failed to initialize multi-annotator: {e}")
                self.use_multi_annotator = False

    def _load_decks(self) -> list[dict]:
        """Load decks with metadata, filtered by game if specified."""
        candidates: list[Path] = [
            PATHS.decks_with_metadata,
            PATHS.decks_all_final,
            PATHS.decks_all_enhanced,
            PATHS.decks_all_unified,
            PATHS.backend / "decks_hetero.jsonl",
        ]

        decks: list[dict] = []
        src_path: Path | None = None

        for p in candidates:
            if p.exists():
                src_path = p
                break

        if src_path is None:
            # Try any .jsonl file in data/processed/ as last resort
            for jsonl_file in PATHS.processed.glob("*.jsonl"):
                if "deck" in jsonl_file.name.lower():
                    src_path = jsonl_file
                    print(f"Warning: Using fallback deck file: {src_path}")
                    break

        if src_path is None:
            raise FileNotFoundError(
                f"No deck metadata found. Checked: {[str(p) for p in candidates]}. "
                f"Also checked: {list(PATHS.processed.glob('*.jsonl'))}"
            )

        with open(src_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Filter by game if specified
                if self.game and self.game.lower() != "all":
                    deck_game = d.get("game", "").lower()
                    if deck_game and deck_game != self.game.lower():
                        continue

                # Normalize cards
                if "cards" not in d or not isinstance(d.get("cards"), list):
                    cards: list[str] = []
                    parts = d.get("partitions") or d.get("Partitions")
                    if isinstance(parts, list):
                        for part in parts:
                            cs = part.get("cards") or part.get("Cards")
                            if isinstance(cs, list):
                                for c in cs:
                                    name = c.get("name") or c.get("Name")
                                    if isinstance(name, str):
                                        cards.append(name)
                    if cards:
                        d["cards"] = cards

                # Normalize archetype
                if "archetype" not in d or not isinstance(d.get("archetype"), str):
                    t = d.get("type") or d.get("Type")
                    inner = t.get("inner") if isinstance(t, dict) else None
                    if isinstance(inner, dict):
                        arch = inner.get("archetype") or inner.get("Archetype")
                        if isinstance(arch, str):
                            d["archetype"] = arch

                decks.append(d)

        return decks

    async def annotate_similarity_pairs(
        self,
        num_pairs: int = 100,
        strategy: str = "diverse",
        batch_size: int = 10,
    ) -> list[CardSimilarityAnnotation]:
        """Create similarity annotations for card pairs.

        Args:
            num_pairs: How many pairs to annotate
            strategy: "diverse" (wide coverage) or "focused" (specific archetype)
            batch_size: Number of pairs to process in parallel
        """
        print(f"\nAnnotating {num_pairs} similarity pairs ({strategy} strategy)...")

        # Select pairs to annotate
        if strategy == "diverse":
            pairs = self._select_diverse_pairs(num_pairs)
        elif strategy == "uncertainty":
            # Use uncertainty-based selection (hard mining)
            if self.use_uncertainty_selection and self.uncertainty_selector:
                # Get candidate pairs (more than needed for selection)
                candidate_pairs = self._select_diverse_pairs(num_pairs * 3)  # Get more candidates
                uncertain_pairs = self.uncertainty_selector.select_uncertain_pairs(
                    [(c1, c2) for c1, c2, _ in candidate_pairs],
                    top_k=num_pairs,
                    min_uncertainty=0.3,
                )
                # Convert back to (card1, card2, context) format
                pair_dict = {(c1, c2): ctx for c1, c2, ctx in candidate_pairs}
                pairs = [
                    (u.card1, u.card2, pair_dict.get((u.card1, u.card2), {}))
                    for u in uncertain_pairs
                ]
                print(f"  Selected {len(pairs)} uncertain pairs for annotation")
            else:
                # Fallback to diverse if uncertainty selection not available
                pairs = self._select_diverse_pairs(num_pairs)
        else:
            pairs = self._select_focused_pairs(num_pairs)

        annotations = []
        semaphore = asyncio.Semaphore(batch_size)

        async def annotate_pair(
            card1: str, card2: str, context: dict
        ) -> CardSimilarityAnnotation | None:
            async with semaphore:
                try:
                    # Use multi-annotator mode if enabled (IAA + consensus)
                    ann: CardSimilarityAnnotation | None = None
                    if self.use_multi_annotator and self.multi_annotator:
                        try:
                            # Get graph context for multi-annotator
                            graph_context = ""
                            if self.graph_enricher:
                                try:
                                    graph_features = await asyncio.wait_for(
                                        asyncio.to_thread(
                                            self.graph_enricher.extract_graph_features, card1, card2
                                        ),
                                        timeout=5.0,
                                    )
                                    if graph_features:
                                        jaccard = (
                                            graph_features.get("jaccard_similarity", 0.0)
                                            if isinstance(graph_features, dict)
                                            else getattr(graph_features, "jaccard_similarity", 0.0)
                                        )
                                        cooccur = (
                                            graph_features.get("cooccurrence_count", 0)
                                            if isinstance(graph_features, dict)
                                            else getattr(graph_features, "cooccurrence_count", 0)
                                        )
                                        graph_context = (
                                            f"Graph: Jaccard={jaccard:.3f}, Co-occurrence={cooccur}"
                                        )
                                except Exception:
                                    pass

                            # Annotate with multiple models and get consensus
                            multi_result = await self.multi_annotator.annotate_pair_multi(
                                card1=card1,
                                card2=card2,
                                graph_context=graph_context,
                            )

                            # Use consensus annotation if available, otherwise use first annotation
                            if multi_result.consensus_annotation:
                                ann = multi_result.consensus_annotation
                            elif multi_result.annotations:
                                ann = list(multi_result.annotations.values())[0]
                            else:
                                return None

                            # Add IAA metadata
                            ann = ann.model_copy(
                                update={
                                    "card1": card1,
                                    "card2": card2,
                                    "timestamp": datetime.now().isoformat(),
                                    "game": self.game or "unknown",
                                    "source": "llm_multi_annotator",
                                }
                            )

                            # Store IAA metrics in annotation metadata (if we add a metadata field)
                            # For now, log IAA metrics
                            if multi_result.iaa_metrics.get("krippendorff_alpha", 0.0) < 0.6:
                                print(
                                    f"  Low IAA (α={multi_result.iaa_metrics.get('krippendorff_alpha', 0.0):.2f}) for {card1} vs {card2}"
                                )

                            # Skip single annotator path, go directly to enrichment
                        except Exception as e:
                            print(
                                f"  Multi-annotator failed for {card1} vs {card2}: {e}, falling back to single annotator"
                            )
                            ann = None  # Force single annotator path

                    # Single annotator mode (default or fallback)
                    if ann is None:
                        # Get graph context if available (non-blocking)
                        graph_context = ""
                        if self.graph_enricher:
                            try:
                                # Get graph features asynchronously (with timeout)
                                graph_features = await asyncio.wait_for(
                                    asyncio.to_thread(
                                        self.graph_enricher.extract_graph_features, card1, card2
                                    ),
                                    timeout=5.0,  # 5 second timeout
                                )
                                if graph_features:
                                    jaccard = (
                                        graph_features.get("jaccard_similarity", 0.0)
                                        if isinstance(graph_features, dict)
                                        else getattr(graph_features, "jaccard_similarity", 0.0)
                                    )
                                    cooccur = (
                                        graph_features.get("cooccurrence_count", 0)
                                        if isinstance(graph_features, dict)
                                        else getattr(graph_features, "cooccurrence_count", 0)
                                    )
                                    distance = (
                                        graph_features.get("graph_distance")
                                        if isinstance(graph_features, dict)
                                        else getattr(graph_features, "graph_distance", None)
                                    )

                                    # Dynamic score anchors based on graph evidence (CRITICAL for calibration)
                                    # These are MINIMUM requirements - function/attributes can raise scores higher
                                    score_anchor = ""
                                    if jaccard > 0.3:
                                        score_anchor = f"**GRAPH EVIDENCE ANCHOR**: Jaccard {jaccard:.3f} > 0.3 → similarity score MUST be >= 0.6 (strong graph evidence = strong similarity). If they also share function/attributes, score can be 0.7-0.9."
                                    elif jaccard > 0.1:
                                        score_anchor = f"**GRAPH EVIDENCE ANCHOR**: Jaccard {jaccard:.3f} > 0.1 → similarity score MUST be >= 0.3 (moderate graph evidence = moderate similarity). If they also share function/attributes, score can be 0.4-0.7."
                                    elif jaccard > 0.0:
                                        score_anchor = f"**GRAPH EVIDENCE ANCHOR**: Jaccard {jaccard:.3f} > 0.0 → similarity score should be >= 0.1 (weak graph evidence). However, if they share function/attributes/archetype, score can be 0.3-0.6 despite low graph evidence."
                                    else:
                                        score_anchor = f"**GRAPH EVIDENCE ANCHOR**: Jaccard {jaccard:.3f} = 0.0 → no graph connection. However, if they share function (both removal, both card draw, etc.) or attributes (same type, similar cost), similarity can still be 0.3-0.6. Only use 0.0-0.2 if they are truly unrelated in function, attributes, AND archetype."

                                    if cooccur > 10:
                                        score_anchor += f"\n**CO-OCCURRENCE ANCHOR**: {cooccur} decks co-occurrence → similarity score MUST be >= 0.4 (frequent pairing = relationship exists). This is a MINIMUM - if they also share function, score can be higher."
                                    elif cooccur > 0:
                                        score_anchor += f"\n**CO-OCCURRENCE ANCHOR**: {cooccur} decks co-occurrence → similarity score should be >= 0.2 (some pairing = connection exists). If they also share function/attributes, score can be 0.3-0.6."

                                    graph_context = f"""
**Graph Evidence:**
- Jaccard similarity: {jaccard:.3f}
- Co-occurrence count: {cooccur} decks
- Graph distance: {distance if distance is not None else "disconnected"}

{score_anchor}

**SCORING LOGIC**:
1. Graph evidence provides MINIMUM score requirements (enforced)
2. Function/attributes/archetype can RAISE scores above graph minimum
3. Example: Low Jaccard (0.05) but same function (both removal) → score 0.4-0.6 (function overrides weak graph)
4. Example: High Jaccard (0.4) → score MUST be >= 0.6 (graph evidence is strong, enforces minimum)
5. Example: High Jaccard (0.4) + same function → score 0.7-0.9 (graph + function = very high)

**CRITICAL**: Graph anchors are MINIMUM requirements. Use function/attributes to determine if score should be higher than the minimum.
"""
                            except TimeoutError:
                                # Graph query timed out, continue without it
                                pass
                            except Exception:
                                # Graph enrichment failed, continue without it
                                pass

                        # Build prompt with dynamic meta-judge feedback
                        prompt_parts = [
                            f"Card 1: {card1}",
                            f"Card 2: {card2}",
                            f"Context: They co-occur in {context.get('count', 0)} decks ({context.get('archetypes', 'unknown')})",
                        ]

                        if graph_context:
                            prompt_parts.append(graph_context.strip())
                            prompt_parts.append(
                                "Use the graph evidence above to inform your judgment, but also consider function, attributes, and archetype context."
                            )

                        # Add meta-judge feedback if available (dynamic context injection)
                        if (
                            hasattr(self, "meta_judge_prompt_additions")
                            and self.meta_judge_prompt_additions
                        ):
                            prompt_parts.append("")
                            prompt_parts.append(
                                "**Meta-Judge Feedback (Apply to This Annotation):**"
                            )
                            for addition in self.meta_judge_prompt_additions[
                                -3:
                            ]:  # Last 3 additions
                                if isinstance(addition, str):
                                    prompt_parts.append(f"- {addition}")

                        prompt_parts.extend(
                            [
                                "",
                                "How similar are these cards? Can card2 substitute for card1?",
                                "Consider: function, power level, deckbuilding constraints.",
                            ]
                        )

                        prompt = "\n".join(prompt_parts)

                        # Use game-specific agent if available, otherwise default
                        agent = similarity_agent
                        if self.game:
                            # Create game-specific agent with game context in prompt
                            from .llm_annotator import get_similarity_prompt

                            game_prompt = get_similarity_prompt(self.game)
                            agent = make_agent(
                                SIM_MODEL,
                                CardSimilarityAnnotation,
                                game_prompt,
                            )

                        result = await agent.run(prompt)

                        # Check if result has output
                        if not hasattr(result, "output"):
                            print(
                                f"  Warning: Result has no 'output' attribute for {card1} vs {card2}"
                            )
                            print(f"    Result type: {type(result)}, attributes: {dir(result)}")
                            return None

                        ann = result.output

                        # Check if output is None
                        if ann is None:
                            print(f"  Warning: result.output is None for {card1} vs {card2}")
                            # Check if there's error info
                            if hasattr(result, "error"):
                                print(f"    Error: {result.error}")
                            if hasattr(result, "data"):
                                print(f"    Data: {result.data}")
                            return None

                        # Ensure we have a CardSimilarityAnnotation
                        if not isinstance(ann, CardSimilarityAnnotation):
                            print(
                                f"  Warning: Expected CardSimilarityAnnotation, got {type(ann)} for {card1} vs {card2}"
                            )
                            print(f"    Output value: {ann}")
                            return None

                        # Add metadata using model_copy
                        try:
                            ann = ann.model_copy(
                                update={
                                    "card1": card1,  # Ensure card names are set
                                    "card2": card2,
                                    "model_name": SIM_MODEL,
                                    "model_params": {"provider": "openrouter", "temperature": 0.8},
                                    "timestamp": datetime.now().isoformat(),
                                    "game": self.game or "unknown",
                                    "source": "llm",
                                }
                            )
                        except Exception as e:
                            print(
                                f"  Error updating annotation metadata for {card1} vs {card2}: {e}"
                            )
                            import traceback

                            traceback.print_exc()
                            return None

                    # At this point, ann should be set (either from multi-annotator or single annotator)
                    if ann is None:
                        return None

                    # Enrich with graph features and card attributes if available
                    if self.graph_enricher:
                        try:
                            # Get card attributes from graph DB nodes
                            node1 = await asyncio.to_thread(self.graph_enricher.get_node, card1)
                            node2 = await asyncio.to_thread(self.graph_enricher.get_node, card2)

                            # Build card_attributes dict from node data
                            card_attributes = {}
                            if node1 and node1.get("attributes"):
                                attrs1 = node1["attributes"]
                                if isinstance(attrs1, dict):
                                    card_attributes[card1] = attrs1
                            if node2 and node2.get("attributes"):
                                attrs2 = node2["attributes"]
                                if isinstance(attrs2, dict):
                                    card_attributes[card2] = attrs2

                            # Convert annotation to dict for enrichment
                            ann_dict = ann.model_dump() if hasattr(ann, "model_dump") else dict(ann)

                            # Enrich with graph features and card attributes
                            enriched = await asyncio.to_thread(
                                enrich_annotation_with_graph,
                                ann_dict,
                                graph=None,  # Use lazy enricher instead
                                card_attributes=card_attributes if card_attributes else None,
                                game=self.game,
                            )

                            # Add graph features from lazy enricher (if not already added)
                            if "graph_features" not in enriched or not enriched.get(
                                "graph_features"
                            ):
                                graph_features = await asyncio.to_thread(
                                    self.graph_enricher.extract_graph_features, card1, card2
                                )
                                if graph_features:
                                    # Convert GraphFeatures to dict for JSON serialization
                                    if hasattr(graph_features, "model_dump"):
                                        enriched["graph_features"] = graph_features.model_dump()
                                    elif hasattr(graph_features, "__dict__"):
                                        enriched["graph_features"] = graph_features.__dict__
                                    else:
                                        enriched["graph_features"] = dict(graph_features)

                            # Return enriched dict (caller will handle serialization)
                            return enriched
                        except Exception as e:
                            # Graph enrichment failed, return original annotation
                            print(f"  Warning: Graph enrichment failed for {card1} vs {card2}: {e}")
                            import traceback

                            traceback.print_exc()
                            return ann

                    return ann
                except Exception as e:
                    print(f"  Error on {card1} vs {card2}: {e}")
                    import traceback

                    traceback.print_exc()
                    return None

        # Process in batches
        for i in range(0, len(pairs), batch_size):
            batch = pairs[i : i + batch_size]
            batch_results = await asyncio.gather(
                *[annotate_pair(card1, card2, ctx) for card1, card2, ctx in batch],
                return_exceptions=True,
            )
            for result in batch_results:
                if isinstance(result, Exception):
                    print(f"  Error: {result}")
                elif result is not None:
                    annotations.append(result)
            if len(annotations) % 10 == 0 and len(annotations) > 0:
                print(f"  {len(annotations)}/{num_pairs} annotations generated...")

        # Meta-judge annotations if enabled
        if self.use_meta_judge and meta_judge_annotations and len(annotations) > 0:
            try:
                print(f"\n  Running meta-judge on {len(annotations)} annotations...")
                # Convert to dict format for meta-judge
                ann_dicts = []
                for ann in annotations:
                    if isinstance(ann, dict):
                        ann_dicts.append(ann)
                    elif hasattr(ann, "model_dump"):
                        ann_dicts.append(ann.model_dump())
                    else:
                        ann_dicts.append(dict(ann))

                judgment = await meta_judge_annotations(
                    ann_dicts,
                    game=self.game,
                    batch_id=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                )

                print(f"  Meta-judge quality score: {judgment.overall_quality:.2f}/1.0")
                if judgment.issues:
                    print(f"  Issues found: {len(judgment.issues)}")
                    for issue in judgment.issues[:3]:  # Show first 3
                        # Handle both dict and Pydantic model
                        if isinstance(issue, dict):
                            severity = issue.get("severity", "unknown")
                            desc = issue.get("description", "")
                        else:
                            severity = getattr(issue, "severity", "unknown")
                            desc = getattr(issue, "description", "")
                        print(f"    - {severity}: {desc[:80] if desc else 'No description'}")

                # Inject context back into annotator
                if inject_context_into_annotator:
                    inject_context_into_annotator(judgment, self)
                    print("  Meta-judge feedback injected into annotator")
            except Exception as e:
                print(f"  Warning: Meta-judge failed: {e}")
                import traceback

                traceback.print_exc()

        return annotations

    def _select_diverse_pairs(self, n: int) -> list[tuple[str, str, dict]]:
        """Select diverse pairs across formats and archetypes."""
        # Find cards that appear in multiple archetypes (interesting)
        card_archetypes = defaultdict(set)
        card_counts = Counter()

        for deck in self.decks:
            arch = deck.get("archetype", "Unknown")
            for card in deck.get("cards", []):
                if isinstance(card, dict):
                    card_name = card.get("name", "")
                else:
                    card_name = str(card)
                if card_name:
                    card_archetypes[card_name].add(arch)
                    card_counts[card_name] += 1

        # Get cards that appear in 2-5 archetypes (not too narrow, not universal staples)
        interesting_cards = [
            card for card, archs in card_archetypes.items() if 2 <= len(archs) <= 5
        ]

        # Pair them
        import random

        random.shuffle(interesting_cards)
        pairs = []

        for i in range(0, min(n * 2, len(interesting_cards)), 2):
            if i + 1 < len(interesting_cards):
                c1, c2 = interesting_cards[i], interesting_cards[i + 1]
                common_archs = card_archetypes[c1] & card_archetypes[c2]
                pairs.append(
                    (
                        c1,
                        c2,
                        {
                            "count": min(card_counts[c1], card_counts[c2]),
                            "archetypes": ", ".join(list(common_archs)[:3])
                            if common_archs
                            else "none",
                        },
                    )
                )

        return pairs[:n]

    def _select_focused_pairs(
        self, n: int, archetype: str | None = None
    ) -> list[tuple[str, str, dict]]:
        """Select pairs from specific archetype."""
        if not archetype:
            # Pick most common archetype
            arch_counts = Counter(d.get("archetype") for d in self.decks)
            archetype = arch_counts.most_common(1)[0][0]
            print(f"  Focusing on: {archetype}")

        # Get cards from this archetype
        arch_decks = [d for d in self.decks if d.get("archetype") == archetype]
        card_counts = Counter()

        for deck in arch_decks:
            for card in deck.get("cards", []):
                if isinstance(card, dict):
                    card_name = card.get("name", "")
                else:
                    card_name = str(card)
                if card_name:
                    card_counts[card_name] += 1

        # Take top N most common cards and pair them
        common_cards = [card for card, _ in card_counts.most_common(n * 2)]
        pairs = []

        for i in range(0, min(len(common_cards), n * 2), 2):
            if i + 1 < len(common_cards):
                pairs.append(
                    (
                        common_cards[i],
                        common_cards[i + 1],
                        {"count": len(arch_decks), "archetypes": archetype},
                    )
                )

        return pairs[:n]
