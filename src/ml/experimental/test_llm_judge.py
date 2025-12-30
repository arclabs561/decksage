#!/usr/bin/env python3
"""Quick test of LLM judge v2 with Pydantic AI + OpenAI"""

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from llm_judge import LLMJudge

# Test queries based on existing data
test_queries = {
    "Lightning Bolt": [
        ("Chain Lightning", 0.847),
        ("Fireblast", 0.831),
        ("Lava Dart", 0.825),
        ("Kessig Flamebreather", 0.839),
        ("Burning-Tree Emissary", 0.831),
    ],
    "Brainstorm": [
        ("Ponder", 0.892),
        ("Preordain", 0.850),
        ("Necropotence", 0.846),
        ("Scroll of Fate", 0.875),
        ("Tundra", 0.828),
    ],
    "Dark Ritual": [
        ("Cabal Ritual", 0.817),
        ("Balustrade Spy", 0.845),
        ("Undercity Informer", 0.833),
        ("Innocent Blood", 0.807),
        ("Lotus Petal", 0.800),
    ],
}


def main():
    print("🧪 Testing LLM Judge v2 (Pydantic AI + OpenAI)\n")
    print("=" * 70)

    try:
        judge = LLMJudge()
        print("✅ LLM Judge initialized\n")
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        print("\nMake sure OPENROUTER_API_KEY is set in .env")
        return 1

    for query_card, predictions in test_queries.items():
        print(f"\n📌 Evaluating: {query_card}")
        print("-" * 70)

        try:
            result = judge.evaluate_similarity(
                query_card=query_card, similar_cards=predictions, context="Magic: The Gathering"
            )

            print(f"Quality Score: {result.get('overall_quality', 'N/A')}/10")
            print(f"\nAnalysis: {result.get('analysis', 'N/A')}")

            if result.get("card_ratings"):
                print("\nCard Ratings:")
                for rating in result["card_ratings"][:3]:  # Top 3
                    print(f"  • {rating['card']}: {rating['relevance']}/4")
                    print(f"    Reasoning: {rating.get('reasoning', 'N/A')[:80]}...")

            if result.get("issues"):
                print(f"\n⚠️  Issues: {', '.join(result['issues'][:2])}")

            if result.get("missing_cards"):
                print(f"\n🔍 Missing: {', '.join(result['missing_cards'][:3])}")

        except Exception as e:
            print(f"❌ Evaluation failed: {e}")
            import traceback
            traceback.print_exc()
            continue

    print("\n" + "=" * 70)
    print("✅ LLM Judge v2 test complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
