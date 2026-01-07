#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pydantic-ai",
# ]
# ///

"""
Test IAA and Uncertainty-Based Selection Integration

Validates that:
1. Multi-annotator IAA system works correctly
2. Uncertainty-based selection identifies hard pairs
3. Integration with LLMAnnotator works end-to-end
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.ml.annotation.llm_annotator import LLMAnnotator
from src.ml.annotation.multi_annotator_iaa import MultiAnnotatorIAA
from src.ml.annotation.uncertainty_based_selection import UncertaintyBasedSelector


async def test_multi_annotator_iaa():
    """Test multi-annotator IAA system."""
    print("\n" + "=" * 60)
    print("Testing Multi-Annotator IAA System")
    print("=" * 60)
    
    try:
        multi_iaa = MultiAnnotatorIAA(
            annotator_configs=None,  # Use defaults
            min_iaa_threshold=0.6,
            use_consensus=True,
        )
        print("✓ MultiAnnotatorIAA initialized")
        
        # Test with a simple pair
        result = await multi_iaa.annotate_pair_multi(
            card1="Lightning Bolt",
            card2="Shock",
            graph_context="Graph: Jaccard=0.45, Co-occurrence=120",
        )
        
        print(f"✓ Multi-annotator annotation completed")
        print(f"  Card1: {result.card1}")
        print(f"  Card2: {result.card2}")
        print(f"  Annotators: {len(result.annotations)}")
        print(f"  Consensus: {result.consensus_annotation is not None}")
        print(f"  IAA Metrics:")
        print(f"    Krippendorff's Alpha: {result.iaa_metrics.get('krippendorff_alpha', 0.0):.3f}")
        print(f"    Score Alpha: {result.iaa_metrics.get('score_alpha', 0.0):.3f}")
        print(f"    Type Alpha: {result.iaa_metrics.get('type_alpha', 0.0):.3f}")
        print(f"    Agreement Level: {result.agreement_level}")
        
        # Show individual annotations
        print(f"\n  Individual Annotations:")
        for name, ann in result.annotations.items():
            print(f"    {name}: score={ann.similarity_score:.3f}, type={ann.similarity_type}")
        
        if result.consensus_annotation:
            print(f"\n  Consensus: score={result.consensus_annotation.similarity_score:.3f}, type={result.consensus_annotation.similarity_type}")
        
        return True
    except Exception as e:
        print(f"✗ Multi-annotator IAA test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_uncertainty_selection():
    """Test uncertainty-based selection."""
    print("\n" + "=" * 60)
    print("Testing Uncertainty-Based Selection")
    print("=" * 60)
    
    try:
        from src.ml.annotation.lazy_graph_enricher import LazyGraphEnricher
        from src.ml.utils.paths import PATHS
        
        # Initialize graph enricher if available
        graph_enricher = None
        if PATHS.incremental_graph_db.exists():
            graph_enricher = LazyGraphEnricher(PATHS.incremental_graph_db, game="magic")
            print("✓ Graph enricher initialized")
        else:
            print("⚠ Graph DB not found, testing without graph features")
        
        selector = UncertaintyBasedSelector(
            graph_enricher=graph_enricher,
            embedding_models=None,  # Can add embedding models later
        )
        print("✓ UncertaintyBasedSelector initialized")
        
        # Test with some candidate pairs
        candidate_pairs = [
            ("Lightning Bolt", "Shock"),
            ("Counterspell", "Mana Leak"),
            ("Black Lotus", "Mox Pearl"),
            ("Lightning Bolt", "Black Lotus"),  # Very different
        ]
        
        print(f"\n  Computing uncertainty for {len(candidate_pairs)} pairs...")
        uncertainties = []
        for card1, card2 in candidate_pairs:
            uncertainty = selector.compute_uncertainty(card1, card2)
            uncertainties.append(uncertainty)
            print(f"    {card1} vs {card2}: uncertainty={uncertainty.uncertainty_score:.3f} ({uncertainty.uncertainty_type})")
        
        # Select most uncertain pairs
        selected = selector.select_uncertain_pairs(
            candidate_pairs,
            top_k=2,
            min_uncertainty=0.0,  # Low threshold for testing
        )
        
        print(f"\n  Selected {len(selected)} uncertain pairs:")
        for u in selected:
            print(f"    {u.card1} vs {u.card2}: {u.uncertainty_score:.3f} ({u.uncertainty_type})")
        
        return True
    except Exception as e:
        print(f"✗ Uncertainty selection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_llm_annotator_integration():
    """Test LLMAnnotator with IAA and uncertainty selection."""
    print("\n" + "=" * 60)
    print("Testing LLMAnnotator Integration")
    print("=" * 60)
    
    try:
        # Test with uncertainty selection
        print("\n1. Testing with uncertainty-based selection:")
        annotator_uncertainty = LLMAnnotator(
            game="magic",
            use_graph_enrichment=True,
            use_evoc_clustering=False,  # Skip for speed
            use_meta_judge=False,  # Skip for speed
            use_multi_annotator=False,
            use_uncertainty_selection=True,
        )
        print("✓ LLMAnnotator initialized with uncertainty selection")
        
        # Test with multi-annotator
        print("\n2. Testing with multi-annotator IAA:")
        annotator_iaa = LLMAnnotator(
            game="magic",
            use_graph_enrichment=True,
            use_evoc_clustering=False,
            use_meta_judge=False,
            use_multi_annotator=True,
            use_uncertainty_selection=False,
        )
        print("✓ LLMAnnotator initialized with multi-annotator IAA")
        
        # Test annotation with uncertainty selection (small batch)
        print("\n3. Generating annotations with uncertainty selection (2 pairs):")
        annotations_uncertainty = await annotator_uncertainty.annotate_similarity_pairs(
            num_pairs=2,
            strategy="uncertainty",
            batch_size=2,
        )
        print(f"✓ Generated {len(annotations_uncertainty)} annotations with uncertainty selection")
        for ann in annotations_uncertainty:
            if isinstance(ann, dict):
                print(f"  {ann.get('card1')} vs {ann.get('card2')}: score={ann.get('similarity_score', 0.0):.3f}")
            else:
                print(f"  {ann.card1} vs {ann.card2}: score={ann.similarity_score:.3f}")
        
        # Test annotation with multi-annotator (small batch)
        print("\n4. Generating annotations with multi-annotator IAA (2 pairs):")
        annotations_iaa = await annotator_iaa.annotate_similarity_pairs(
            num_pairs=2,
            strategy="diverse",
            batch_size=2,
        )
        print(f"✓ Generated {len(annotations_iaa)} annotations with multi-annotator IAA")
        for ann in annotations_iaa:
            if isinstance(ann, dict):
                print(f"  {ann.get('card1')} vs {ann.get('card2')}: score={ann.get('similarity_score', 0.0):.3f}, source={ann.get('source', 'unknown')}")
            else:
                print(f"  {ann.card1} vs {ann.card2}: score={ann.similarity_score:.3f}, source={ann.source}")
        
        return True
    except Exception as e:
        print(f"✗ LLMAnnotator integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("IAA and Uncertainty Selection Integration Tests")
    print("=" * 60)
    
    results = []
    
    # Test 1: Multi-annotator IAA
    results.append(await test_multi_annotator_iaa())
    
    # Test 2: Uncertainty selection
    results.append(await test_uncertainty_selection())
    
    # Test 3: Integration
    results.append(await test_llm_annotator_integration())
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Multi-Annotator IAA: {'✓ PASS' if results[0] else '✗ FAIL'}")
    print(f"Uncertainty Selection: {'✓ PASS' if results[1] else '✗ FAIL'}")
    print(f"LLMAnnotator Integration: {'✓ PASS' if results[2] else '✗ FAIL'}")
    
    if all(results):
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

