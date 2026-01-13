#!/usr/bin/env python3
"""
Test agent topology with real annotation generation.

This script:
1. Generates real annotations using the topology
2. Analyzes behavior and quality
3. Identifies issues and refinement opportunities
"""

import asyncio
import json
import sys
from pathlib import Path


project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths


setup_project_paths()

from src.ml.annotation.llm_annotator import LLMAnnotator


async def test_topology_vs_direct(game: str = "magic", num_pairs: int = 5):
    """Compare topology vs direct annotation."""
    print("=" * 80)
    print(f"TESTING TOPOLOGY VS DIRECT: {game.upper()}")
    print("=" * 80)

    test_pairs = [
        ("Lightning Bolt", "Shock"),
        ("Path to Exile", "Swords to Plowshares"),
        ("Counterspell", "Mana Leak"),
        ("Lightning Bolt", "Counterspell"),  # Different functions
        ("Brainstorm", "Ponder"),
    ]

    # Test with topology
    print("\n--- WITH TOPOLOGY ---")
    annotator_topology = LLMAnnotator(
        game=game,
        use_agent_topology=True,
        use_graph_enrichment=True,
        use_meta_judge=False,  # Disable to isolate topology effects
    )

    topology_results = []
    for card1, card2 in test_pairs[:num_pairs]:
        print(f"\n  {card1} vs {card2} (topology)...")
        try:
            ann = await annotator_topology.annotate_pair(card1, card2, {})
            if ann:
                topology_results.append(
                    {
                        "card1": card1,
                        "card2": card2,
                        "score": ann.similarity_score
                        if hasattr(ann, "similarity_score")
                        else ann.get("similarity_score", 0.0),
                        "type": ann.similarity_type
                        if hasattr(ann, "similarity_type")
                        else ann.get("similarity_type", "unknown"),
                        "reasoning": ann.reasoning[:100]
                        if hasattr(ann, "reasoning")
                        else ann.get("reasoning", "")[:100],
                    }
                )
                print(
                    f"    Score: {topology_results[-1]['score']:.2f}, Type: {topology_results[-1]['type']}"
                )
        except Exception as e:
            print(f"    Error: {e}")

    # Test without topology (direct)
    print("\n--- WITHOUT TOPOLOGY (DIRECT) ---")
    annotator_direct = LLMAnnotator(
        game=game,
        use_agent_topology=False,
        use_graph_enrichment=True,
        use_meta_judge=False,
    )

    direct_results = []
    for card1, card2 in test_pairs[:num_pairs]:
        print(f"\n  {card1} vs {card2} (direct)...")
        try:
            ann = await annotator_direct.annotate_pair(card1, card2, {})
            if ann:
                direct_results.append(
                    {
                        "card1": card1,
                        "card2": card2,
                        "score": ann.similarity_score
                        if hasattr(ann, "similarity_score")
                        else ann.get("similarity_score", 0.0),
                        "type": ann.similarity_type
                        if hasattr(ann, "similarity_type")
                        else ann.get("similarity_type", "unknown"),
                        "reasoning": ann.reasoning[:100]
                        if hasattr(ann, "reasoning")
                        else ann.get("reasoning", "")[:100],
                    }
                )
                print(
                    f"    Score: {direct_results[-1]['score']:.2f}, Type: {direct_results[-1]['type']}"
                )
        except Exception as e:
            print(f"    Error: {e}")

    # Compare results
    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)

    for i, (card1, card2) in enumerate(test_pairs[:num_pairs]):
        if i < len(topology_results) and i < len(direct_results):
            top = topology_results[i]
            direct = direct_results[i]
            diff = top["score"] - direct["score"]
            print(f"\n{card1} vs {card2}:")
            print(f"  Topology: {top['score']:.2f} ({top['type']})")
            print(f"  Direct:   {direct['score']:.2f} ({direct['type']})")
            print(f"  Diff:     {diff:+.2f}")

    # Analyze score distribution
    if topology_results and direct_results:
        top_scores = [r["score"] for r in topology_results]
        direct_scores = [r["score"] for r in direct_results]

        print("\nScore Statistics:")
        print(
            f"  Topology: mean={sum(top_scores) / len(top_scores):.2f}, range=[{min(top_scores):.2f}, {max(top_scores):.2f}]"
        )
        print(
            f"  Direct:   mean={sum(direct_scores) / len(direct_scores):.2f}, range=[{min(direct_scores):.2f}, {max(direct_scores):.2f}]"
        )


async def analyze_topology_behavior():
    """Analyze topology behavior and identify issues."""
    print("\n" + "=" * 80)
    print("TOPOLOGY BEHAVIOR ANALYSIS")
    print("=" * 80)

    from src.ml.annotation.agent_topology import create_annotation_topology

    topology = create_annotation_topology(
        game="magic",
        use_specialists=True,
        use_validator=True,
        use_supervisor=True,
    )

    # Test router
    print("\n1. Router Behavior:")
    if topology.router_agent:
        test_cases = [
            ("Lightning Bolt", "Shock", "magic"),
            ("Pikachu", "Raichu", "pokemon"),
            ("Unknown1", "Unknown2", None),
        ]
        for card1, card2, game in test_cases:
            result = await topology.router_agent.run(
                f"Route: card1={card1}, card2={card2}, game={game or 'unknown'}"
            )
            if hasattr(result, "output"):
                routing = result.output
                print(
                    f"  {card1} vs {card2} (game={game}): → {routing.specialist} (confidence: {routing.confidence:.2f})"
                )

    # Test specialist selection
    print("\n2. Specialist Selection:")
    for game in ["magic", "pokemon", "yugioh"]:
        specialist = topology.specialist_agents.get(game)
        if specialist:
            print(f"  {game}: ✓ Available")
        else:
            print(f"  {game}: ✗ Missing")

    # Test validator
    print("\n3. Validator Behavior:")
    if topology.validator_agent:
        # Create a test annotation
        test_annotation = {
            "card1": "Lightning Bolt",
            "card2": "Shock",
            "similarity_score": 0.2,  # Potentially too low
            "reasoning": "Both are red instant burn spells",
            "thinking": "They have the same function",
        }
        result = await topology.validator_agent.run(f"Validate: {json.dumps(test_annotation)}")
        if hasattr(result, "output"):
            validation = result.output
            print(f"  Is Valid: {validation.is_valid}")
            print(f"  Quality: {validation.quality_score:.2f}")
            if validation.issues:
                print(f"  Issues: {validation.issues}")
            if validation.suggestions:
                print(f"  Suggestions: {validation.suggestions}")


async def main():
    """Run topology tests and analysis."""
    print("🧪 Testing Agent Topology Through Real Use")
    print()

    try:
        # Test topology vs direct
        await test_topology_vs_direct(game="magic", num_pairs=3)

        # Analyze behavior
        await analyze_topology_behavior()

        print("\n" + "=" * 80)
        print("✅ ANALYSIS COMPLETE")
        print("=" * 80)
        print("\nNext steps:")
        print("  1. Review score differences between topology and direct")
        print("  2. Check if router correctly routes to specialists")
        print("  3. Validate that validator catches quality issues")
        print("  4. Refine based on findings")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
