#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai>=0.0.12",
# ]
# ///
"""
Enhanced label generation with better models, richer context, and improved prompts.

Uses:
- Better models (GPT-4, Claude 3.5 Sonnet) with explicit model selection
- Richer context (card attributes, Oracle text, functional tags)
- Improved prompts with examples and clear criteria
- Multi-step reasoning for complex queries

Research Basis:
- Clear guidelines with examples improve annotation quality
- Richer context reduces ambiguity and improves consistency
- Better models (frontier LLMs) provide more accurate judgments
- Multi-dimensional annotation captures nuanced relationships

References:
- Data annotation best practices: https://www.atltranslate.com/ai/blog/labeling-data-best-practices
- Annotation guidelines: https://snorkel.ai/blog/data-annotation/
- Data labeling best practices: https://www.netguru.com/blog/data-labeling-best-practices
- Human data quality: https://lilianweng.github.io/posts/2024-02-05-human-data-quality/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

try:
    from pydantic_ai import Agent
    from pydantic import BaseModel, Field
    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import expanded judge criteria for better prompts
try:
    from ml.evaluation.expanded_judge_criteria import EXPANDED_SIMILARITY_JUDGE_PROMPT
    USE_EXPANDED_CRITERIA = True
except ImportError:
    USE_EXPANDED_CRITERIA = False

# Cost tracking (optional)
try:
    from ml.utils.pydantic_ai_helpers import run_with_tracking
    HAS_PYDANTIC_AI_HELPERS = True
except ImportError:
    HAS_PYDANTIC_AI_HELPERS = False
    run_with_tracking = None  # type: ignore[assignment]

try:
    from ml.utils.llm_cost_tracker import LLMCostTracker  # noqa: F401
    HAS_COST_TRACKER = True
except ImportError:
    HAS_COST_TRACKER = False

# Enhanced prompt with rich context and examples (legacy - use EXPANDED_SIMILARITY_JUDGE_PROMPT instead)
ENHANCED_LABEL_GENERATION_PROMPT_BASE = """You are an expert TCG judge specializing in card similarity evaluation.

**Your Task**: For a given query card, generate a comprehensive list of similar cards organized by relevance level.

**Context Available** (use all available information):
- Card Oracle text (rules text) - **CRITICAL**: Read the actual card text
- Functional tags (removal, ramp, card draw, etc.) - 90+ role classifications
- Mana cost and converted mana cost (CMC) - Efficiency matters
- Card type (creature, instant, sorcery, etc.) - Type affects similarity
- Color identity - Same colors = more similar
- Format legality and usage patterns - Format context matters
- Archetype associations - Archetype staples are more similar
- Power/Toughness (for creatures) - Stats affect similarity
- Keywords and abilities - Shared keywords = more similar
- Set and rarity - Context for power level

**Relevance Levels** (mapped to 0-4 similarity scale):

1. **highly_relevant** (Score: 4, equivalent to 0.9-1.0 similarity)
   - Direct functional substitutes (Lightning Bolt → Chain Lightning)
   - Perfect role equivalents (Counterspell → Mana Leak in tempo decks)
   - Cards that serve identical purposes (Sol Ring → Mana Crypt)

2. **relevant** (Score: 3, equivalent to 0.7-0.89 similarity)
   - Similar function with minor differences (Fatal Push → Path to Exile)
   - Same role, different execution (Brainstorm → Ponder)
   - Strong alternatives in same archetype (Dark Confidant → Phyrexian Arena)

3. **somewhat_relevant** (Score: 2, equivalent to 0.4-0.69 similarity)
   - Same color/archetype, different function (Lightning Bolt → Monastery Swiftspear)
   - Similar mana cost, related effect (Lightning Bolt → Skullcrack)
   - Cards that work together (Lightning Bolt → Young Pyromancer) - note: synergy, not similarity

4. **marginally_relevant** (Score: 1, equivalent to 0.2-0.39 similarity)
   - Same color, different type/function (Lightning Bolt → Mountain)
   - Weak thematic connection (Lightning Bolt → Electrostatic Bolt)
   - Same format, different role (Lightning Bolt → Goblin Guide)

5. **irrelevant** (Score: 0, equivalent to 0.0-0.19 similarity)
   - Different colors, types, functions (Lightning Bolt → Counterspell)
   - No meaningful relationship (Lightning Bolt → Island)

**Example Query: "Lightning Bolt"**
- highly_relevant (4): ["Chain Lightning", "Lava Spike"] - both 1R instant, 3 damage
- relevant (3): ["Fireblast", "Lava Dart", "Burst Lightning"] - similar burn, minor differences
- somewhat_relevant (2): ["Needle Drop", "Rift Bolt", "Skullcrack"] - related red effects
- marginally_relevant (1): ["Goblin Guide"] - same color/format, different function
- irrelevant (0): ["Counterspell", "Island", "Dark Confidant"] - different colors/functions

**Evaluation Criteria** (in priority order, use ALL available context):

1. **Functional similarity** (HIGHEST PRIORITY): Does it do the same thing?
   - Read Oracle text carefully - same effect = highly_relevant (4)
   - Example: "Lightning Bolt" (1R, instant, 3 damage) vs "Chain Lightning" (1R, instant, 3 damage) = 4
   - Example: "Lightning Bolt" vs "Shock" (1R, instant, 2 damage) = 3 (similar but weaker)

2. **Role similarity**: Does it serve the same role in a deck?
   - Removal vs removal, card draw vs card draw, ramp vs ramp
   - Consider deck archetype context
   - Example: "Fatal Push" vs "Path to Exile" (both removal, different execution) = 3

3. **Mana efficiency**: Similar CMC and color requirements?
   - Same CMC + same colors = more similar
   - Example: "Lightning Bolt" (1R) vs "Lava Spike" (1R) = 4
   - Example: "Lightning Bolt" (1R) vs "Fireblast" (0R) = 3 (different CMC)

4. **Archetype fit**: Is it used in the same archetypes?
   - Cards that define archetypes together = relevant (3)
   - Example: "Dark Confidant" + "Tarmogoyf" (both Jund staples) = 3

5. **Synergy potential**: Do they work well together?
   - Cards that combo = somewhat_relevant (2) - note: synergy, not similarity
   - Example: "Thassa's Oracle" + "Demonic Consultation" = 2 (combo, not substitutes)

6. **Format context**: Same format legality and usage?
   - Format-specific cards = more similar if same format
   - Example: Modern: Lightning Bolt (legal) vs Chain Lightning (not legal) = lower similarity
   - Example: Legacy: Both legal = higher similarity
   - Example: Path to Exile (Modern) vs Swords to Plowshares (Legacy) = 3 (same role, different format)

7. **Type and keywords**: Same type and shared keywords?
   - Shared keywords (flash, haste, etc.) = more similar
   - Same type (instant vs instant) = more similar than different types

**Output Requirements**:
- Provide 5-10 cards per relevance level (more for highly_relevant)
- Include diverse card types when appropriate
- Consider format-specific alternatives (e.g., Modern vs Legacy)
- Use ALL available context (Oracle text, attributes, tags)
- Explain reasoning for edge cases in the reasoning field

**Quality Standards** (be rigorous):
- **Be precise**: "Lightning Bolt" and "Chain Lightning" are highly_relevant (4) - both 1R instant, 3 damage
- **Be comprehensive**: Include both obvious and subtle similarities
- **Be accurate**: Don't include cards that are clearly different (different functions)
- **Be diverse**: Include cards from different eras, rarities, and formats when relevant
- **Use context**: If Oracle text is provided, read it carefully and use it
- **Distinguish similarity from synergy**: Similar cards can replace each other; synergistic cards work together

**Critical Distinctions**:
- **Co-occurrence ≠ Similarity**: Cards that appear together (synergy) are NOT similar
  - Example: "Goblin Guide" and "Lightning Bolt" co-occur but aren't similar (creature vs instant)
- **Statistical similarity ≠ Functional similarity**: High embedding similarity doesn't mean functional similarity
- **Substitutability matters**: Can you replace one with the other? If not, lower score

**Calibration Guidelines**:
- Use the full scale (0-4), don't cluster at extremes
- Most cards will be 2-3 (moderate similarity)
- Reserve 4 (highly_relevant) for truly near-identical substitutes
- Reserve 0 (irrelevant) for completely unrelated cards
- If unsure between two scores, choose the lower one (be conservative)
- Consider format context: format mismatches reduce similarity scores

Generate labels for the query card with this enhanced understanding, using ALL available context."""

# Use expanded criteria if available, otherwise use base
if USE_EXPANDED_CRITERIA:
    ENHANCED_LABEL_GENERATION_PROMPT = EXPANDED_SIMILARITY_JUDGE_PROMPT + """

**Additional Context for Label Generation**:
You are generating labels organized by relevance levels (highly_relevant, relevant, somewhat_relevant, marginally_relevant, irrelevant).

For each relevance level, provide 5-10 card names that match that level of similarity to the query card.

**CRITICAL: Each card must appear in EXACTLY ONE relevance level**
- A card cannot be both "highly_relevant" AND "relevant" - choose the most appropriate level
- A card cannot be both "relevant" AND "irrelevant" - this is a contradiction
- If a card could fit multiple levels, choose the HIGHEST appropriate level (most similar)
- Example: "Chain Lightning" for "Lightning Bolt" should be "highly_relevant" (4), not also in "relevant" (3)

**Output Format**: Return a JSON object with arrays for each relevance level containing card names, plus a reasoning field explaining the similarity patterns."""
else:
    ENHANCED_LABEL_GENERATION_PROMPT = ENHANCED_LABEL_GENERATION_PROMPT_BASE


if HAS_PYDANTIC_AI:
    class EnhancedCardLabels(BaseModel):
        """Enhanced card similarity labels with reasoning."""
        highly_relevant: list[str] = Field(
            description="Direct functional substitutes and perfect role equivalents (5-10 cards)"
        )
        relevant: list[str] = Field(
            description="Similar function with minor differences, strong alternatives (5-10 cards)"
        )
        somewhat_relevant: list[str] = Field(
            description="Same color/archetype different function, similar mana cost (5-10 cards)"
        )
        marginally_relevant: list[str] = Field(
            description="Weak thematic connection, same color different type (3-5 cards)"
        )
        irrelevant: list[str] = Field(
            description="No meaningful relationship, different colors/types (3-5 cards for calibration)"
        )
        reasoning: str = Field(
            description="Brief explanation of the similarity patterns identified (2-3 sentences)"
        )
else:
    # Dummy class when pydantic not available
    class EnhancedCardLabels:
        pass


def load_card_context(card_name: str, card_attrs_path: Path | None = None, game: str | None = None) -> dict[str, Any]:
    """Load card attributes for context from multiple sources."""
    context = {}
    
    # Try card attributes CSV first (if path provided)
    if card_attrs_path and card_attrs_path.exists():
        try:
            import pandas as pd
            df = pd.read_csv(card_attrs_path)
            # Handle both "NAME" and "name" column names (case-insensitive)
            name_col = None
            for col in df.columns:
                if col.upper() == "NAME" or col.lower() == "name":
                    name_col = col
                    break
            
            if name_col:
                # Use case-insensitive comparison
                card_row = df[df[name_col].astype(str).str.lower() == card_name.lower()]
            else:
                # Fallback: try first column
                card_row = df[df.iloc[:, 0].astype(str).str.lower() == card_name.lower()]
            
            if not card_row.empty:
                row = card_row.iloc[0]
                # Safely get columns (handle missing columns gracefully)
                def safe_get(col_name: str, default: str = "") -> str:
                    """Get column value, handling case variations and missing columns."""
                    # Try exact match first
                    if col_name in row:
                        val = row[col_name]
                        return str(val) if pd.notna(val) else default
                    # Try case-insensitive match
                    for col in row.index:
                        if col.lower() == col_name.lower():
                            val = row[col]
                            return str(val) if pd.notna(val) else default
                    return default
                
                # Handle CMC conversion (might be string or float)
                cmc_val = safe_get("cmc", "0")
                try:
                    cmc = float(cmc_val) if cmc_val else 0.0
                except (ValueError, TypeError):
                    cmc = 0.0
                
                context = {
                    "oracle_text": safe_get("oracle_text", ""),
                    "type": safe_get("type", ""),
                    "mana_cost": safe_get("mana_cost", ""),
                    "cmc": cmc,
                    "colors": safe_get("colors", ""),
                    "rarity": safe_get("rarity", ""),
                    "power": safe_get("power", ""),
                    "toughness": safe_get("toughness", ""),
                    "keywords": safe_get("keywords", ""),
                    "functional_tags": safe_get("functional_tags", ""),
                    "archetype": safe_get("archetype", ""),
                    "format_legal": safe_get("format_legal", ""),
                }
                return context
        except Exception as e:
            logger.debug(f"Could not load card context from CSV: {e}")
    
    # Try loading from card database based on game
    if game:
        try:
            from ml.data.card_database import get_card_database
            card_db = get_card_database()
            # Validate card exists in database
            if card_db.is_valid_card(card_name, game):
                # Could extend to return full card data from database
                # For now, just validate existence
                pass
        except ImportError:
            pass
    
    # Try loading from Scryfall API for Magic cards (if available)
    if game == "magic" and not context:
        try:
            from ml.scripts.enrich_attributes_with_scryfall import get_card_from_scryfall
            card_data = get_card_from_scryfall(card_name)
            if card_data:
                from ml.scripts.enrich_attributes_with_scryfall import extract_attributes_from_scryfall
                attrs = extract_attributes_from_scryfall(card_data)
                context = {
                    "oracle_text": attrs.get("oracle_text", ""),
                    "type": attrs.get("type", ""),
                    "mana_cost": attrs.get("mana_cost", ""),
                    "cmc": attrs.get("cmc", ""),
                    "colors": attrs.get("colors", ""),
                    "rarity": attrs.get("rarity", ""),
                }
        except (ImportError, Exception) as e:
            logger.debug(f"Could not load from Scryfall API: {e}")
    
    # Default: try standard path
    if not context:
        from ml.utils.paths import PATHS
        default_path = PATHS.card_attributes
        if default_path.exists():
            try:
                import pandas as pd
                df = pd.read_csv(default_path)
                card_row = df[df["NAME"].str.lower() == card_name.lower()]
                if not card_row.empty:
                    row = card_row.iloc[0]
                    context = {
                        "oracle_text": row.get("oracle_text", ""),
                        "type": row.get("type", ""),
                        "mana_cost": row.get("mana_cost", ""),
                        "cmc": row.get("cmc", ""),
                        "colors": row.get("colors", ""),
                        "rarity": row.get("rarity", ""),
                    }
            except Exception as e:
                logger.debug(f"Could not load card context from default path: {e}")
    
    return context


def make_enhanced_label_agent(
    model_name: str | None = None,
    use_best_model: bool = True,
) -> Agent | None:
    """Create enhanced LLM agent with better model selection."""
    if not HAS_PYDANTIC_AI:
        return None
    
    try:
        # Load .env
        env_file = Path(__file__).parent.parent.parent.parent / ".env"
        if env_file.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(env_file)
            except ImportError:
                # Manual parse
                with open(env_file) as f:
                    for line in f:
                        if "=" in line and not line.strip().startswith("#"):
                            key, value = line.split("=", 1)
                            os.environ[key.strip()] = value.strip().strip('"').strip("'")
        
        # Model selection: prefer frontier models from leaderboard
        # Top models: gemini-3-pro (#1), claude-opus-4-5 (#5), grok-4.1-thinking (#3)
        if model_name:
            selected_model = model_name
        elif use_best_model:
            # Try frontier models first (from leaderboard)
            selected_model = (
                os.getenv("ANNOTATOR_MODEL_BEST") or
                os.getenv("ANNOTATOR_MODEL") or
                "anthropic/claude-opus-4.5"  # Top quality (#5 text, #1 webdev on leaderboard)
            )
        else:
            selected_model = (
                os.getenv("ANNOTATOR_MODEL") or
                os.getenv("OPENROUTER_MODEL") or
                "anthropic/claude-opus-4-5-20251101"  # High quality default
            )
        
        provider = os.getenv("LLM_PROVIDER", "openrouter")
        
        logger.info(f"Using model: {provider}:{selected_model}")
        
        agent = Agent(
            f"{provider}:{selected_model}",
            output_type=EnhancedCardLabels,
            system_prompt=ENHANCED_LABEL_GENERATION_PROMPT,
        )
        
        return agent
    except Exception as e:
        logger.error(f"Failed to create enhanced agent: {e}")
        return None


def generate_labels_with_context(
    agent: Agent,
    query: str,
    use_case: str | None = None,
    card_context: dict[str, Any] | None = None,
    game: str | None = None,
) -> dict[str, Any]:
    """Generate labels with enhanced context."""
    # Build enhanced prompt with context
    game_name = game or "Magic: The Gathering"  # Default to Magic if not specified
    game_display = {"magic": "Magic: The Gathering", "pokemon": "Pokémon TCG", "yugioh": "Yu-Gi-Oh!"}.get(game, game_name)
    prompt_parts = [f"Generate similarity labels for {game_display} card: **{query}**"]
    
    if use_case:
        prompt_parts.append(f"\n**Use Case**: {use_case}")
    
    # Always try to load card context if not provided
    if not card_context:
        card_context = load_card_context(query, game=game)
    
    if card_context:
        prompt_parts.append("\n**Card Context**:")
        if card_context.get("oracle_text"):
            prompt_parts.append(f"- Oracle Text: {card_context['oracle_text'][:200]}...")
        if card_context.get("type"):
            prompt_parts.append(f"- Type: {card_context['type']}")
        if card_context.get("mana_cost"):
            prompt_parts.append(f"- Mana Cost: {card_context['mana_cost']}")
        if card_context.get("cmc"):
            prompt_parts.append(f"- CMC: {card_context['cmc']}")
        if card_context.get("colors"):
            prompt_parts.append(f"- Colors: {card_context['colors']}")
    else:
        prompt_parts.append("\n**Note**: Card context not available. Use your knowledge of this card.")
    
    # Add game context if available (CRITICAL for multi-game system)
    if game:
        prompt_parts.append(f"\n**CRITICAL: Game Context**")
        prompt_parts.append(f"You are evaluating cards for {game_display}.")
        prompt_parts.append(f"ONLY include cards from {game_display}. Do not include cards from other games.")
        prompt_parts.append(f"This is a critical constraint - cross-game contamination is a serious error.")
    
    prompt_parts.append("\nGenerate comprehensive labels considering functional similarity, role, archetype, and format context.")
    
    prompt = "\n".join(prompt_parts)
    
    try:
        # Use tracking wrapper if available
        if HAS_COST_TRACKER and HAS_PYDANTIC_AI_HELPERS and run_with_tracking:
            result = run_with_tracking(
                agent=agent,
                prompt=prompt,
                model=model_name if 'model_name' in locals() else "unknown",
                provider=provider if 'provider' in locals() else "openrouter",
                operation="label_generation",
            )
        else:
            result = agent.run_sync(prompt)
        
        # Handle different Pydantic AI result formats
        if hasattr(result, 'data') and result.data:
            data = result.data
        elif hasattr(result, 'output') and result.output:
            data = result.output
        else:
            logger.error(f"Unexpected result format: {result}")
            return {}
        
        # Convert to standard format
        labels = {
            "highly_relevant": data.highly_relevant,
            "relevant": data.relevant,
            "somewhat_relevant": data.somewhat_relevant,
            "marginally_relevant": data.marginally_relevant,
            "irrelevant": data.irrelevant,
            "_reasoning": getattr(data, 'reasoning', ''),
        }
        
        # Validate and filter cross-game contamination if game is known
        if game:
            try:
                from ml.data.card_database import get_card_database
                card_db = get_card_database()
                
                for level in ["highly_relevant", "relevant", "somewhat_relevant", "marginally_relevant", "irrelevant"]:
                    cards = labels[level]
                    valid_cards, invalid_cards = card_db.filter_cards_by_game(cards, game)
                    if invalid_cards:
                        logger.warning(f"Filtered {len(invalid_cards)} cross-game cards from {level} for {query}: {invalid_cards[:3]}")
                    labels[level] = valid_cards
            except ImportError:
                # Card database not available, skip filtering
                pass
            except Exception as e:
                logger.warning(f"Could not filter cross-game cards: {e}")
        
        return labels
    except Exception as e:
        logger.error(f"Failed to generate labels: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return {}


def main() -> int:
    """Test enhanced label generation."""
    parser = argparse.ArgumentParser(description="Enhanced label generation with better models")
    parser.add_argument("--query", type=str, required=True, help="Query card name")
    parser.add_argument("--use-case", type=str, help="Use case (substitute, synergy, archetype)")
    parser.add_argument("--card-attrs", type=str, help="Path to card_attributes_enriched.csv")
    parser.add_argument("--model", type=str, help="Specific model to use")
    parser.add_argument("--use-best", action="store_true", help="Use best available model")
    
    args = parser.parse_args()
    
    if not HAS_PYDANTIC_AI:
        logger.error("pydantic-ai required")
        return 1
    
    # Load context
    card_context = None
    if args.card_attrs:
        card_context = load_card_context(args.query, Path(args.card_attrs))
    
    # Create agent
    agent = make_enhanced_label_agent(
        model_name=args.model,
        use_best_model=args.use_best or not args.model,
    )
    
    if not agent:
        logger.error("Failed to create agent")
        return 1
    
    # Generate labels
    labels = generate_labels_with_context(
        agent,
        args.query,
        use_case=args.use_case,
        card_context=card_context,
    )
    
    print(json.dumps(labels, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

