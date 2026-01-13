#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-ai",
# ]
# ///

"""
Test script for agentic meta-judge with multi-round conversations.

Demonstrates:
1. Multi-round annotation with feedback
2. Dynamic feedback injection via conversation history
3. IAA moderation and consensus building
"""

import asyncio
import sys
from pathlib import Path


# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from ml.annotation.agentic_meta_judge import AgenticMetaJudge
from ml.annotation.llm_annotator import CardSimilarityAnnotation


async def test_agentic_meta_judge():
    """Test the agentic meta-judge system."""
    print("=" * 70)
    print("Testing Agentic Meta-Judge with Multi-Round Conversations")
    print("=" * 70)

    # Create meta-judge
    meta_judge = AgenticMetaJudge(
        model="anthropic/claude-sonnet-4.5",
        max_rounds=3,
        min_consensus_threshold=0.7,
        min_quality_threshold=0.6,
    )

    # Simulate initial annotations from multiple annotators
    # In practice, these would come from MultiAnnotatorIAA
    initial_annotations = {
        "annotator_1": CardSimilarityAnnotation(
            card1="Lightning Bolt",
            card2="Chain Lightning",
            similarity_score=0.85,
            similarity_type="functional",
            reasoning="Both are 1-mana red instant burn spells dealing 3 damage. Near-identical function.",
            thinking="Step 1: Function - both removal/burn. Step 2: Attributes - both 1R instant. Step 3: Graph - high Jaccard. Step 4: Score - 0.85 (near-identical).",
        ),
        "annotator_2": CardSimilarityAnnotation(
            card1="Lightning Bolt",
            card2="Chain Lightning",
            similarity_score=0.75,
            similarity_type="functional",
            reasoning="Similar function but Chain Lightning has different targeting restrictions.",
            thinking="Step 1: Function - both burn. Step 2: Attributes - similar but not identical. Step 3: Graph - high co-occurrence. Step 4: Score - 0.75 (very similar but not identical).",
        ),
        "annotator_3": CardSimilarityAnnotation(
            card1="Lightning Bolt",
            card2="Chain Lightning",
            similarity_score=0.90,
            similarity_type="functional",
            reasoning="Near-identical cards, both 1-mana red instant burn dealing 3 damage.",
            thinking="Step 1: Function - identical. Step 2: Attributes - nearly identical. Step 3: Graph - very high Jaccard. Step 4: Score - 0.90 (near-identical substitutes).",
        ),
    }

    print("\n📝 Initial Annotations:")
    for annotator_id, ann in initial_annotations.items():
        print(f"  {annotator_id}: Score {ann.similarity_score:.2f} - {ann.reasoning[:60]}...")

    # Run multi-round moderation
    print("\n🔄 Running Multi-Round Moderation...")
    final_round, all_rounds = await meta_judge.moderate_multi_round(initial_annotations)

    # Display results
    print("\n" + "=" * 70)
    print("Results")
    print("=" * 70)

    for round_data in all_rounds:
        print(f"\n📊 Round {round_data.round_number}:")
        if round_data.meta_judge_feedback:
            print("  Individual Feedback:")
            for annotator_id, feedback in round_data.meta_judge_feedback.items():
                print(f"    {annotator_id}:")
                print(f"      Quality: {feedback.quality_score:.2f}")
                print(f"      Should Revise: {feedback.should_revise}")
                if feedback.issues:
                    print(f"      Issues: {', '.join(feedback.issues)}")
                if feedback.suggestions:
                    print(f"      Suggestions: {', '.join(feedback.suggestions)}")

        if round_data.consensus_decision:
            print("\n  Consensus Decision:")
            print(f"    Consensus Reached: {round_data.consensus_decision.consensus_reached}")
            print(f"    Consensus Score: {round_data.consensus_decision.consensus_score:.2f}")
            print(f"    Quality Acceptable: {round_data.consensus_decision.quality_acceptable}")
            print(f"    Recommended Action: {round_data.consensus_decision.recommended_action}")
            print(f"    Feedback: {round_data.consensus_decision.feedback_for_round[:100]}...")

    print("\n" + "=" * 70)
    print("✅ Test Complete")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_agentic_meta_judge())
