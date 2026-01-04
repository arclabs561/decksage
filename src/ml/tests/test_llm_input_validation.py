#!/usr/bin/env python3
"""
Input Validation Tests

Tests that LLM validators handle invalid inputs robustly.
"""

import os

import pytest
from dotenv import load_dotenv


load_dotenv()


@pytest.mark.llm
@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set")
def test_invalid_similarity_scores():
    """Test that invalid similarity scores are handled."""
    from ..experimental.llm_judge import LLMJudge

    judge = LLMJudge(model="openai/gpt-4o-mini")

    # Negative scores
    result = judge.evaluate_similarity("Test", [("Card", -0.5)])
    assert result is not None
    assert "overall_quality" in result

    # Scores > 1.0
    result = judge.evaluate_similarity("Test", [("Card", 1.5)])
    assert result is not None

    # Mixed valid/invalid
    result = judge.evaluate_similarity("Test", [("A", -0.1), ("B", 0.5), ("C", 2.0)])
    assert result is not None


@pytest.mark.llm
@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set")
def test_special_characters_in_names():
    """Test cards with special characters."""
    from ..experimental.llm_judge import LLMJudge

    judge = LLMJudge(model="openai/gpt-4o-mini")

    # Quotes in names
    result = judge.evaluate_similarity('Card "Name"', [('Other "Card"', 0.9)])
    assert result is not None

    # Newlines (shouldn't break prompts)
    result = judge.evaluate_similarity("Card\nName", [("Other", 0.9)])
    assert result is not None


@pytest.mark.llm
def test_batch_empty_queries():
    """Test batch_evaluate with empty query list."""
    from ..experimental.llm_judge import LLMJudge

    judge = LLMJudge(model="openai/gpt-4o-mini")

    # Should return empty results, not crash
    results = judge.batch_evaluate([], lambda c, k: [(c, 0.9)])
    assert results == []


@pytest.mark.llm
def test_batch_all_predictions_fail():
    """Test batch_evaluate when model_fn always fails."""
    from ..experimental.llm_judge import LLMJudge

    judge = LLMJudge(model="openai/gpt-4o-mini")

    def failing_model(card, k):
        raise ValueError("Model broken")

    # Should handle gracefully
    results = judge.batch_evaluate(["Test1", "Test2"], failing_model)
    assert results == []  # All failed, should be empty


@pytest.mark.llm
def test_model_fn_returns_wrong_type():
    """Test when model_fn returns wrong type."""
    from ..experimental.llm_judge import LLMJudge

    judge = LLMJudge(model="openai/gpt-4o-mini")

    # Returns dict instead of list[tuple]
    def bad_model(card, k):
        return {"wrong": "type"}

    # Should raise TypeError with clear message
    with pytest.raises(TypeError, match="similar_cards must be"):
        results = judge.batch_evaluate(["Test"], bad_model)
