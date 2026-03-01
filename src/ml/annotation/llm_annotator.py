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
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# Auto-load .env for provider keys with minimal config
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

try:
    import pydantic_ai  # type: ignore[import-not-found]
except ImportError:
    HAS_PYDANTIC_AI = False
    print("Install pydantic-ai: pip install pydantic-ai")
else:
    HAS_PYDANTIC_AI = True
    del pydantic_ai

from ..utils.paths import PATHS


logger = logging.getLogger(__name__)


# Graph enrichment imports
try:
    from .agentic_meta_judge import AgenticMetaJudge, AnnotationRound
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
    AgenticMetaJudge = None  # type: ignore
    AnnotationRound = None  # type: ignore
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

    # Multi-faceted similarity breakdown (richer than a single score)
    functional_score: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Functional replacement similarity (same role/effect). 0=different function, 1=identical function",
    )
    synergy_score: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Synergy/combo potential (how well they work together). 0=no synergy, 1=key combo piece",
    )
    meta_relevance: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Competitive meta relevance (co-occurrence in tournament play). 0=never paired, 1=always paired in meta decks",
    )
    key_similarities: list[str] = Field(
        default_factory=list,
        description="Concrete shared traits (e.g., 'both 1-mana instant removal', 'both draw 2 cards')",
    )
    key_differences: list[str] = Field(
        default_factory=list,
        description="Concrete differentiators (e.g., 'Bolt hits face, Path only hits creatures')",
    )

    # Provenance fingerprint
    model_name: str | None = Field(
        default=None,
        description="Full model ID on provider (e.g., 'anthropic/claude-sonnet-4-6')",
    )
    model_params: dict[str, Any] | None = Field(
        default=None, description="Model parameters (temperature, max_tokens, etc.)"
    )
    prompt_version: str | None = Field(
        default=None,
        description="Semantic version of the prompt template (e.g., 'v3.1')",
    )
    prompt_hash: str | None = Field(default=None, description="SHA-256 prefix of full prompt text sent")
    annotator_id: str | None = Field(
        default=None, description="Annotator/judge ID for multi-judge systems"
    )
    timestamp: str | None = Field(default=None, description="ISO timestamp of annotation")
    game: str | None = Field(default=None, description="Game (magic, pokemon, yugioh, etc.)")
    source: str = Field(default="llm", description="Annotation source")


class ArchetypeDescription(BaseModel):
    """LLM description of an archetype label."""

    archetype_name: str = Field(description="Archetype name/label")
    description: str = Field(description="Short archetype description (2-4 sentences)")
    example_cards: list[str] = Field(default_factory=list, description="Representative cards")
    game: str | None = Field(default=None, description="Game (magic, pokemon, yugioh)")
    format: str | None = Field(default=None, description="Format context, if known")


# ============================================================================
# Annotation Agents
# ============================================================================

archetype_description_agent = None

if HAS_PYDANTIC_AI:
    from ..utils.pydantic_ai_helpers import make_agent

    # Env-configurable models (bias toward higher quality defaults)
    # Latest model (January 2026): Gemini 3 Flash - best balance of speed/quality/cost
    SIM_MODEL = os.getenv("ANNOTATOR_MODEL_SIMILARITY", "google/gemini-3-flash-preview")

    # Prompt version -- bump on any semantic change to scoring rules or output schema
    SIMILARITY_PROMPT_VERSION = "v5.0"

    # Enhanced SIMILARITY_PROMPT with CoT and score diversity
    SIMILARITY_PROMPT_BASE = """You are an expert TCG judge creating similarity annotations.

**SCORING SCALE (0.0 to 1.0):**
- 0.0-0.10: Unrelated. Different functions, different archetypes, no strategic connection. Sharing a card type (both are spells, both are traps) is NOT enough for >0.10.
- 0.11-0.20: Tangential. Same broad category (both are removal) but different targets, timing, cost tier, or game-state role. No competitive player would consider one when building around the other.
- 0.21-0.35: Weak connection. Same function but different efficiency tier, OR same archetype but different roles within it. A player building a deck might consider both but for different slots.
- 0.36-0.55: Moderate similarity. Same function AND similar cost/efficiency, OR strong co-occurrence in competitive decks. Would appear on the same shortlist during deckbuilding.
- 0.56-0.75: Strong similarity. Same function, similar attributes, competitive alternatives. A player choosing between them would weigh specific meta tradeoffs.
- 0.76-0.90: Near-substitute. Functionally interchangeable in most contexts, minor differences (cost, drawback, format legality).
- 0.91-1.0: Functional reprint or strictly-better/worse pair.

**CALIBRATION ANCHOR: Most random card pairs score 0.05-0.15.** Two cards sharing only a card type or broad mechanic category without specific functional overlap should score below 0.15. Reserve 0.20+ for pairs where a deckbuilder would plausibly consider both cards for a related purpose.

**Step-by-step analysis:**
1. **Function**: What does each card do? Same specific function = higher score.
2. **Attributes**: Compare cost, type, stats, keywords.
3. **Graph Evidence**: Use the co-occurrence data provided (if any). High deck overlap confirms competitive relevance.
4. **Archetype**: Same archetype? Different archetypes with overlapping function?
5. **Score**: Map analysis to the scale above. Anchor to the calibration examples below.

**SCORING RULES:**
1. **Graph evidence sets a floor** (when co-occurrence data is provided):
   - Jaccard > 0.3 → floor 0.60
   - Jaccard > 0.1 → floor 0.30
   - Co-occurrence > 10 decks → floor 0.40
   - Low/no co-occurrence → floor 0.0
2. **Function raises above floor**: Same function → +0.25-0.40 above floor
3. **Shared type alone is NOT similarity**: "Both are trap cards" or "both are monsters" → 0.05-0.10

**CALIBRATION EXAMPLES (use these as anchors):**
- Lightning Bolt vs Shock: 0.70 (same function, same cost, 3 vs 2 damage)
- Path to Exile vs Swords to Plowshares: 0.80 (same function, near-identical effect)
- Counterspell vs Mana Leak: 0.50 (same function, different late-game)
- Lightning Bolt vs Counterspell: 0.10 (both instants, completely different functions)
- Sol Ring vs Wrath of God: 0.05 (unrelated -- different function, type, role)
- Dark Magician vs Blue-Eyes White Dragon: 0.15 (both vanilla beaters, different archetypes)

**Output Requirements:**
- Provide `thinking` field with step-by-step reasoning
- Provide `reasoning` field with summary explanation
- Use the FULL score range (0.0-1.0)
- Be specific about why this score was chosen
- Provide `functional_score` (0-1): how interchangeable are they as functional replacements?
- Provide `synergy_score` (0-1): how well do they work together in a deck?
- Provide `meta_relevance` (0-1): how often do they co-occur in competitive/tournament decks? 0=never paired, 1=always paired
- Provide `key_similarities`: 2-4 concrete shared traits (e.g., "both 1-mana instant removal")
- Provide `key_differences`: 1-3 concrete differentiators (e.g., "Bolt hits face, Path only hits creatures")

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

    # Export SIMILARITY_PROMPT_BASE as SIMILARITY_PROMPT for backward compatibility
    SIMILARITY_PROMPT = SIMILARITY_PROMPT_BASE

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
- Extra Deck mechanics: Fusion, Synchro, Xyz, Link summoning
- DO NOT use Magic: The Gathering terminology (mana, instant, sorcery, etc.)
- Yu-Gi-Oh! has NO mana system. Do not score manabase similarity.

**ARCHETYPE ISOLATION (Critical)**
- Archetype membership is defined by name substrings (e.g., "Snake-Eye" cards reference "Snake-Eye" in their text)
- An archetype-specific card (text says "target one Snake-Eye card") is NOT similar to a generic card with the same effect
- Two searchers from different archetypes are NOT interchangeable even if both "add a monster from deck to hand"
- Same archetype cards → score 0.5-0.8 depending on functional overlap
- Cross-archetype cards with same effect → score 0.2-0.4 unless both are generic

**CARD CATEGORY TAXONOMY (Use This for Scoring)**
1. **Standalone generics**: usable in ANY deck (Ash Blossom, Infinite Impermanence, staple spells) → compare freely across decks
2. **Engine cards**: only function within their archetype package → only similar to cards in same engine
3. **Splashable engines**: small self-contained packages added to unrelated decks → similar to other splashable engines of same function
4. **Tech cards**: meta-dependent sideboard/flex slots → similar within their niche only

**HAND TRAP TAXONOMY (Do NOT Treat All Hand Traps as Similar)**
- Ash Blossom: stops searches/summons-from-deck/mill-to-GY (hits ~80% of combo openers)
- Infinite Impermanence: negates on-field activated monster effects (broader target, different timing)
- Nibiru: punishes 5+ summons by mass-tributing (combo chain punisher, dead vs short combos)
- Ghost Ogre: destroys on-field cards when they activate (narrower than Ash, different function)
- Maxx "C": draws per special summon (where legal -- format-dependent)
- These are NOT substitutes for each other. Score hand traps within same sub-function 0.4-0.6, across sub-functions 0.2-0.4

**GOING FIRST vs GOING SECOND (Critical Axis)**
- Going-first cards (combo pieces, negates, floodgates) ≠ going-second cards (board breakers, hand traps)
- Dark Ruler No More is a going-second board breaker; Ash Blossom works in both game states
- Two board breakers are more similar to each other than a board breaker is to a hand trap

**BANLIST STATUS**
- Forbidden cards cannot substitute for anything in competitive play
- When a card is Limited (1 copy), players run 1 of it + 2-3 of similar cards → the "what replaces it?" query is the core similarity use case
- Always note if a card's status affects its substitutability

**SCORING EXAMPLES:**
- Blue-Eyes White Dragon vs Blue-Eyes Alternative → 0.85 (same archetype, similar function)
- Ash Blossom vs Ghost Ogre → 0.45 (both hand traps but different functions, different meta calls)
- Ash Blossom vs Dark Ruler No More → 0.25 (both disruption but different game-state categories)
- Snake-Eye Ash vs Reinforcement of the Army → 0.30 (both search but one is archetype-locked)
- Dark Magician vs Blue-Eyes → 0.30 (different archetypes, similar era/nostalgia only)
"""
            elif game_lower in ["pokemon", "pkm"]:
                game_context = """
**GAME CONTEXT: Pokemon Trading Card Game**
- Use Pokemon TCG terminology: "Pokemon", "Energy", "Trainer", "HP", "Type", "Weakness", "Resistance"
- Card types: Pokemon (Basic, Stage 1/2, EX, GX, V, VMAX, VSTAR, ex), Trainer (Supporter, Item, Stadium, Tool), Energy
- Regulation marks and rotation affect card availability
- DO NOT use Magic: The Gathering terminology

**PRIZE TRADE SYSTEM (Critical -- Invisible in Card Text)**
- Single-prize Pokemon (no rule box): gives up 1 prize when KO'd
- Pokemon ex/V: gives up 2 prizes when KO'd
- Pokemon VMAX: gives up 3 prizes when KO'd
- Two cards with IDENTICAL attack text are fundamentally different if they have different prize costs
- A single-prize attacker doing 160 damage is strategically superior to a 2-prize attacker doing 160
- "Same attack, different prize cost" is a CRITICAL difference, not a footnote → reduce similarity by 0.2-0.3

**SUPPORTER TAXONOMY (Do NOT Treat All Draw Supporters as Similar)**
- Professor's Research: unconditional draw 7 but FORCES discard of current hand → best when hand is bad
- Iono: mutual shuffle-draw scaled by prizes + disruption to opponent → tempo/disruption tool
- Arven: searches 1 Item + 1 Tool → low draw, high consistency for specific setups
- These serve different strategic purposes despite all being "draw Supporters" → score 0.4-0.6, not 0.8+

**ITEM vs SUPPORTER DISTINCTION**
- If an Item and a Supporter do the same thing, the Item is better (no once-per-turn restriction)
- Search Items (Nest Ball, Ultra Ball) are more similar to each other than either is to a search Supporter

**ROTATION LEGALITY**
- Regulation marks (letters H/I/J for current Standard) gate legality
- A rotated card is NOT a substitute for its Standard-legal replacement in competitive play
- Always note if rotation status affects substitutability

**SCORING:**
- Same evolution line → 0.5-0.7
- Same type + similar role → 0.4-0.6
- Same function but different prize cost → reduce by 0.2-0.3
- Charizard ex (2-prize) vs Radiant Charizard (1-prize) → 0.40 (thematically related but different prize economies)
"""
            elif game_lower in ["magic", "mtg"]:
                game_context = """
**GAME CONTEXT: Magic: The Gathering**
- Use Magic terminology: "mana", "instant", "sorcery", "creature", "power", "toughness", "CMC"
- Consider: Colors (WUBRG), card types, mana costs, keywords
- Formats: Vintage, Legacy, Modern, Pioneer, Standard, Pauper, Commander/EDH

**STRICTLY BETTER / FUNCTIONAL REPRINT (Player Vocabulary)**
- "Strictly better": card A is superior in at least one respect, inferior in zero. Lightning Bolt > Shock (same cost, 3 > 2 damage)
- "Functional reprint": different name, identical/near-identical rules text → genuinely interchangeable in casual play
- "Budget version of": approximates same function for lower $, with some sacrifice (lower power, higher mana cost)
- "On a different axis": two cards that address same problem through different mechanisms (Thoughtseize vs Counterspell both stop spells, but operate differently) → score 0.3-0.4, NOT 0.7+

**MANA COST PRECISION (Multi-Axis)**
- CMC is not the only cost dimension. Color pip density matters independently:
  - {R} vs {2}{R}: both red, but different splash-ability in multicolor decks
  - {R}{R} vs {1}{R}: both 2-CMC, but double pip demands more color commitment
- Instant vs Sorcery with same effect: meaningfully different (holding up mana at end of turn ≠ main phase cast) → reduce similarity by 0.1-0.2

**FORMAT LEGALITY (Hard Gate)**
- A card not legal in a format cannot substitute for one that is, within that format
- Same pair can have different similarity across formats:
  - Counterspell vs Mana Leak: Mana Leak is the Modern option, but becomes dead late game; Counterspell is strictly better in Legacy → note format dependency
  - Chain Lightning is Legacy-only; Lightning Bolt is Modern+Legacy

**COMMANDER SPECIAL CASE**
- 100-card singleton means you run BOTH the "strictly better" and "strictly worse" versions
- Similarity in Commander is about "fills same role" not "substitutes for" → both can coexist

**SIDEBOARD vs MAINDECK**
- Hate cards (graveyard hate, artifact hate) are similar within hate category, not across categories
- Rest in Peace vs Stony Silence: both sideboard staples, completely different targets → score 0.15

**SCORING:**
- Lightning Bolt vs Shock → 0.70 (same function, strictly better relationship)
- Path vs Swords to Plowshares → 0.80 (functional reprint, minor difference in drawback)
- Counterspell vs Mana Leak → 0.50 (same function, different efficiency and late-game)
- Thoughtseize vs Counterspell → 0.30 (both stop spells but on different axes)
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

    ARCHETYPE_DESC_MODEL = os.getenv("ANNOTATOR_MODEL_ARCHETYPE", "openai/gpt-4o-mini")
    ARCHETYPE_DESC_PROMPT = """You are an expert TCG deck analyst.

Given an archetype label and a small sample of representative cards, write a concise description
of the archetype. Keep it concrete and game-appropriate.

Return a structured response that matches the output schema."""

    archetype_description_agent = make_agent(
        ARCHETYPE_DESC_MODEL,
        ArchetypeDescription,
        ARCHETYPE_DESC_PROMPT,
    )

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
        use_agentic_meta_judge: bool = False,
        agentic_meta_judge_max_rounds: int = 3,
        enforce_baseline_rules: bool = True,  # Set to False when using agentic meta-judge
        use_agent_topology: bool = False,  # Use hierarchical agent topology
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
        self.use_agentic_meta_judge = use_agentic_meta_judge and HAS_ENRICHMENT
        self.use_agent_topology = use_agent_topology and HAS_ENRICHMENT
        # Research-based: Keep both dynamic feedback AND static rules (hybrid approach)
        # Dynamic feedback for refinement, static rules for validation/safety
        self.enforce_baseline_rules = enforce_baseline_rules and HAS_ENRICHMENT

        # Agent topology (hierarchical agent system)
        self.agent_topology = None
        if self.use_agent_topology:
            try:
                from .agent_topology import create_annotation_topology

                self.agent_topology = create_annotation_topology(
                    game=game,
                    use_specialists=True,
                    use_validator=True,
                    use_supervisor=True,
                )
                print(
                    "  Agent topology enabled (hierarchical: supervisor → specialists → validator)"
                )
            except Exception as e:
                print(f"  Warning: Failed to initialize agent topology: {e}")
                self.use_agent_topology = False

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

        # Agentic meta-judge for multi-round moderation
        self.agentic_meta_judge: AgenticMetaJudge | None = None
        if self.use_agentic_meta_judge and AgenticMetaJudge:
            try:
                self.agentic_meta_judge = AgenticMetaJudge(
                    model=None,  # Use default (Claude Sonnet)
                    max_rounds=agentic_meta_judge_max_rounds,
                    min_consensus_threshold=0.7,
                    min_quality_threshold=0.6,
                )
                print(
                    f"  Agentic meta-judge enabled (max {agentic_meta_judge_max_rounds} rounds, IAA moderation)"
                )
                if self.enforce_baseline_rules:
                    print("  Warning: Baseline rules disabled when using agentic meta-judge")
            except Exception as e:
                print(f"  Warning: Failed to initialize agentic meta-judge: {e}")
                self.use_agentic_meta_judge = False

    def _load_decks(self) -> list[dict]:
        """Load decks with metadata, filtered by game if specified."""
        # Small, tracked fixture for tests and dev environments that don't have
        # full processed datasets checked out.
        test_fixture = (
            Path(__file__).resolve().parent.parent
            / "tests"
            / "fixtures"
            / "decks_export_hetero_small.jsonl"
        )
        candidates: list[Path] = [
            PATHS.decks_with_metadata,
            PATHS.decks_all_final,
            PATHS.decks_all_enhanced,
            PATHS.decks_all_unified,
            PATHS.backend / "decks_hetero.jsonl",
            test_fixture,
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

    async def annotate_archetypes(self, top_n: int = 10) -> list[ArchetypeDescription]:
        """Generate short archetype descriptions for the most common archetypes."""
        if not HAS_PYDANTIC_AI or archetype_description_agent is None:
            raise ImportError("pydantic-ai required")

        # Pick the most common archetypes (exclude missing/unknown)
        arch_counts = Counter(
            a for a in (d.get("archetype") for d in self.decks) if isinstance(a, str) and a.strip()
        )
        archetypes = [a for a, _ in arch_counts.most_common(max(1, int(top_n)))]

        results: list[ArchetypeDescription] = []

        for arch in archetypes:
            arch_decks = [d for d in self.decks if d.get("archetype") == arch]

            # Best-effort format context: use the most common non-empty format.
            fmt_counts = Counter(
                f for f in (d.get("format") for d in arch_decks) if isinstance(f, str) and f.strip()
            )
            fmt = fmt_counts.most_common(1)[0][0] if fmt_counts else None

            # Collect representative cards (dedupe, preserve order)
            raw_cards: list[str] = []
            for d in arch_decks:
                cs = d.get("cards")
                if not isinstance(cs, list):
                    continue
                for c in cs:
                    if isinstance(c, str):
                        raw_cards.append(c)
                    elif isinstance(c, dict):
                        name = c.get("name") or c.get("Name")
                        if isinstance(name, str):
                            raw_cards.append(name)

            seen: set[str] = set()
            sample_cards: list[str] = []
            for c in raw_cards:
                c = str(c).strip()
                if not c or c in seen:
                    continue
                seen.add(c)
                sample_cards.append(c)
                if len(sample_cards) >= 20:
                    break

            prompt = (
                "Game: "
                + str(self.game or "all")
                + "\nFormat: "
                + str(fmt or "Unknown")
                + "\nArchetype: "
                + arch
                + "\nSample Cards: "
                + ", ".join(sample_cards)
                + "\n\nWrite a concise archetype description."
            )

            run = await archetype_description_agent.run(prompt)
            results.append(run.output)

        return results

    async def annotate_similarity_pairs(
        self,
        num_pairs: int = 100,
        strategy: str = "diverse",
        batch_size: int = 10,
    ) -> list[CardSimilarityAnnotation | dict[str, Any]]:
        """Create similarity annotations for card pairs.

        Args:
            num_pairs: How many pairs to annotate
            strategy: "diverse" (wide coverage) or "focused" (specific archetype)
            batch_size: Number of pairs to process in parallel
        """
        print(f"\nAnnotating {num_pairs} similarity pairs ({strategy} strategy)...")

        # Select pairs to annotate
        # Default to stratified diverse (high/medium/low similarity mix)
        # Prefer uncertainty-based selection if available (active learning)
        if strategy == "diverse":
            # Try uncertainty first if available, fall back to stratified diverse
            if self.use_uncertainty_selection and self.uncertainty_selector:
                # Use uncertainty-based selection (hard mining) - preferred for active learning
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
                print(f"  Selected {len(pairs)} uncertain pairs for annotation (active learning)")
            else:
                pairs = self._select_diverse_pairs(num_pairs)  # Now uses stratified sampling
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
        ) -> CardSimilarityAnnotation | dict[str, Any] | None:
            async with semaphore:
                try:
                    # Initialize graph_features for baseline rule enforcement
                    graph_features = None

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

                            # Use agentic meta-judge for multi-round moderation if enabled
                            if self.use_agentic_meta_judge and self.agentic_meta_judge:
                                # Moderate with agentic meta-judge (multi-round with feedback)
                                (
                                    final_round,
                                    all_rounds,
                                ) = await self.agentic_meta_judge.moderate_multi_round(
                                    multi_result.annotations,
                                    multi_annotator=self.multi_annotator,  # Pass for revision calls
                                    card1=card1,  # Required for revisions
                                    card2=card2,  # Required for revisions
                                    graph_context=graph_context,  # For revision context
                                )

                                # Use consensus annotation from final round if available
                                if (
                                    final_round.consensus_decision
                                    and final_round.consensus_decision.recommended_action
                                    == "accept"
                                ):
                                    # Use the best annotation from final round (highest quality feedback)
                                    if final_round.meta_judge_feedback:
                                        best_annotator = max(
                                            final_round.meta_judge_feedback.items(),
                                            key=lambda x: x[1].quality_score,
                                        )[0]
                                        ann = final_round.annotations.get(best_annotator)
                                    else:
                                        # Fallback to consensus if available
                                        ann = multi_result.consensus_annotation or next(
                                            iter(multi_result.annotations.values())
                                        )
                                else:
                                    # Consensus not reached, use best from initial round
                                    ann = multi_result.consensus_annotation or next(
                                        iter(multi_result.annotations.values())
                                    )

                                # Update source field for agentic meta-judge path and ensure required fields
                                if ann:
                                    updates = {
                                        "card1": card1,
                                        "card2": card2,
                                        "timestamp": datetime.now().isoformat(),
                                        "game": self.game or "unknown",
                                        "source": "llm_multi_annotator_agentic",
                                    }
                                    # Fix missing reasoning/thinking
                                    if not ann.reasoning or len(ann.reasoning.strip()) < 10:
                                        updates["reasoning"] = (
                                            ann.reasoning
                                            or f"Similarity score of {ann.similarity_score:.2f} based on multi-annotator consensus."
                                        )
                                    if not ann.thinking or len(ann.thinking.strip()) < 10:
                                        updates["thinking"] = (
                                            ann.thinking
                                            or f"Multi-annotator analysis determined similarity score of {ann.similarity_score:.2f}."
                                        )

                                    ann = ann.model_copy(update=updates)

                                # Log moderation results
                                if final_round.consensus_decision:
                                    print(
                                        f"  Meta-judge: {final_round.consensus_decision.recommended_action} "
                                        f"(consensus={final_round.consensus_decision.consensus_score:.2f}, "
                                        f"rounds={len(all_rounds)})"
                                    )
                            else:
                                # Use consensus annotation if available, otherwise use first annotation
                                if multi_result.consensus_annotation:
                                    ann = multi_result.consensus_annotation
                                elif multi_result.annotations:
                                    ann = next(iter(multi_result.annotations.values()))
                                else:
                                    return None

                                # Add confidence and calibration metadata from multi-result
                                confidence = (
                                    multi_result.confidence_score
                                    if hasattr(multi_result, "confidence_score")
                                    else 0.5
                                )
                                calibration_error = (
                                    multi_result.calibration_error
                                    if hasattr(multi_result, "calibration_error")
                                    else None
                                )

                                # Add IAA metadata and ensure required fields
                                updates = {
                                    "card1": card1,
                                    "card2": card2,
                                    "timestamp": datetime.now().isoformat(),
                                    "game": self.game or "unknown",
                                    "source": "llm_multi_annotator"
                                    + ("_agentic" if self.use_agentic_meta_judge else ""),
                                }
                                # Fix missing reasoning/thinking
                                if not ann.reasoning or len(ann.reasoning.strip()) < 10:
                                    updates["reasoning"] = (
                                        ann.reasoning
                                        or f"Similarity score of {ann.similarity_score:.2f} based on multi-annotator consensus."
                                    )
                                if not ann.thinking or len(ann.thinking.strip()) < 10:
                                    updates["thinking"] = (
                                        ann.thinking
                                        or f"Multi-annotator analysis determined similarity score of {ann.similarity_score:.2f}."
                                    )

                                ann = ann.model_copy(update=updates)

                                # Store confidence and calibration in annotation metadata if we add those fields
                                # For now, log them
                                if calibration_error and calibration_error > 0.3:
                                    logger.warning(
                                        f"High calibration error ({calibration_error:.2f}) for {card1} vs {card2} "
                                        f"(confidence={confidence:.2f})"
                                    )

                            # Store IAA metrics in annotation metadata (if we add a metadata field)
                            # For now, log IAA metrics
                            if multi_result.iaa_metrics.get("krippendorff_alpha", 0.0) < 0.6:
                                print(
                                    f"  Low IAA (alpha={multi_result.iaa_metrics.get('krippendorff_alpha', 0.0):.2f}) for {card1} vs {card2}"
                                )

                            # Validate and enforce baseline rules for multi-annotator path (only if enabled)
                            if self.enforce_baseline_rules and graph_features and ann:
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

                                min_score = None
                                violation_reason = None

                                if jaccard > 0.3:
                                    min_score = 0.6
                                    if ann.similarity_score < min_score:
                                        violation_reason = f"Jaccard {jaccard:.3f} > 0.3 requires score >= 0.6, got {ann.similarity_score:.3f}"
                                elif jaccard > 0.1:
                                    min_score = 0.3
                                    if ann.similarity_score < min_score:
                                        violation_reason = f"Jaccard {jaccard:.3f} > 0.1 requires score >= 0.3, got {ann.similarity_score:.3f}"

                                if cooccur > 10:
                                    cooccur_min = 0.4
                                    if min_score is None or cooccur_min > min_score:
                                        min_score = cooccur_min
                                    if ann.similarity_score < cooccur_min:
                                        if violation_reason:
                                            violation_reason += (
                                                f"; Co-occurrence {cooccur} requires score >= 0.4"
                                            )
                                        else:
                                            violation_reason = f"Co-occurrence {cooccur} requires score >= 0.4, got {ann.similarity_score:.3f}"

                                if violation_reason and min_score is not None:
                                    logger.warning(
                                        f"BASELINE RULE VIOLATION (multi-annotator): {violation_reason}. Adjusting score from {ann.similarity_score:.3f} to {min_score:.3f}"
                                    )
                                    ann = ann.model_copy(update={"similarity_score": min_score})
                                    original_reasoning = ann.reasoning
                                    ann = ann.model_copy(
                                        update={
                                            "reasoning": f"{original_reasoning} [Note: Score adjusted to {min_score:.3f} to meet graph evidence minimum requirement (Jaccard {jaccard:.3f}, co-occurrence {cooccur})]"
                                        }
                                    )

                            # Skip single annotator path, go directly to enrichment
                        except Exception as e:
                            print(
                                f"  Multi-annotator failed for {card1} vs {card2}: {e}, falling back to single annotator"
                            )
                            ann = None  # Force single annotator path
                            graph_features = None  # Reset graph_features for single annotator path

                    # Single annotator mode (default or fallback)
                    if ann is None:
                        # Get graph context if available (non-blocking)
                        graph_context = ""
                        graph_features = None  # Initialize for baseline rule enforcement
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
                        # Priority: Critical feedback at top, important in middle
                        # Use game-specific feedback (not unioned across games)
                        game_key = (self.game or "unknown").lower() if self.game else "unknown"
                        feedback = None

                        # Prefer game-specific feedback
                        if (
                            hasattr(self, "meta_judge_feedback_by_game")
                            and game_key in self.meta_judge_feedback_by_game
                        ):
                            feedback = self.meta_judge_feedback_by_game[game_key]
                        elif hasattr(self, "meta_judge_feedback"):
                            # Fall back to global feedback (backward compatibility)
                            feedback = self.meta_judge_feedback

                        if feedback:
                            if feedback.get("critical"):
                                prompt_parts.insert(2, "")  # Insert after initial context
                                prompt_parts.insert(
                                    3,
                                    f"**CRITICAL Meta-Judge Feedback for {self.game.upper() if self.game else 'ALL GAMES'} (MUST APPLY):**",
                                )
                                for item in feedback["critical"][-2:]:  # Last 2 critical items
                                    if isinstance(item, dict):
                                        # Only include if game matches or no game tag
                                        item_game = item.get("game", "").lower()
                                        if not item_game or item_game == game_key:
                                            prompt_parts.insert(
                                                4,
                                                f"- {item.get('type', 'issue')}: {item.get('fix', '')}",
                                            )
                                    else:
                                        prompt_parts.insert(4, f"- {item}")

                            if feedback.get("important"):
                                prompt_parts.append("")
                                prompt_parts.append(
                                    f"**Important Meta-Judge Feedback for {self.game.upper() if self.game else 'ALL GAMES'}:**"
                                )
                                for item in feedback["important"][-2:]:  # Last 2 important items
                                    if isinstance(item, dict):
                                        # Only include if game matches or no game tag
                                        item_game = item.get("game", "").lower()
                                        if not item_game or item_game == game_key:
                                            prompt_parts.append(
                                                f"- {item.get('type', 'issue')}: {item.get('fix', '')}"
                                            )
                                    else:
                                        prompt_parts.append(f"- {item}")

                        # Backward compatibility: also check old format
                        elif (
                            hasattr(self, "meta_judge_prompt_additions")
                            and self.meta_judge_prompt_additions
                        ):
                            prompt_parts.append("")
                            prompt_parts.append("**Meta-Judge Feedback:**")
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

                        # Use agent topology if enabled, otherwise use direct agent
                        if self.use_agent_topology and self.agent_topology:
                            # Use hierarchical agent topology (supervisor → specialist → validator)
                            try:
                                graph_features_dict = (
                                    graph_features.model_dump()
                                    if hasattr(graph_features, "model_dump")
                                    else (
                                        graph_features if isinstance(graph_features, dict) else {}
                                    )
                                )
                                ann = await self.agent_topology.annotate(
                                    card1=card1,
                                    card2=card2,
                                    game=self.game,
                                    context={
                                        "graph_features": graph_features_dict,
                                        "archetypes": context.get("archetypes", "unknown"),
                                    },
                                    timeout=30.0,  # 30 second timeout for full topology
                                )
                                # Skip to enrichment step (topology handles validation)
                                # Note: topology returns annotation, continue to enrichment
                            except TimeoutError:
                                import logging

                                logger = logging.getLogger(__name__)
                                logger.warning(
                                    f"Agent topology timeout for {card1} vs {card2}, falling back to direct agent"
                                )
                                # Fall back to direct agent
                                ann = None  # Force fallback
                            except Exception as e:
                                import logging

                                logger = logging.getLogger(__name__)
                                logger.warning(
                                    f"Agent topology failed for {card1} vs {card2}, falling back to direct agent: {e}"
                                )
                                # Fall back to direct agent
                                ann = None  # Force fallback

                            # If topology failed, fall through to direct agent
                            if ann is None:
                                # Fall back to direct agent
                                agent = similarity_agent
                                if self.game:
                                    from .llm_annotator import get_similarity_prompt

                                    game_prompt = get_similarity_prompt(self.game)
                                    agent = make_agent(
                                        SIM_MODEL,
                                        CardSimilarityAnnotation,
                                        game_prompt,
                                    )
                                result = await agent.run(prompt)
                                ann = result.output
                        else:
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
                            ann = result.output

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

                        # Validate and enforce baseline rules based on graph evidence (only if enabled)
                        if self.enforce_baseline_rules and graph_features:
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

                            # Enforce baseline rules (adjust score if it violates minimum requirements)
                            min_score = None
                            violation_reason = None

                            if jaccard > 0.3:
                                min_score = 0.6
                                if ann.similarity_score < min_score:
                                    violation_reason = f"Jaccard {jaccard:.3f} > 0.3 requires score >= 0.6, got {ann.similarity_score:.3f}"
                            elif jaccard > 0.1:
                                min_score = 0.3
                                if ann.similarity_score < min_score:
                                    violation_reason = f"Jaccard {jaccard:.3f} > 0.1 requires score >= 0.3, got {ann.similarity_score:.3f}"

                            if cooccur > 10:
                                cooccur_min = 0.4
                                if min_score is None or cooccur_min > min_score:
                                    min_score = cooccur_min
                                if ann.similarity_score < cooccur_min:
                                    if violation_reason:
                                        violation_reason += (
                                            f"; Co-occurrence {cooccur} requires score >= 0.4"
                                        )
                                    else:
                                        violation_reason = f"Co-occurrence {cooccur} requires score >= 0.4, got {ann.similarity_score:.3f}"

                            # If violation detected, prefer to log and let prompt handle it next time
                            # Only force if score is significantly below minimum (more than 0.2 difference)
                            if violation_reason and min_score is not None:
                                import logging

                                logger = logging.getLogger(__name__)
                                # Only force if score is way off (more than 0.2 below minimum)
                                if ann.similarity_score < min_score - 0.2:
                                    logger.warning(
                                        f"BASELINE RULE VIOLATION: {violation_reason}. Adjusting score from {ann.similarity_score:.3f} to {min_score:.3f}"
                                    )
                                    ann = ann.model_copy(update={"similarity_score": min_score})
                                    original_reasoning = ann.reasoning
                                    ann = ann.model_copy(
                                        update={
                                            "reasoning": f"{original_reasoning} [Note: Score adjusted to {min_score:.3f} to meet graph evidence minimum (Jaccard {jaccard:.3f}, co-occurrence {cooccur})]"
                                        }
                                    )
                                else:
                                    # Minor violation - just log, don't force (let prompt handle it)
                                    logger.info(
                                        f"Minor baseline rule deviation: {violation_reason} (score {ann.similarity_score:.3f} close to minimum {min_score:.3f})"
                                    )

                        # Ensure required fields are populated before adding metadata
                        if not ann.reasoning or len(ann.reasoning.strip()) < 10:
                            ann = ann.model_copy(
                                update={
                                    "reasoning": ann.reasoning
                                    or f"Similarity score of {ann.similarity_score:.2f} based on functional and attribute analysis."
                                }
                            )
                        if not ann.thinking or len(ann.thinking.strip()) < 10:
                            ann = ann.model_copy(
                                update={
                                    "thinking": ann.thinking
                                    or f"Analyzed function, attributes, and graph evidence to determine similarity score of {ann.similarity_score:.2f}."
                                }
                            )

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

                            # Ensure card_comparison exists even if enrichment failed partially
                            if "card_comparison" not in enriched or not enriched.get(
                                "card_comparison"
                            ):
                                enriched["card_comparison"] = {
                                    "card1_attrs": {},
                                    "card2_attrs": {},
                                    "attribute_similarity": {},
                                    "functional_overlap": [],
                                    "differences": [],
                                }

                            # Ensure reasoning and thinking exist
                            if (
                                not enriched.get("reasoning")
                                or len(str(enriched.get("reasoning", "")).strip()) < 10
                            ):
                                enriched["reasoning"] = (
                                    enriched.get("reasoning")
                                    or f"Similarity score of {enriched.get('similarity_score', 0.0):.2f} based on analysis."
                                )
                            if (
                                not enriched.get("thinking")
                                or len(str(enriched.get("thinking", "")).strip()) < 10
                            ):
                                enriched["thinking"] = (
                                    enriched.get("thinking")
                                    or f"Analyzed to determine similarity score of {enriched.get('similarity_score', 0.0):.2f}."
                                )

                            # Return enriched dict (caller will handle serialization)
                            return enriched
                        except Exception as e:
                            # Graph enrichment failed, return original annotation with required fields
                            print(f"  Warning: Graph enrichment failed for {card1} vs {card2}: {e}")
                            import traceback

                            traceback.print_exc()

                            # Ensure required fields exist even if enrichment failed
                            ann_dict = ann.model_dump() if hasattr(ann, "model_dump") else dict(ann)
                            if "card_comparison" not in ann_dict:
                                ann_dict["card_comparison"] = {
                                    "card1_attrs": {},
                                    "card2_attrs": {},
                                    "attribute_similarity": {},
                                    "functional_overlap": [],
                                    "differences": [],
                                }
                            if (
                                not ann_dict.get("reasoning")
                                or len(str(ann_dict.get("reasoning", "")).strip()) < 10
                            ):
                                ann_dict["reasoning"] = (
                                    ann_dict.get("reasoning")
                                    or f"Similarity score of {ann_dict.get('similarity_score', 0.0):.2f}."
                                )
                            if (
                                not ann_dict.get("thinking")
                                or len(str(ann_dict.get("thinking", "")).strip()) < 10
                            ):
                                ann_dict["thinking"] = (
                                    ann_dict.get("thinking")
                                    or f"Analyzed similarity: {ann_dict.get('similarity_score', 0.0):.2f}."
                                )

                            return ann_dict

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
        """Select stratified pairs: 33% high-similarity, 33% medium, 33% diverse.

        This ensures we get a good distribution of similarity scores across the full range,
        rather than clustering in low ranges from only dissimilar pairs.
        """
        # Find cards that appear in multiple archetypes (interesting)
        card_archetypes = defaultdict(set)
        card_counts = Counter()

        for deck in self.decks:
            arch = deck.get("archetype", "Unknown")
            for card in deck.get("cards", []):
                card_name = card.get("name", "") if isinstance(card, dict) else str(card)
                if card_name:
                    card_archetypes[card_name].add(arch)
                    card_counts[card_name] += 1

        # Get cards that appear in 2-5 archetypes (not too narrow, not universal staples)
        interesting_cards = [
            card for card, archs in card_archetypes.items() if 2 <= len(archs) <= 5
        ]

        import random

        random.shuffle(interesting_cards)

        # Stratified sampling: 33% high-similarity (same archetype), 33% medium (overlapping), 33% diverse (different)
        n_high = max(1, n // 3)
        n_medium = max(1, n // 3)
        n_diverse = n - n_high - n_medium

        # High-similarity pairs: Same archetype
        arch_to_cards = defaultdict(list)
        for card in interesting_cards:
            for arch in card_archetypes[card]:
                arch_to_cards[arch].append(card)

        high_pairs = []
        for arch, cards in arch_to_cards.items():
            if len(cards) >= 2 and len(high_pairs) < n_high:
                sampled = random.sample(cards, min(2, len(cards)))
                if len(sampled) == 2:
                    c1, c2 = sampled
                    common_archs = card_archetypes[c1] & card_archetypes[c2]
                    high_pairs.append(
                        (
                            c1,
                            c2,
                            {
                                "count": min(card_counts[c1], card_counts[c2]),
                                "archetypes": ", ".join(list(common_archs)[:3])
                                if common_archs
                                else arch,
                                "similarity_expected": "high",
                            },
                        )
                    )

        # Medium-similarity pairs: Overlapping archetypes but not identical
        medium_pairs = []
        attempts = 0
        while len(medium_pairs) < n_medium and attempts < n_medium * 10:
            attempts += 1
            c1, c2 = random.sample(interesting_cards, 2)
            common_archs = card_archetypes[c1] & card_archetypes[c2]
            if (
                common_archs
                and len(common_archs) < len(card_archetypes[c1])
                and len(common_archs) < len(card_archetypes[c2])
            ):
                # Overlapping but not identical archetypes
                medium_pairs.append(
                    (
                        c1,
                        c2,
                        {
                            "count": min(card_counts[c1], card_counts[c2]),
                            "archetypes": ", ".join(list(common_archs)[:3])
                            if common_archs
                            else "overlapping",
                            "similarity_expected": "medium",
                        },
                    )
                )

        # Diverse pairs: Different archetypes (original behavior)
        diverse_pairs = []
        for i in range(0, min(n_diverse * 2, len(interesting_cards)), 2):
            if i + 1 < len(interesting_cards):
                c1, c2 = interesting_cards[i], interesting_cards[i + 1]
                common_archs = card_archetypes[c1] & card_archetypes[c2]
                if not common_archs:  # Only truly diverse pairs
                    diverse_pairs.append(
                        (
                            c1,
                            c2,
                            {
                                "count": min(card_counts[c1], card_counts[c2]),
                                "archetypes": "none",
                                "similarity_expected": "low",
                            },
                        )
                    )

        # Combine all pairs
        all_pairs = high_pairs[:n_high] + medium_pairs[:n_medium] + diverse_pairs[:n_diverse]
        random.shuffle(all_pairs)  # Shuffle to avoid ordering bias

        # Fill remaining slots with random pairs if needed
        while len(all_pairs) < n:
            if len(interesting_cards) >= 2:
                c1, c2 = random.sample(interesting_cards, 2)
                common_archs = card_archetypes[c1] & card_archetypes[c2]
                all_pairs.append(
                    (
                        c1,
                        c2,
                        {
                            "count": min(card_counts[c1], card_counts[c2]),
                            "archetypes": ", ".join(list(common_archs)[:3])
                            if common_archs
                            else "none",
                            "similarity_expected": "mixed",
                        },
                    )
                )
            else:
                break

        return all_pairs[:n]

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
                card_name = card.get("name", "") if isinstance(card, dict) else str(card)
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
