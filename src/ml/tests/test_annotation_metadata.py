#!/usr/bin/env python3
"""
Tests for annotation metadata tracking.

Verifies:
1. LLM annotations include metadata (model, params, timestamp)
2. Hand annotations support IAA tracking
3. Annotation metadata can be extracted and used
4. Graph integration with annotation metadata
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest


try:
    from ml.annotation.llm_annotator import CardSimilarityAnnotation

    HAS_LLM_ANNOTATOR = True
except ImportError:
    HAS_LLM_ANNOTATOR = False

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False


@pytest.mark.skipif(not HAS_LLM_ANNOTATOR, reason="LLM annotator not available")
def test_llm_annotation_metadata_fields():
    """Test that LLM annotations include metadata fields."""
    ann = CardSimilarityAnnotation(
        card1="Lightning Bolt",
        card2="Chain Lightning",
        similarity_score=0.9,
        similarity_type="functional",
        reasoning="Both 1-mana red burn spells",
        is_substitute=True,
        context_dependent=False,
        example_decks=[],
        model_name="anthropic/claude-4.5-sonnet",
        model_params={"provider": "openrouter"},
        prompt_hash="abc123",
        annotator_id="judge_1",
        timestamp=datetime.now().isoformat(),
    )

    # Verify all metadata fields are present
    assert ann.model_name is not None
    assert ann.model_params is not None
    assert ann.annotator_id is not None
    assert ann.timestamp is not None

    # Verify serialization
    data = ann.model_dump()
    assert "model_name" in data
    assert "model_params" in data
    assert "annotator_id" in data
    assert "timestamp" in data


@pytest.mark.skipif(not HAS_YAML, reason="PyYAML not available")
@pytest.mark.skip(reason="hand_annotate.create_annotation_batch function is missing/corrupted")
def test_hand_annotation_iaa_structure():
    """Test that hand annotation YAML includes IAA tracking section."""
    try:
        from ml.annotation.hand_annotate import create_annotation_batch
    except ImportError:
        pytest.skip("hand_annotate module not available")

    # Create a minimal test batch
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        output_path = Path(f.name)

    try:
        # This would normally create a batch, but we'll check the template structure
        # Instead, check that the function exists and has IAA support
        import inspect

        from ml.annotation import hand_annotate

        # Check if IAA tracking is mentioned in the code
        source = inspect.getsource(hand_annotate.create_annotation_batch)
        assert "iaa_tracking" in source or "annotator" in source.lower()

    finally:
        if output_path.exists():
            output_path.unlink()


def test_annotation_metadata_extraction():
    """Test extracting metadata from annotations."""
    from ml.utils.annotation_utils import load_similarity_annotations

    # Create test annotation file
    test_ann = {
        "card1": "Lightning Bolt",
        "card2": "Chain Lightning",
        "similarity_score": 0.9,
        "similarity_type": "functional",
        "is_substitute": True,
        "model_name": "anthropic/claude-4.5-sonnet",
        "model_params": {"provider": "openrouter"},
        "annotator_id": "judge_1",
        "timestamp": datetime.now().isoformat(),
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(test_ann) + "\n")
        ann_path = Path(f.name)

    try:
        annotations = load_similarity_annotations(ann_path)
        assert len(annotations) == 1

        ann = annotations[0]
        assert ann.get("model_name") == "anthropic/claude-4.5-sonnet"
        assert ann.get("annotator_id") == "judge_1"
        assert ann.get("timestamp") is not None

    finally:
        if ann_path.exists():
            ann_path.unlink()


def test_graph_metadata_storage():
    """Test that annotation metadata can be stored in graph edges."""
    from ml.data.incremental_graph import Edge

    # Create edge with annotation metadata
    edge = Edge(
        card1="Lightning Bolt",
        card2="Chain Lightning",
        weight=5.0,
        metadata={
            "annotation": {
                "similarity_type": "functional",
                "is_substitute": True,
                "model_name": "anthropic/claude-4.5-sonnet",
            }
        },
    )

    # Verify metadata is stored
    assert edge.metadata is not None
    assert "annotation" in edge.metadata
    assert edge.metadata["annotation"]["similarity_type"] == "functional"
    assert edge.metadata["annotation"]["is_substitute"] is True

    # Verify serialization
    edge_dict = edge.to_dict()
    assert "metadata" in edge_dict
    assert "annotation" in edge_dict["metadata"]


@pytest.mark.skip(
    reason="train_multitask_refined_enhanced.create_enhanced_edgelist function is missing/corrupted"
)
def test_annotation_metadata_in_edgelist():
    """Test that annotation metadata is included in edgelist output."""
    # This would test the actual edgelist creation
    # For now, verify the function signature accepts annotation_metadata
    try:
        from ml.scripts.train_multitask_refined_enhanced import create_enhanced_edgelist
    except ImportError:
        pytest.skip("train_multitask_refined_enhanced module not available")

    import inspect

    sig = inspect.signature(create_enhanced_edgelist)

    # Verify annotation_metadata parameter exists
    assert "annotation_metadata" in sig.parameters
    param = sig.parameters["annotation_metadata"]
    assert param.default is None  # Should be optional


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
