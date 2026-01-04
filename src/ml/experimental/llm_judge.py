#!/usr/bin/env python3
"""
LLM Judge for Similarity Evaluation

Evaluates similarity predictions using LLM-as-judge approach.
Provides structured quality assessments of similarity results.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from pydantic import BaseModel, Field
    from pydantic_ai import Agent
    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False

try:
    from ml.utils.pydantic_ai_helpers import make_agent
    HAS_HELPERS = True
except ImportError:
    HAS_HELPERS = False


class CardRating(BaseModel):
    """Rating for a single card."""
    card: str
    relevance: int = Field(ge=0, le=4, description="0-4 relevance score")
    reasoning: str = Field(description="Why this score?")


class SimilarityEvaluation(BaseModel):
    """LLM evaluation of similarity predictions."""
    overall_quality: int = Field(ge=0, le=10, description="Overall quality score 0-10")
    analysis: str = Field(description="Detailed analysis of similarity quality")
    card_ratings: list[CardRating] = Field(description="Ratings for each candidate card")
    issues: list[str] = Field(default_factory=list, description="Any issues identified")
    missing_cards: list[str] = Field(default_factory=list, description="Cards that should be included")


class LLMJudge:
    """LLM-as-judge for evaluating similarity predictions."""
    
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize LLM judge.
        
        Args:
            model: Model name (default: from env or gpt-4o-mini)
            api_key: API key (default: from OPENROUTER_API_KEY env var)
        """
        if not HAS_PYDANTIC_AI:
            raise ImportError("pydantic-ai required: pip install pydantic-ai")
        
        if not HAS_HELPERS:
            raise ImportError("ml.utils.pydantic_ai_helpers required")
        
        self.model = model or os.getenv("ANNOTATOR_MODEL_JUDGE") or "openai/gpt-4o-mini"
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        # Create agent with similarity evaluation prompt
        system_prompt = """You are an expert TCG judge evaluating card similarity predictions.

Given a query card and a list of similar cards with similarity scores, evaluate:
1. Overall quality of the predictions (0-10 scale)
2. Relevance of each candidate card (0-4 scale)
3. Any issues or missing cards

Provide structured evaluation with clear reasoning."""
        
        self.agent = make_agent(self.model, SimilarityEvaluation, system_prompt)
    
    def evaluate_similarity(
        self,
        query_card: str,
        similar_cards: list[tuple[str, float]] | list[str],
        context: str = "Magic: The Gathering",
    ) -> dict[str, Any]:
        """
        Evaluate similarity predictions.
        
        Args:
            query_card: The query card name
            similar_cards: List of (card, score) tuples or list of card names
            context: Game context (e.g., "Magic: The Gathering")
        
        Returns:
            Dict with overall_quality, analysis, card_ratings, issues, missing_cards
        """
        # Handle empty candidates gracefully
        if not similar_cards:
            return {
                "overall_quality": 0,
                "analysis": "No similar cards provided for evaluation.",
                "card_ratings": [],
                "issues": ["No candidates provided"],
                "missing_cards": [],
            }
        
        # Normalize similar_cards format
        if similar_cards and isinstance(similar_cards[0], str):
            # List of card names only
            candidates = [(card, 0.0) for card in similar_cards]
        else:
            # List of (card, score) tuples
            candidates = similar_cards
        
        # Build prompt
        candidates_str = "\n".join(f"- {card} (score: {score:.3f})" for card, score in candidates)
        
        prompt = f"""Evaluate similarity predictions for the query card: {query_card}

Context: {context}

Similar cards found:
{candidates_str}

Evaluate:
1. Overall quality of these predictions (0-10, where 10 is perfect)
2. Relevance of each candidate (0-4 scale)
3. Any issues or missing cards that should be included

Provide detailed analysis."""
        
        try:
            # Run agent using run_sync (standard pattern in codebase)
            result = self.agent.run_sync(prompt)
            
            # Extract structured result
            if hasattr(result, 'output'):
                evaluation = result.output
            elif hasattr(result, 'data'):
                evaluation = result.data
            else:
                evaluation = result
            
            # Convert to dict format expected by tests
            return {
                "overall_quality": evaluation.overall_quality if hasattr(evaluation, 'overall_quality') else 0,
                "analysis": evaluation.analysis if hasattr(evaluation, 'analysis') else "",
                "card_ratings": [
                    {
                        "card": rating.card,
                        "relevance": rating.relevance,
                        "reasoning": rating.reasoning,
                    }
                    for rating in (evaluation.card_ratings if hasattr(evaluation, 'card_ratings') else [])
                ],
                "issues": evaluation.issues if hasattr(evaluation, 'issues') else [],
                "missing_cards": evaluation.missing_cards if hasattr(evaluation, 'missing_cards') else [],
            }
        except Exception as e:
            # Return error result instead of crashing
            return {
                "overall_quality": None,
                "analysis": f"Error during evaluation: {str(e)}",
                "card_ratings": [],
                "issues": [f"Evaluation failed: {str(e)}"],
                "missing_cards": [],
            }

