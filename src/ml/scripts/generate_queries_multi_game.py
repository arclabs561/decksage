#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai>=0.0.12",
# ]
# ///
"""
Generate test queries for all games (Magic, Yu-Gi-Oh!, Pokémon).

Uses game-specific prompts and examples.
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

# Import enhanced query generation
import sys
script_dir = Path(__file__).parent
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

try:
    from generate_queries_enhanced import (
        EnhancedTestQuery,
        EnhancedTestQueryBatch,
        make_enhanced_query_agent,
        generate_enhanced_queries,
    )
    HAS_ENHANCED = True
except ImportError:
    HAS_ENHANCED = False


GAME_PROMPTS = {
    "magic": """You are an expert at generating high-quality test queries for Magic: The Gathering card similarity evaluation.

**Your Task**: Generate diverse test queries for Magic: The Gathering card similarity evaluation.

Note: This prompt is game-specific for Magic: The Gathering. For game-agnostic prompts, use the enhanced query generation system.

1. **Diversity Requirements**:
   - **Card Types**: Creatures, instants, sorceries, enchantments, artifacts, planeswalkers, lands
   - **Formats**: Standard, Modern, Legacy, Vintage, Commander, Limited, Pioneer
   - **Archetypes**: Aggro, Control, Combo, Midrange, Tempo, Ramp
   - **Power Levels**: Commons, uncommons, rares, mythics, format staples, niche cards
   - **Functions**: Removal, card draw, ramp, threats, answers, combo pieces, utility
   - **Eras**: Classic (Alpha-Urza), Modern era, Recent sets

2. **Query Selection Standards**:
   - **Well-known cards**: Not obscure, recognizable to players
   - **Clear similar cards**: Should have 5-10 obvious similar cards
   - **Specific use case**: Each query should test a specific similarity type
   - **Representative**: Cover different aspects of the game
   - **Challenging**: Include edge cases and nuanced similarities

3. **Use Case Categories**:
   - **substitute**: Cards that can replace each other (Lightning Bolt → Chain Lightning)
   - **synergy**: Cards that work well together (Thassa's Oracle + Demonic Consultation)
   - **archetype**: Cards that define archetypes (Dark Confidant → Jund)
   - **functional**: Cards with similar functions (Counterspell → Mana Leak)

Generate {num_queries} diverse, high-quality test queries.""",

    "pokemon": """You are an expert at generating high-quality test queries for Pokémon TCG card similarity evaluation.

**Your Task**: Generate diverse test queries for Pokémon TCG card similarity evaluation.

1. **Diversity Requirements**:
   - **Card Types**: Pokémon (Basic, Stage 1, Stage 2, V, VMAX, GX, EX), Trainers (Items, Supporters, Stadiums), Energy
   - **Functions**: Draw support, search, energy acceleration, disruption, evolution support, rule box cards
   - **Archetypes**: Aggro, Control, Combo, Toolbox
   - **Power Levels**: Commons, uncommons, rares, ultra rares, staples

2. **Query Selection Standards**:
   - **Well-known cards**: Recognizable to players
   - **Clear similar cards**: Should have 5-10 obvious similar cards
   - **Specific use case**: Each query should test a specific similarity type

3. **Use Case Categories**:
   - **substitute**: Cards that can replace each other (Professor's Research → Professor Juniper)
   - **synergy**: Cards that work well together (Pikachu → Pikachu VMAX)
   - **archetype**: Cards that define archetypes
   - **functional**: Cards with similar functions (Quick Ball → Ultra Ball)

Generate {num_queries} diverse, high-quality test queries for Pokémon TCG.""",

    "yugioh": """You are an expert at generating high-quality test queries for Yu-Gi-Oh! card similarity evaluation.

**Your Task**: Generate diverse test queries for Yu-Gi-Oh! card similarity evaluation.

1. **Diversity Requirements**:
   - **Card Types**: Monsters (Normal, Effect, Fusion, Synchro, Xyz, Link), Spells, Traps
   - **Functions**: Hand traps, negation, search, special summon, floodgates, quick effects, OTK enablers
   - **Archetypes**: Meta decks, rogue strategies, combo decks, control decks
   - **Power Levels**: Staples, archetype-specific, niche cards

2. **Query Selection Standards**:
   - **Well-known cards**: Recognizable to players
   - **Clear similar cards**: Should have 5-10 obvious similar cards
   - **Specific use case**: Each query should test a specific similarity type

3. **Use Case Categories**:
   - **substitute**: Cards that can replace each other (Ash Blossom → Effect Veiler)
   - **synergy**: Cards that work well together (Blue-Eyes White Dragon → Blue-Eyes Alternative)
   - **archetype**: Cards that define archetypes
   - **functional**: Cards with similar functions (Pot of Greed → Pot of Desires)

Generate {num_queries} diverse, high-quality test queries for Yu-Gi-Oh!.""",
}


def generate_game_queries(
    game: str,
    num_queries: int,
    agent: Agent | None = None,
) -> list[EnhancedTestQuery]:
    """Generate queries for a specific game."""
    if not HAS_PYDANTIC_AI:
        logger.error("pydantic-ai required")
        return []
    
    if not HAS_ENHANCED:
        logger.error("Enhanced query generation not available")
        return []
    
    # Use game-specific prompt
    game_prompt = GAME_PROMPTS.get(game, GAME_PROMPTS["magic"])
    prompt = game_prompt.format(num_queries=num_queries)
    
    # Create agent if not provided
    if agent is None:
        agent = make_enhanced_query_agent()
    
    if not agent:
        logger.error("Could not create query generation agent")
        return []
    
    try:
        result = agent.run_sync(prompt)
        
        # Handle different result formats
        if hasattr(result, 'data') and result.data:
            data = result.data
        elif hasattr(result, 'output') and result.output:
            data = result.output
        else:
            logger.error(f"Unexpected result format: {result}")
            return []
        
        return data.queries if hasattr(data, 'queries') else []
    except Exception as e:
        logger.error(f"Failed to generate queries: {e}")
        return []


def main() -> int:
    """Generate queries for all games."""
    parser = argparse.ArgumentParser(description="Generate test queries for all games")
    parser.add_argument("--game", type=str, required=True, choices=["magic", "pokemon", "yugioh"],
                       help="Game to generate queries for")
    parser.add_argument("--num-queries", type=int, default=50, help="Number of queries to generate")
    parser.add_argument("--output", type=str, help="Output JSON (optional)")
    
    args = parser.parse_args()
    
    if not HAS_PYDANTIC_AI:
        print("❌ pydantic-ai required")
        return 1
    
    print(f"Generating {args.num_queries} queries for {args.game}...")
    
    queries = generate_game_queries(args.game, args.num_queries)
    
    if not queries:
        print("❌ No queries generated")
        return 1
    
    print(f"✅ Generated {len(queries)} queries")
    
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dict format
        queries_dict = {}
        for q in queries:
            queries_dict[q.query] = {
                "use_case": q.use_case,
                "format": q.format,
                "archetype": q.archetype,
                "reasoning": q.reasoning,
                "expected_similar": q.expected_similar if hasattr(q, 'expected_similar') else [],
                "difficulty": q.difficulty if hasattr(q, 'difficulty') else None,
            }
        
        output_data = {
            "version": "generated",
            "game": args.game,
            "queries": queries_dict,
        }
        
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        
        print(f"✅ Saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

