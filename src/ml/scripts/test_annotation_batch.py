#!/usr/bin/env python3
"""
Small Batch Annotation Test

Test LLM annotation system on 5 decks before scaling.
Validates: API works, quality is good, costs are reasonable.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv(Path("../../.env"))


def load_sample_decks(jsonl_path, n=5):
    """Load sample decks from different archetypes."""

    samples = []
    seen_archetypes = set()

    with open(jsonl_path) as f:
        for line in f:
            deck = json.loads(line)
            arch = deck.get("archetype", "unknown")

            # Get diverse archetypes
            if arch not in seen_archetypes and arch != "unknown":
                samples.append(deck)
                seen_archetypes.add(arch)

                if len(samples) >= n:
                    break

    return samples


def annotate_deck_quality(deck, client):
    """Get LLM assessment of deck quality and archetype consistency."""

    cards = [c["name"] for c in deck.get("cards", [])]
    archetype = deck.get("archetype", "unknown")
    format_name = deck.get("format", "unknown")

    prompt = f"""Analyze this Magic: The Gathering deck.

Format: {format_name}
Claimed Archetype: {archetype}
Deck list: {", ".join(cards[:50])}...  # First 50 cards

Questions:
1. Does the archetype label match the actual cards? (yes/no/partial)
2. Is this a coherent competitive deck? (1-10 score)
3. What's the deck's actual strategy in one sentence?
4. Any obvious issues or inconsistencies?

Respond in JSON format:
{{
  "archetype_match": "yes|no|partial",
  "coherence_score": 1-10,
  "actual_strategy": "one sentence",
  "issues": ["list of issues if any"]
}}
"""

    response = client.chat.completions.create(
        model="anthropic/claude-4.5-sonnet",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=500,
    )

    content = response.choices[0].message.content

    # Try to parse JSON from response
    try:
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content.strip())
        return result
    except (json.JSONDecodeError, IndexError) as e:
        return {"error": f"Failed to parse response: {e}", "raw": content}


def main():
    data_path = Path("../../data/processed/decks_with_metadata.jsonl")

    # Check API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ OPENROUTER_API_KEY not found")
        print("Set in .env or: export OPENROUTER_API_KEY=your-key")
        return

    # Initialize client
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    print("LLM ANNOTATION TEST")
    print("=" * 60)
    print("Testing on 5 sample decks")
    print()

    # Load samples
    samples = load_sample_decks(data_path, n=5)
    print(f"Loaded {len(samples)} sample decks from different archetypes")

    # Annotate each
    results = []
    for i, deck in enumerate(samples, 1):
        arch = deck.get("archetype", "unknown")
        fmt = deck.get("format", "unknown")

        print(f"\n[{i}/5] {fmt} - {arch}")
        print("-" * 60)

        try:
            annotation = annotate_deck_quality(deck, client)

            print(f"Archetype Match: {annotation.get('archetype_match', 'error')}")
            print(f"Coherence Score: {annotation.get('coherence_score', 'error')}/10")
            print(f"Strategy: {annotation.get('actual_strategy', 'error')}")
            if annotation.get("issues"):
                print(f"Issues: {annotation.get('issues')}")

            results.append(
                {
                    "deck": {"format": fmt, "archetype": arch, "deck_id": deck.get("deck_id")},
                    "annotation": annotation,
                }
            )

        except Exception as e:
            print(f"❌ Error: {e}")
            results.append({"deck": {"format": fmt, "archetype": arch}, "error": str(e)})

    # Save results
    output_path = Path("../../annotations/test_batch_oct_3.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'=' * 60}")
    print("TEST COMPLETE")
    print(f"{'=' * 60}")
    print(f"Annotations: {len([r for r in results if 'annotation' in r])}/5 successful")
    print(f"Saved to: {output_path}")
    print()
    print("✅ If quality looks good, scale up annotation")
    print("   Next: Annotate 100 decks (~$2-3)")


if __name__ == "__main__":
    main()
