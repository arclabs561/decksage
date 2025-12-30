#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai>=0.0.12",
# ]
# ///
"""
Generate labels for new test set queries using LLM-as-Judge.

For queries that were generated but don't have labels yet, use LLM-as-Judge
to generate highly_relevant, relevant, somewhat_relevant, marginally_relevant, and irrelevant cards.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

try:
    from pydantic_ai import Agent
    from pydantic import BaseModel, Field
    import os
    from pathlib import Path
    
    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


LABEL_GENERATION_PROMPT = """You are an expert at evaluating card similarity for TCGs.

**Your Task**: For a given query card, generate a list of similar cards organized by relevance level.

**Relevance Levels**:
- **highly_relevant**: Direct substitutes, functional equivalents, or cards that serve the exact same role
- **relevant**: Cards that are similar in function or role, but not perfect substitutes
- **somewhat_relevant**: Cards with some similarity (same color, similar effect, same archetype)
- **marginally_relevant**: Cards with weak similarity (same type, same color, but different function)
- **irrelevant**: Cards that are not similar (different colors, different types, different functions)

**Evaluation Criteria**:
1. **Functional similarity**: Does it do the same thing?
2. **Role similarity**: Does it serve the same role in a deck?
3. **Archetype similarity**: Is it used in the same archetypes?
4. **Color identity**: Same or overlapping colors?
5. **Mana cost**: Similar CMC?
6. **Card type**: Same type (creature, instant, sorcery, etc.)?

**Output Format**: Return a JSON object with arrays for each relevance level containing card names.

**Examples**:
Query: "Lightning Bolt"
- highly_relevant: ["Chain Lightning", "Lava Spike"]
- relevant: ["Fireblast", "Lava Dart"]
- somewhat_relevant: ["Needle Drop", "Rift Bolt"]
- marginally_relevant: ["Skewer the Critics"]
- irrelevant: ["Counterspell", "Island", "Monastery Swiftspear"]

Generate labels for the query card."""


class CardLabels(BaseModel):
    """Card similarity labels organized by relevance."""
    highly_relevant: list[str] = Field(description="Direct substitutes, functional equivalents")
    relevant: list[str] = Field(description="Similar in function or role")
    somewhat_relevant: list[str] = Field(description="Some similarity (color, effect, archetype)")
    marginally_relevant: list[str] = Field(description="Weak similarity (type, color)")
    irrelevant: list[str] = Field(description="Not similar (different colors, types, functions)")


def make_label_generation_agent() -> Agent | None:
    """Create LLM agent for generating labels."""
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
                pass
        
        # Use frontier models from leaderboard (claude-opus-4-5 is top quality)
        model_name = (
            os.getenv("ANNOTATOR_MODEL_BEST") or
            os.getenv("ANNOTATOR_MODEL") or
            os.getenv("OPENROUTER_MODEL") or
            "anthropic/claude-opus-4.5"  # Top quality (#5 text, #1 webdev)
        )
        provider = os.getenv("LLM_PROVIDER", "openrouter")
        
        agent = Agent(
            f"{provider}:{model_name}",
            output_type=CardLabels,
            system_prompt=LABEL_GENERATION_PROMPT,
        )
        
        return agent
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        return None


def generate_labels_for_query(agent: Agent, query: str, use_case: str | None = None) -> dict[str, list[str]]:
    """Generate labels for a query card."""
    prompt = f"""Generate similarity labels for TCG card: {query}
"""
    
    if use_case:
        prompt += f"\nUse case: {use_case}\n"
    
    prompt += """
Provide 3-5 cards for each relevance level. Focus on well-known cards that are actually similar.
"""
    
    try:
        result = agent.run_sync(prompt)
        
        if hasattr(result, 'data') and result.data:
            labels = result.data
            if isinstance(labels, CardLabels):
                return {
                    "highly_relevant": labels.highly_relevant,
                    "relevant": labels.relevant,
                    "somewhat_relevant": labels.somewhat_relevant,
                    "marginally_relevant": labels.marginally_relevant,
                    "irrelevant": labels.irrelevant,
                }
            elif isinstance(labels, dict):
                return labels
    except Exception as e:
        logger.error(f"Error generating labels for {query}: {e}")
    
    return {
        "highly_relevant": [],
        "relevant": [],
        "somewhat_relevant": [],
        "marginally_relevant": [],
        "irrelevant": [],
    }


def generate_labels_for_test_set(
    test_set: dict[str, dict[str, Any]],
    batch_size: int = 10,
) -> dict[str, dict[str, Any]]:
    """Generate labels for queries that don't have them yet."""
    agent = make_label_generation_agent()
    if not agent:
        logger.error("Cannot create LLM agent")
        return test_set
    
    # Find queries that need labels
    queries_needing_labels = []
    for query, data in test_set.items():
        # Check if labels are missing or empty
        has_labels = (
            data.get("highly_relevant") or
            data.get("relevant") or
            data.get("somewhat_relevant")
        )
        if not has_labels:
            queries_needing_labels.append((query, data))
    
    logger.info(f"Found {len(queries_needing_labels)} queries needing labels")
    
    if not queries_needing_labels:
        return test_set
    
    # Generate labels in batches
    updated = test_set.copy()
    processed = 0
    
    for i in range(0, len(queries_needing_labels), batch_size):
        batch = queries_needing_labels[i:i+batch_size]
        logger.info(f"Processing batch {i//batch_size + 1}/{(len(queries_needing_labels)-1)//batch_size + 1} ({len(batch)} queries)...")
        
        for query, data in batch:
            use_case = data.get("use_case")
            labels = generate_labels_for_query(agent, query, use_case)
            
            # Merge labels into existing data
            updated[query] = {**data, **labels}
            processed += 1
            
            logger.debug(f"  Generated labels for {query}: {len(labels['highly_relevant'])} highly relevant")
    
    logger.info(f"✅ Generated labels for {processed} queries")
    
    return updated


def main() -> int:
    """Generate labels for new test set queries."""
    parser = argparse.ArgumentParser(description="Generate labels for test set queries")
    parser.add_argument("--input", type=str, required=True, help="Test set JSON")
    parser.add_argument("--output", type=str, required=True, help="Output test set JSON")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for generation")
    
    args = parser.parse_args()
    
    if not HAS_PYDANTIC_AI:
        logger.error("pydantic-ai not available")
        logger.error("Install with: pip install pydantic-ai")
        return 1
    
    # Load test set
    with open(args.input) as f:
        test_data = json.load(f)
        test_set = test_data.get("queries", test_data)
    
    # Generate labels
    updated = generate_labels_for_test_set(test_set, args.batch_size)
    
    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump({
            "version": "labeled",
            "queries": updated,
            "metadata": {
                "original_size": len(test_set),
                "updated_size": len(updated),
            },
        }, f, indent=2)
    
    logger.info(f"✅ Labeled test set saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

