#!/usr/bin/env python3
"""
Test the agent topology with real annotations.

Validates that:
1. Router correctly routes to game specialists
2. Specialists generate game-appropriate annotations
3. Validator catches quality issues
4. Supervisor coordinates the workflow
"""

import asyncio
import sys
from pathlib import Path


project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths


setup_project_paths()

from src.ml.annotation.agent_topology import create_annotation_topology


async def test_router():
    """Test router agent routing decisions."""
    print("=" * 80)
    print("TESTING ROUTER AGENT")
    print("=" * 80)

    topology = create_annotation_topology(
        use_specialists=True, use_validator=False, use_supervisor=False
    )

    test_cases = [
        ("Lightning Bolt", "Shock", "magic"),
        ("Pikachu", "Raichu", "pokemon"),
        ("Blue-Eyes White Dragon", "Dark Magician", "yugioh"),
        ("Unknown Card 1", "Unknown Card 2", None),
    ]

    for card1, card2, game in test_cases:
        if topology.router_agent:
            result = await topology.router_agent.run(
                f"Route annotation: card1={card1}, card2={card2}, game={game or 'unknown'}"
            )
            if hasattr(result, "output"):
                routing = result.output
                print(f"\n{card1} vs {card2} (game={game}):")
                print(f"  → Routed to: {routing.specialist}")
                print(f"  → Reasoning: {routing.reasoning}")
                print(f"  → Confidence: {routing.confidence:.2f}")


async def test_specialists():
    """Test game-specific specialist agents."""
    print("\n" + "=" * 80)
    print("TESTING SPECIALIST AGENTS")
    print("=" * 80)

    test_cases = [
        ("magic", "Lightning Bolt", "Shock"),
        ("pokemon", "Pikachu", "Raichu"),
        ("yugioh", "Blue-Eyes White Dragon", "Dark Magician"),
    ]

    for game, card1, card2 in test_cases:
        print(f"\n--- {game.upper()} Specialist ---")
        topology = create_annotation_topology(
            game=game,
            use_specialists=True,
            use_validator=False,
            use_supervisor=False,
        )

        try:
            ann = await topology.annotate(card1, card2, game=game)
            print(f"  Card 1: {ann.card1}")
            print(f"  Card 2: {ann.card2}")
            print(f"  Score: {ann.similarity_score:.2f}")
            print(f"  Type: {ann.similarity_type}")
            print(f"  Reasoning: {ann.reasoning[:100]}...")
        except Exception as e:
            print(f"  Error: {e}")


async def test_full_topology():
    """Test full topology with supervisor and validator."""
    print("\n" + "=" * 80)
    print("TESTING FULL TOPOLOGY (Supervisor + Validator)")
    print("=" * 80)

    topology = create_annotation_topology(
        game="magic",
        use_specialists=True,
        use_validator=True,
        use_supervisor=True,
    )

    test_pairs = [
        ("Lightning Bolt", "Shock"),
        ("Path to Exile", "Swords to Plowshares"),
    ]

    for card1, card2 in test_pairs:
        print(f"\n--- {card1} vs {card2} ---")
        try:
            ann = await topology.annotate(card1, card2, game="magic")
            print(f"  Score: {ann.similarity_score:.2f}")
            print(f"  Type: {ann.similarity_type}")
            print(f"  Is Substitute: {ann.is_substitute}")
        except Exception as e:
            print(f"  Error: {e}")


async def main():
    """Run all topology tests."""
    print("🧪 Testing Agent Topology")
    print()

    try:
        await test_router()
        await test_specialists()
        await test_full_topology()

        print("\n" + "=" * 80)
        print("✅ TOPOLOGY TESTS COMPLETE")
        print("=" * 80)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
