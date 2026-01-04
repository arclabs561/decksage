#!/usr/bin/env python3
"""
Tests for evaluation functions.
"""

import pytest
from pathlib import Path
import sys

# Add src to path
src_dir = Path(__file__).parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


def test_evaluate_embedding_basic():
    """Test basic embedding evaluation."""
    try:
        from gensim.models import KeyedVectors
        from ml.scripts.evaluate_all_embeddings import evaluate_embedding
        
        # Create minimal test set
        test_set = {
            "Lightning Bolt": {
                "highly_relevant": ["Shock"],
                "relevant": ["Bolt"],
            }
        }
        
        # This test requires an actual embedding, so we'll skip if not available
        embedding_path = Path("data/embeddings/multitask_embeddings.wv")
        if not embedding_path.exists():
            pytest.skip("Embedding not found")
        
        embedding = KeyedVectors.load(str(embedding_path))
        
        # Check if test query is in vocabulary
        if "Lightning Bolt" not in embedding:
            pytest.skip("Test query not in embedding vocabulary")
        
        result = evaluate_embedding(embedding, test_set, top_k=10, verbose=False)
        
        assert "p@10" in result
        assert "mrr" in result
        assert "num_evaluated" in result
        assert result["p@10"] >= 0.0
        assert result["p@10"] <= 1.0
        
    except ImportError:
        pytest.skip("gensim not available")


def test_evaluate_embedding_coverage():
    """Test that evaluation reports vocabulary coverage."""
    try:
        from gensim.models import KeyedVectors
        from ml.scripts.evaluate_all_embeddings import evaluate_embedding
        
        test_set = {
            "Lightning Bolt": {
                "highly_relevant": ["Shock"],
            },
            "Nonexistent Card": {
                "highly_relevant": ["Other"],
            }
        }
        
        embedding_path = Path("data/embeddings/multitask_embeddings.wv")
        if not embedding_path.exists():
            pytest.skip("Embedding not found")
        
        embedding = KeyedVectors.load(str(embedding_path))
        
        result = evaluate_embedding(embedding, test_set, top_k=10, verbose=False)
        
        assert "vocab_coverage" in result
        assert "found_in_vocab" in result["vocab_coverage"]
        assert "not_in_vocab" in result["vocab_coverage"]
        
    except ImportError:
        pytest.skip("gensim not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

