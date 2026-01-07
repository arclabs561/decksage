#!/usr/bin/env python3
"""
Quick test script to verify visual embeddings work.

Run this to quickly verify the system is working.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from ml.utils.path_setup import setup_project_paths
    setup_project_paths()
except ImportError:
    src_path = project_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))

def quick_test():
    """Quick test of visual embeddings."""
    print("=" * 60)
    print("Quick Visual Embeddings Test")
    print("=" * 60)
    print()
    
    # Test 1: Import
    print("1. Testing imports...")
    try:
        from ml.similarity.visual_embeddings import CardVisualEmbedder, get_visual_embedder
        from ml.similarity.fusion import FusionWeights
        print("   ✓ Imports successful")
    except ImportError as e:
        print(f"   ✗ Import failed: {e}")
        print("   Install with: uv add sentence-transformers pillow requests transformers sentencepiece")
        return False
    
    # Test 2: Initialize
    print("\n2. Testing initialization...")
    try:
        embedder = get_visual_embedder()
        print(f"   ✓ Embedder initialized: {embedder.model_name}")
    except Exception as e:
        print(f"   ✗ Initialization failed: {e}")
        return False
    
    # Test 3: Embedding generation
    print("\n3. Testing embedding generation...")
    try:
        from PIL import Image
        img = Image.new("RGB", (224, 224), color="red")
        embedding = embedder.embed_card(img)
        print(f"   ✓ Embedding generated: shape {embedding.shape}")
    except Exception as e:
        print(f"   ✗ Embedding generation failed: {e}")
        return False
    
    # Test 4: Fusion weights
    print("\n4. Testing fusion weights...")
    try:
        weights = FusionWeights()
        assert hasattr(weights, "visual_embed")
        print(f"   ✓ Fusion weights include visual_embed: {weights.visual_embed}")
    except Exception as e:
        print(f"   ✗ Fusion weights test failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✅ All quick tests passed!")
    print("=" * 60)
    print("\nVisual embeddings are working correctly.")
    print("To use in API, set VISUAL_EMBEDDER_MODEL environment variable.")
    
    return True

if __name__ == "__main__":
    success = quick_test()
    sys.exit(0 if success else 1)

