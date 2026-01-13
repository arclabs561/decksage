#!/usr/bin/env python3
"""
Validate agent topology improvements.

Tests:
1. Error handling and fallbacks
2. Timeout handling
3. Integration with LLMAnnotator
4. Performance characteristics
"""

import asyncio
import sys
import time
from pathlib import Path


project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from ml.utils.path_setup import setup_project_paths


setup_project_paths()

from src.ml.annotation.agent_topology import create_annotation_topology
from src.ml.annotation.llm_annotator import LLMAnnotator


async def test_error_handling():
    """Test error handling and fallbacks."""
    print("=" * 80)
    print("TESTING ERROR HANDLING")
    print("=" * 80)

    topology = create_annotation_topology(
        game="magic",
        use_specialists=True,
        use_validator=True,
        use_supervisor=True,
    )

    # Test with invalid cards (should still work with fallbacks)
    test_cases = [
        ("Lightning Bolt", "Shock"),  # Valid
        ("Invalid Card 1", "Invalid Card 2"),  # Invalid (tests fallback)
    ]

    for card1, card2 in test_cases:
        print(f"\n--- {card1} vs {card2} ---")
        try:
            start = time.time()
            ann = await topology.annotate(card1, card2, game="magic", timeout=30.0)
            elapsed = time.time() - start
            print(f"  ✓ Success: score={ann.similarity_score:.2f}, time={elapsed:.1f}s")
        except Exception as e:
            print(f"  ✗ Failed: {e}")


async def test_timeout_handling():
    """Test timeout handling."""
    print("\n" + "=" * 80)
    print("TESTING TIMEOUT HANDLING")
    print("=" * 80)

    topology = create_annotation_topology(
        game="magic",
        use_specialists=True,
        use_validator=True,
        use_supervisor=True,
        router_timeout=1.0,  # Short timeout
        validator_timeout=1.0,
        supervisor_timeout=1.0,
    )

    try:
        start = time.time()
        ann = await topology.annotate("Lightning Bolt", "Shock", game="magic", timeout=5.0)
        elapsed = time.time() - start
        print(f"  ✓ Completed in {elapsed:.1f}s (with short timeouts)")
    except TimeoutError:
        print("  ✗ Timeout (expected with very short timeouts)")
    except Exception as e:
        print(f"  ✗ Error: {e}")


async def test_integration():
    """Test integration with LLMAnnotator."""
    print("\n" + "=" * 80)
    print("TESTING LLMANNOTATOR INTEGRATION")
    print("=" * 80)

    try:
        annotator = LLMAnnotator(
            game="magic",
            use_agent_topology=True,
            use_graph_enrichment=True,
            use_meta_judge=False,  # Disable to isolate topology
        )

        print("  ✓ LLMAnnotator initialized with topology")

        # Test annotation
        print("\n  Testing annotation...")
        start = time.time()
        ann = await annotator.annotate_pair("Lightning Bolt", "Shock", {})
        elapsed = time.time() - start

        if ann:
            print(
                f"  ✓ Annotation generated: score={ann.similarity_score if hasattr(ann, 'similarity_score') else 'N/A':.2f}, time={elapsed:.1f}s"
            )
        else:
            print("  ✗ Annotation returned None")
    except Exception as e:
        print(f"  ✗ Integration failed: {e}")
        import traceback

        traceback.print_exc()


async def test_performance():
    """Test performance characteristics."""
    print("\n" + "=" * 80)
    print("TESTING PERFORMANCE")
    print("=" * 80)

    test_pairs = [
        ("Lightning Bolt", "Shock"),
        ("Path to Exile", "Swords to Plowshares"),
    ]

    # Test with topology
    print("\n--- With Topology ---")
    topology = create_annotation_topology(
        game="magic",
        use_specialists=True,
        use_validator=True,
        use_supervisor=True,
    )

    topology_times = []
    for card1, card2 in test_pairs:
        try:
            start = time.time()
            ann = await topology.annotate(card1, card2, game="magic")
            elapsed = time.time() - start
            topology_times.append(elapsed)
            print(f"  {card1} vs {card2}: {elapsed:.1f}s")
        except Exception as e:
            print(f"  {card1} vs {card2}: Error - {e}")

    if topology_times:
        print(f"  Average: {sum(topology_times) / len(topology_times):.1f}s")

    # Test without topology (direct)
    print("\n--- Without Topology (Direct) ---")
    annotator = LLMAnnotator(
        game="magic",
        use_agent_topology=False,
        use_graph_enrichment=True,
        use_meta_judge=False,
    )

    direct_times = []
    for card1, card2 in test_pairs:
        try:
            start = time.time()
            ann = await annotator.annotate_pair(card1, card2, {})
            elapsed = time.time() - start
            direct_times.append(elapsed)
            print(f"  {card1} vs {card2}: {elapsed:.1f}s")
        except Exception as e:
            print(f"  {card1} vs {card2}: Error - {e}")

    if direct_times:
        print(f"  Average: {sum(direct_times) / len(direct_times):.1f}s")

    if topology_times and direct_times:
        overhead = (sum(topology_times) / len(topology_times)) - (
            sum(direct_times) / len(direct_times)
        )
        print(f"\n  Topology overhead: {overhead:+.1f}s")


async def main():
    """Run all validation tests."""
    print("🧪 Validating Agent Topology Improvements")
    print()

    try:
        await test_error_handling()
        await test_timeout_handling()
        await test_integration()
        await test_performance()

        print("\n" + "=" * 80)
        print("✅ VALIDATION COMPLETE")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
