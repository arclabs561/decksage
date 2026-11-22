#!/usr/bin/env python3
"""
Quick test of LLM annotation system with OpenRouter.
Creates a small batch of annotations to verify setup works.
"""

import asyncio
import json
import sys

from ..annotation.llm_annotator import HAS_PYDANTIC_AI, LLMAnnotator


async def quick_test():
    """Run quick annotation test."""
    if not HAS_PYDANTIC_AI:
        print("Error: pydantic-ai not installed")
        print("Install: pip install pydantic-ai python-dotenv")
        return 1
    # Load .env
    import os
    from pathlib import Path

    from dotenv import load_dotenv

    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        print(f"✓ Loaded .env from {env_file}")
    else:
        print(f"Warning: No .env found at {env_file}")
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Error: OPENROUTER_API_KEY not found in environment")
        return 1
    print("✓ OPENROUTER_API_KEY found")
    print()
    # Initialize annotator
    annotator = LLMAnnotator()
    print("=" * 60)
    print("QUICK TEST: 5 similarity annotations")
    print("=" * 60)
    print()
    # Test similarity annotations (small batch)
    similarity = await annotator.annotate_similarity_pairs(num_pairs=5, strategy="diverse")
    print("\n" + "=" * 60)
    print("RESULTS:")
    print("=" * 60)
    if len(similarity) != 5:
        print(f"Expected five annotations, got {len(similarity)}")
        return 1
    for i, ann in enumerate(similarity, 1):
        print(f"\n{i}. {ann.card1} vs {ann.card2}")
        print(f" Similarity: {ann.similarity_score:.2f} ({ann.similarity_type})")
        print(f" Is substitute: {ann.is_substitute}")
        print(f" Reasoning: {ann.reasoning[:100]}...")
    print("\n" + "=" * 60)
    print(f" Created {len(similarity)} annotations successfully!")
    print("=" * 60)
    # Save test results
    output_file = annotator.output_dir / "test_annotations.json"
    with open(output_file, "w") as f:
        json.dump([a.model_dump() for a in similarity], f, indent=2)
    print(f"\nSaved to: {output_file}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(quick_test()))
