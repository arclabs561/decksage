"""
LLM-Powered UX Enhancements for DeckSage

Uses LLMs to improve search experience:
- Natural language query understanding
- Intelligent query expansion
- Context-aware suggestions
- Query intent classification

Configuration via .env:
- ANTHROPIC_API_KEY: For Claude models
- OPENAI_API_KEY: For GPT models
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

logger = logging.getLogger(__name__)

# Optional LLM integration
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


def understand_query_intent(query: str, game: str | None = None) -> dict[str, Any]:
    """
    Use LLM to understand user query intent.
    
    Returns:
        {
            "intent": "substitute" | "synergy" | "meta" | "general",
            "confidence": float,
            "suggested_method": str,
            "expanded_terms": list[str],
            "clarifications": list[str]
        }
    """
    if not (HAS_ANTHROPIC or HAS_OPENAI):
        # Fallback: simple heuristic
        return _heuristic_intent(query, game)
    
    # Use LLM for intelligent understanding
    prompt = f"""Analyze this card game search query and determine the user's intent.

Query: "{query}"
Game: {game or "unknown"}

Determine:
1. Intent: substitute (finding replacement), synergy (finding combos), meta (format analysis), or general (just searching)
2. Confidence: 0.0-1.0
3. Suggested search method: fusion, embedding, or jaccard
4. Expanded search terms: related keywords that might help
5. Clarifications: questions to help refine if intent is unclear

Return JSON:
{{
    "intent": "substitute|synergy|meta|general",
    "confidence": 0.0-1.0,
    "suggested_method": "fusion|embedding|jaccard",
    "expanded_terms": ["term1", "term2"],
    "clarifications": ["question1", "question2"]
}}"""

    try:
        if HAS_ANTHROPIC:
            client = anthropic.Anthropic(api_key=_get_api_key("ANTHROPIC_API_KEY"))
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            result_text = response.content[0].text
        elif HAS_OPENAI:
            client = OpenAI(api_key=_get_api_key("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500
            )
            result_text = response.choices[0].message.content
        
        # Parse JSON from response
        import json
        # Extract JSON from markdown code blocks if present
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(result_text)
        return result
    except Exception as e:
        logger.warning(f"LLM intent understanding failed: {e}, using heuristic")
        return _heuristic_intent(query, game)


def expand_query_with_context(
    query: str,
    card_attrs: dict[str, Any] | None = None,
    game: str | None = None
) -> list[str]:
    """
    Expand query with context-aware terms using LLM.
    
    Example: "red burn" → ["red", "burn", "lightning", "damage", "instant", "sorcery"]
    """
    if not (HAS_ANTHROPIC or HAS_OPENAI):
        # Fallback: simple expansion
        return [query]
    
    prompt = f"""Expand this card game search query with related terms that would help find relevant cards.

Query: "{query}"
Game: {game or "unknown"}

Generate 3-5 related search terms that capture the same intent but might match different cards.
Return as JSON array: ["term1", "term2", "term3"]"""

    try:
        if HAS_ANTHROPIC:
            client = anthropic.Anthropic(api_key=_get_api_key("ANTHROPIC_API_KEY"))
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            result_text = response.content[0].text
        elif HAS_OPENAI:
            client = OpenAI(api_key=_get_api_key("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200
            )
            result_text = response.choices[0].message.content
        
        import json
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        expanded = json.loads(result_text)
        return expanded if isinstance(expanded, list) else [query]
    except Exception as e:
        logger.warning(f"LLM query expansion failed: {e}")
        return [query]


def generate_smart_suggestions(
    partial_query: str,
    context: dict[str, Any] | None = None
) -> list[str]:
    """
    Generate intelligent autocomplete suggestions using LLM.
    
    Goes beyond prefix matching to suggest semantically related cards.
    """
    if not (HAS_ANTHROPIC or HAS_OPENAI):
        return []
    
    prompt = f"""Generate 5-8 intelligent autocomplete suggestions for this partial card search query.

Partial query: "{partial_query}"
Context: {context or "none"}

Suggestions should:
1. Include cards that match the prefix
2. Include semantically related cards (similar function, type, or theme)
3. Be relevant to card game search

Return as JSON array: ["Card Name 1", "Card Name 2", ...]"""

    try:
        if HAS_ANTHROPIC:
            client = anthropic.Anthropic(api_key=_get_api_key("ANTHROPIC_API_KEY"))
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            result_text = response.content[0].text
        elif HAS_OPENAI:
            client = OpenAI(api_key=_get_api_key("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300
            )
            result_text = response.choices[0].message.content
        
        import json
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        suggestions = json.loads(result_text)
        return suggestions if isinstance(suggestions, list) else []
    except Exception as e:
        logger.warning(f"LLM smart suggestions failed: {e}")
        return []


def _heuristic_intent(query: str, game: str | None = None) -> dict[str, Any]:
    """Fallback heuristic intent detection."""
    query_lower = query.lower()
    
    # Simple keyword-based intent detection
    if any(word in query_lower for word in ["replace", "instead", "alternative", "substitute"]):
        intent = "substitute"
        method = "fusion"
    elif any(word in query_lower for word in ["combo", "synergy", "works with", "pairs"]):
        intent = "synergy"
        method = "jaccard"
    elif any(word in query_lower for word in ["meta", "format", "tier", "competitive"]):
        intent = "meta"
        method = "fusion"
    else:
        intent = "general"
        method = "fusion"
    
    return {
        "intent": intent,
        "confidence": 0.6,  # Lower confidence for heuristic
        "suggested_method": method,
        "expanded_terms": [query],
        "clarifications": []
    }


def _get_api_key(env_var: str) -> str:
    """Get API key from environment variable (loaded from .env)."""
    key = os.getenv(env_var)
    if not key:
        raise ValueError(f"{env_var} not set in .env file or environment")
    return key

