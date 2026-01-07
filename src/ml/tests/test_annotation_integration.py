#!/usr/bin/env python3
"""
Integration tests for annotation workflows.

Tests complete workflows:
1. YAML → substitution pairs → training
2. YAML → test set merge
3. JSONL → substitution pairs
4. Judgments → annotations → substitution pairs
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    yaml = None


@pytest.fixture
def sample_hand_annotation_yaml():
    """Create a sample hand annotation YAML file."""
    data = {
        "metadata": {
            "game": "magic",
            "batch_id": "test_batch",
            "num_queries": 1,
        },
        "tasks": [
            {
                "query": "Lightning Bolt",
                "game": "magic",
                "candidates": [
                    {
                        "card": "Chain Lightning",
                        "relevance": 4,
                        "similarity_type": "substitute",
                        "is_substitute": True,
                    },
                    {
                        "card": "Shock",
                        "relevance": 3,
                        "similarity_type": "functional",
                        "is_substitute": False,
                    },
                ],
            }
        ],
    }
    return data


@pytest.fixture
def sample_llm_annotation_jsonl():
    """Create a sample LLM annotation JSONL file."""
    annotations = [
        {
            "card1": "Lightning Bolt",
            "card2": "Chain Lightning",
            "similarity_score": 0.95,
            "similarity_type": "functional",
            "is_substitute": True,
            "reasoning": "Both 1-mana red burn spells",
        },
        {
            "card1": "Lightning Bolt",
            "card2": "Shock",
            "similarity_score": 0.75,
            "similarity_type": "functional",
            "is_substitute": False,
        },
    ]
    return annotations


@pytest.fixture
def sample_judgment_json():
    """Create a sample judgment JSON file."""
    judgment = {
        "query_card": "Lightning Bolt",
        "annotator": "system",
        "annotation_type": "programmatic_ensemble",
        "timestamp": "2025-01-01T00:00:00",
        "evaluations": [
            {
                "card": "Chain Lightning",
                "relevance": 4,
                "confidence": 0.9,
                "method_votes": ["node2vec"],
                "avg_rank": 1.0,
            },
            {
                "card": "Shock",
                "relevance": 3,
                "confidence": 0.8,
                "method_votes": ["node2vec"],
                "avg_rank": 2.0,
            },
        ],
        "methods_used": ["node2vec"],
    }
    return judgment


@pytest.mark.skipif(not HAS_YAML, reason="PyYAML not available")
def test_yaml_to_substitution_pairs(sample_hand_annotation_yaml):
    """Test complete workflow: YAML → substitution pairs."""
    from ml.utils.annotation_utils import convert_annotations_to_substitution_pairs

    # Create temp YAML file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_hand_annotation_yaml, f)
        yaml_path = Path(f.name)

    try:
        # Convert to substitution pairs
        pairs = convert_annotations_to_substitution_pairs(
            yaml_path,
            min_relevance=4,
            require_substitute_flag=True,
        )

        # Should extract only relevance=4 with is_substitute=True
        assert len(pairs) == 1
        assert ("Lightning Bolt", "Chain Lightning") in pairs or (
            "Chain Lightning",
            "Lightning Bolt",
        ) in pairs

    finally:
        yaml_path.unlink()


def test_jsonl_to_substitution_pairs(sample_llm_annotation_jsonl):
    """Test JSONL → substitution pairs conversion."""
    from ml.utils.annotation_utils import convert_annotations_to_substitution_pairs

    # Create temp JSONL file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for ann in sample_llm_annotation_jsonl:
            f.write(json.dumps(ann) + "\n")
        jsonl_path = Path(f.name)

    try:
        # Convert to substitution pairs
        pairs = convert_annotations_to_substitution_pairs(
            jsonl_path,
            min_similarity=0.8,
            require_substitute_flag=True,
        )

        # Should extract only is_substitute=True with similarity >= 0.8
        assert len(pairs) == 1
        assert ("Lightning Bolt", "Chain Lightning") in pairs or (
            "Chain Lightning",
            "Lightning Bolt",
        ) in pairs

    finally:
        jsonl_path.unlink()


def test_judgment_to_annotations(sample_judgment_json):
    """Test judgment → annotations conversion."""
    from ml.utils.annotation_utils import convert_judgments_to_annotations

    judgments = [sample_judgment_json]
    annotations = convert_judgments_to_annotations(judgments)

    assert len(annotations) == 2
    assert all(ann["card1"] == "Lightning Bolt" for ann in annotations)
    assert any(ann["card2"] == "Chain Lightning" for ann in annotations)
    assert any(ann["card2"] == "Shock" for ann in annotations)

    # Check that relevance=4 → is_substitute=True
    chain_ann = next(ann for ann in annotations if ann["card2"] == "Chain Lightning")
    assert chain_ann["is_substitute"] is True
    assert chain_ann["similarity_score"] > 0.8


def test_auto_detect_format():
    """Test that load_similarity_annotations auto-detects format."""
    from ml.utils.annotation_utils import load_similarity_annotations

    # Test JSONL
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"card1": "A", "card2": "B", "similarity_score": 0.9}\n')
        jsonl_path = Path(f.name)

    try:
        annotations = load_similarity_annotations(jsonl_path)
        assert len(annotations) == 1
        assert annotations[0]["card1"] == "A"
    finally:
        jsonl_path.unlink()

    # Test YAML (if available)
    if HAS_YAML:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {
                    "tasks": [
                        {
                            "query": "A",
                            "candidates": [{"card": "B", "relevance": 4}],
                        }
                    ]
                },
                f,
            )
            yaml_path = Path(f.name)

        try:
            annotations = load_similarity_annotations(yaml_path)
            assert len(annotations) == 1
            assert annotations[0]["card1"] == "A"
            assert annotations[0]["card2"] == "B"
        finally:
            yaml_path.unlink()


def test_annotation_workflow_end_to_end(sample_hand_annotation_yaml):
    """Test complete workflow: YAML → pairs → verify format."""
    from ml.utils.annotation_utils import (
        convert_annotations_to_substitution_pairs,
        load_similarity_annotations,
    )

    if not HAS_YAML:
        pytest.skip("PyYAML not available")

    # Create temp YAML file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_hand_annotation_yaml, f)
        yaml_path = Path(f.name)

    try:
        # Step 1: Load annotations
        annotations = load_similarity_annotations(yaml_path)
        assert len(annotations) == 2

        # Step 2: Convert to substitution pairs
        pairs = convert_annotations_to_substitution_pairs(
            yaml_path,
            min_relevance=4,
            require_substitute_flag=True,
        )
        assert len(pairs) == 1

        # Step 3: Verify pairs format (for training)
        assert all(isinstance(p, tuple) and len(p) == 2 for p in pairs)

    finally:
        yaml_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


