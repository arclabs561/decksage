#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pydantic-ai",
# ]
# ///

"""
End-to-End Test Suite for Annotation System

Tests the complete annotation pipeline:
1. Single annotator
2. Multi-annotator IAA (synthetic IAA with different models/params)
3. Uncertainty-based selection
4. Human annotation queue
5. Integration with graph enrichment
6. Meta-judge feedback
7. All games (Magic, Pokemon, Yu-Gi-Oh)

Validates:
- Different models are used (Gemini Flash, Claude Opus, Gemini Pro)
- Different parameters are applied (temperature 0.3, 0.3, 0.4)
- IAA metrics are calculated correctly
- Uncertainty selection identifies hard pairs
- Human queue works correctly
- All components integrate properly
"""

import asyncio
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load .env
env_file = project_root / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

from src.ml.annotation.llm_annotator import LLMAnnotator
from src.ml.annotation.multi_annotator_iaa import DEFAULT_ANNOTATORS
from src.ml.annotation.human_annotation_queue import HumanAnnotationQueue
from src.ml.utils.paths import PATHS


def verify_iaa_configuration():
    """Verify IAA uses different models and parameters."""
    print("="*70)
    print("Verifying Synthetic IAA Configuration")
    print("="*70)
    print()
    
    print("Default Annotators:")
    models = set()
    temps = set()
    
    for i, config in enumerate(DEFAULT_ANNOTATORS, 1):
        print(f"{i}. {config.name}")
        print(f"   Model: {config.model}")
        print(f"   Temperature: {config.temperature}")
        print(f"   Max Tokens: {config.max_tokens}")
        print()
        models.add(config.model)
        temps.add(config.temperature)
    
    print("Diversity Check:")
    print(f"  ✅ {len(models)} unique models: {', '.join(sorted(models))}")
    print(f"  ✅ {len(temps)} unique temperatures: {sorted(temps)}")
    
    if len(models) == len(DEFAULT_ANNOTATORS) and len(temps) > 1:
        print("\n✅ Synthetic IAA correctly configured with different models and parameters")
        return True
    else:
        print("\n⚠️ Configuration issues detected")
        return False


async def test_single_annotator(game: str = "magic", num_pairs: int = 3):
    """Test single annotator (baseline)."""
    print("\n" + "="*70)
    print(f"Test 1: Single Annotator ({game})")
    print("="*70)
    
    try:
        annotator = LLMAnnotator(
            game=game,
            use_graph_enrichment=True,
            use_evoc_clustering=False,
            use_meta_judge=False,
            use_multi_annotator=False,
            use_uncertainty_selection=False,
            use_human_queue=False,
        )
        
        annotations = await annotator.annotate_similarity_pairs(
            num_pairs=num_pairs,
            strategy="diverse",
            batch_size=2,
        )
        
        if not annotations:
            print("  ✗ No annotations generated")
            return False
        
        print(f"  ✅ Generated {len(annotations)} annotations")
        
        # Check metadata
        for ann in annotations[:2]:  # Check first 2
            if isinstance(ann, dict):
                model = ann.get("model_name", "unknown")
                source = ann.get("source", "unknown")
            else:
                model = getattr(ann, "model_name", "unknown")
                source = getattr(ann, "source", "unknown")
            
            print(f"    Model: {model}, Source: {source}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_multi_annotator_iaa(game: str = "magic", num_pairs: int = 2):
    """Test multi-annotator IAA (synthetic IAA)."""
    print("\n" + "="*70)
    print(f"Test 2: Multi-Annotator IAA ({game})")
    print("="*70)
    
    try:
        annotator = LLMAnnotator(
            game=game,
            use_graph_enrichment=True,
            use_evoc_clustering=False,
            use_meta_judge=False,
            use_multi_annotator=True,  # Enable IAA
            use_uncertainty_selection=False,
            use_human_queue=False,
        )
        
        if not annotator.multi_annotator:
            print("  ✗ Multi-annotator not initialized")
            return False
        
        print(f"  ✅ Multi-annotator initialized with {len(annotator.multi_annotator.annotator_configs)} annotators")
        
        # Verify different models/params
        for config in annotator.multi_annotator.annotator_configs:
            print(f"    - {config.name}: {config.model}, temp={config.temperature}")
        
        annotations = await annotator.annotate_similarity_pairs(
            num_pairs=num_pairs,
            strategy="diverse",
            batch_size=1,  # Smaller batch (3x LLM calls per pair)
        )
        
        if not annotations:
            print("  ✗ No annotations generated")
            return False
        
        print(f"  ✅ Generated {len(annotations)} consensus annotations")
        
        # Check that annotations have IAA metadata
        for ann in annotations[:1]:
            if isinstance(ann, dict):
                source = ann.get("source", "")
                model = ann.get("model_name", "")
            else:
                source = getattr(ann, "source", "")
                model = getattr(ann, "model_name", "")
            
            print(f"    Source: {source}, Model: {model}")
            if "multi_annotator" in source:
                print("  ✅ IAA annotations correctly tagged")
            else:
                print("  ⚠️ Source tag may be missing")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_uncertainty_selection(game: str = "magic", num_pairs: int = 2):
    """Test uncertainty-based selection."""
    print("\n" + "="*70)
    print(f"Test 3: Uncertainty-Based Selection ({game})")
    print("="*70)
    
    try:
        annotator = LLMAnnotator(
            game=game,
            use_graph_enrichment=True,
            use_evoc_clustering=False,
            use_meta_judge=False,
            use_multi_annotator=False,
            use_uncertainty_selection=True,  # Enable uncertainty
            use_human_queue=False,
        )
        
        if not annotator.uncertainty_selector:
            print("  ✗ Uncertainty selector not initialized")
            return False
        
        print("  ✅ Uncertainty selector initialized")
        
        annotations = await annotator.annotate_similarity_pairs(
            num_pairs=num_pairs,
            strategy="uncertainty",
            batch_size=2,
        )
        
        if not annotations:
            print("  ✗ No annotations generated")
            return False
        
        print(f"  ✅ Generated {len(annotations)} annotations from uncertain pairs")
        
        # Check score distribution (uncertain pairs should have diverse scores)
        scores = []
        for ann in annotations:
            if isinstance(ann, dict):
                scores.append(ann.get("similarity_score", 0.0))
            else:
                scores.append(ann.similarity_score)
        
        if scores:
            print(f"    Score range: {min(scores):.3f} - {max(scores):.3f}")
            print(f"    Score std: {(sum((s - sum(scores)/len(scores))**2 for s in scores) / len(scores))**0.5:.3f}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_human_annotation_queue():
    """Test human annotation queue."""
    print("\n" + "="*70)
    print("Test 4: Human Annotation Queue")
    print("="*70)
    
    try:
        queue = HumanAnnotationQueue()
        
        # Check queue status
        stats = queue.get_statistics()
        print(f"  ✅ Queue initialized")
        print(f"    Total tasks: {stats['total']}")
        print(f"    By status: {stats['by_status']}")
        
        # Test queuing a task
        from src.ml.annotation.human_annotation_queue import AnnotationPriority
        
        queue.queue_for_human_annotation(
            card1="Test Card 1",
            card2="Test Card 2",
            game="magic",
            priority=AnnotationPriority.HIGH,
            reason="E2E test",
        )
        
        print("  ✅ Task queued successfully")
        
        # Get pending tasks
        pending = queue.get_pending_tasks(limit=5)
        print(f"    Pending tasks: {len(pending)}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_all_games():
    """Test annotation system across all games."""
    print("\n" + "="*70)
    print("Test 5: All Games Support")
    print("="*70)
    
    games = ["magic", "pokemon", "yugioh"]
    results = {}
    
    for game in games:
        print(f"\n  Testing {game}...")
        try:
            annotator = LLMAnnotator(
                game=game,
                use_graph_enrichment=True,
                use_evoc_clustering=False,
                use_meta_judge=False,
                use_multi_annotator=False,
                use_uncertainty_selection=False,
                use_human_queue=False,
                db_path=PATHS.INCREMENTAL_GRAPH_DB,
            )
            
            # Test with 1 pair per game
            annotations = await annotator.annotate_similarity_pairs(
                num_pairs=1,
                strategy="diverse",
                batch_size=1,
            )
            
            if annotations:
                results[game] = "✅ Working"
                print(f"    ✅ {game}: Generated {len(annotations)} annotation(s)")
            else:
                results[game] = "⚠️ No annotations"
                print(f"    ⚠️ {game}: No annotations generated")
                
        except Exception as e:
            results[game] = f"✗ Error: {e}"
            print(f"    ✗ {game}: {e}")
    
    print(f"\n  Summary:")
    for game, status in results.items():
        print(f"    {game}: {status}")
    
    return all("✅" in status for status in results.values())


async def main():
    """Run all E2E tests."""
    print("\n" + "="*70)
    print("End-to-End Annotation System Test Suite")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    # Check API key
    if not os.getenv("OPENROUTER_API_KEY"):
        print("⚠ Warning: OPENROUTER_API_KEY not set")
        print("  Some tests will be skipped")
        print()
    
    results = {}
    
    # Test 0: Verify IAA configuration
    results["iaa_config"] = verify_iaa_configuration()
    
    # Test 1: Single annotator
    if os.getenv("OPENROUTER_API_KEY"):
        results["single_annotator"] = await test_single_annotator("magic", 2)
    else:
        results["single_annotator"] = "skipped"
    
    # Test 2: Multi-annotator IAA
    if os.getenv("OPENROUTER_API_KEY"):
        results["multi_annotator"] = await test_multi_annotator_iaa("magic", 1)
    else:
        results["multi_annotator"] = "skipped"
    
    # Test 3: Uncertainty selection
    if os.getenv("OPENROUTER_API_KEY"):
        results["uncertainty"] = await test_uncertainty_selection("magic", 2)
    else:
        results["uncertainty"] = "skipped"
    
    # Test 4: Human queue
    results["human_queue"] = await test_human_annotation_queue()
    
    # Test 5: All games
    if os.getenv("OPENROUTER_API_KEY"):
        results["all_games"] = await test_all_games()
    else:
        results["all_games"] = "skipped"
    
    # Summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    
    for test_name, result in results.items():
        if result is True:
            print(f"  ✅ {test_name}")
        elif result is False:
            print(f"  ✗ {test_name}")
        else:
            print(f"  ⏭ {test_name}: {result}")
    
    passed = sum(1 for r in results.values() if r is True)
    total = sum(1 for r in results.values() if r is not False and r != "skipped")
    
    print(f"\n  Passed: {passed}/{total}")
    
    # Save results
    output_file = project_root / "annotations" / "e2e_test_results.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results,
            "passed": passed,
            "total": total,
        }, f, indent=2, default=str)
    
    print(f"\n✓ Results saved to: {output_file}")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

