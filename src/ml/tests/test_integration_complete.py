#!/usr/bin/env python3
"""Integration test proving validators are adopted in existing code."""

from pathlib import Path

import pytest

from ..utils.data_loading import load_decks_jsonl


def test_data_loading_uses_validators():
    """Verify utils.data_loading now uses validators by default."""
    # Load with validation (default)
    project_root = Path(__file__).resolve().parents[3]
    default = project_root / "src" / "backend" / "decks_hetero.jsonl"
    fixture = Path(__file__).parent / "fixtures" / "decks_export_hetero_small.jsonl"
    decks = load_decks_jsonl(
        jsonl_path=default if default.exists() else fixture,
        validate=True,
        formats=None,
        max_placement=None,
    )
    
    assert len(decks) > 0
    # Should be dicts (backward compatible)
    assert isinstance(decks[0], dict)
    # Should have validated fields
    assert "deck_id" in decks[0]
    assert "format" in decks[0]


def test_data_loading_backward_compatible():
    """Verify old code still works with validate=False."""
    project_root = Path(__file__).resolve().parents[3]
    default = project_root / "src" / "backend" / "decks_hetero.jsonl"
    fixture = Path(__file__).parent / "fixtures" / "decks_export_hetero_small.jsonl"
    decks = load_decks_jsonl(
        jsonl_path=default if default.exists() else fixture,
        validate=False,
    )
    
    assert len(decks) > 0
    assert isinstance(decks[0], dict)


def test_data_loading_format_filter():
    """Verify format filtering works with validation."""
    # Load Modern decks only
    project_root = Path(__file__).resolve().parents[3]
    modern_decks = load_decks_jsonl(
        jsonl_path=project_root / "data" / "processed" / "decks_with_metadata.jsonl",
        formats=["Modern"],
        validate=True,
    )
    
    # All should be Modern (or fewer than total if none exist)
    if modern_decks:
        assert all(d["format"] == "Modern" for d in modern_decks[:10])


def test_llm_annotator_imports_and_loads_data():
    """Verify LLMAnnotator can be imported and load data.
    
    NOTE: This does NOT test actual LLM API calls.
    For real LLM tests, see test_llm_validators_real.py
    """
    import os
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    
    from ..annotation.llm_annotator import HAS_PYDANTIC_AI, LLMAnnotator
    
    if not HAS_PYDANTIC_AI:
        pytest.skip("pydantic-ai not available")
    
    annotator = LLMAnnotator()
    assert len(annotator.decks) > 0


def test_llm_data_validator_imports_and_loads_data():
    """Verify DataQualityValidator can be imported and load data.
    
    NOTE: This does NOT test actual LLM API calls.
    For real LLM tests, see test_llm_validators_real.py
    """
    import os
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")
    
    from ..validation.llm_data_validator import HAS_PYDANTIC_AI, DataQualityValidator
    
    if not HAS_PYDANTIC_AI:
        pytest.skip("pydantic-ai not available")
    
    validator = DataQualityValidator()
    assert len(validator.decks) > 0
