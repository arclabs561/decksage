#!/usr/bin/env python3
"""
Pydantic AI Helpers

Shared utilities for working with Pydantic AI agents across the codebase.
Reduces duplication and centralizes common patterns.
"""

import os
from typing import Any


try:
    from pydantic_ai import Agent

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    Agent = None

# Import cost tracker (optional)
try:
    from ml.utils.llm_cost_tracker import get_global_tracker

    HAS_COST_TRACKER = True
except ImportError:
    HAS_COST_TRACKER = False
    get_global_tracker = None

__all__ = ["HAS_PYDANTIC_AI", "get_default_model", "make_agent", "run_with_tracking"]


def make_agent(
    model_name: str,
    result_cls,
    system_prompt: str,
    provider: str | None = None,
) -> Agent:
    """
    Create a Pydantic AI agent with consistent configuration.

    Args:
        model_name: Model name (e.g., "gpt-4o-mini", "claude-4.5-sonnet")
        result_cls: Pydantic model for structured output
        system_prompt: System prompt for the agent
        provider: Provider prefix (default: from env or "openrouter")

    Returns:
        Configured Agent instance

    Example:
        agent = make_agent(
            "gpt-4o-mini",
            MyModel,
            "You are an expert...",
        )
    """
    if not HAS_PYDANTIC_AI:
        raise ImportError("pydantic-ai required: uv add pydantic-ai")

    provider = provider or os.getenv("LLM_PROVIDER", "openrouter")
    return Agent(
        f"{provider}:{model_name}",
        output_type=result_cls,
        system_prompt=system_prompt,
    )


def get_default_model(purpose: str = "general") -> str:
    """
    Get default model for a given purpose.

    Centralizes model selection logic and allows env override.

    Args:
        purpose: "judge", "annotator", "validator", "general"

    Returns:
        Model name (e.g., "openai/gpt-4o-mini")
    """
    # Map purposes to env vars
    env_map = {
        "judge": "JUDGE_MODEL",
        "annotator": "ANNOTATOR_MODEL",
        "validator": "VALIDATOR_MODEL",
        "general": "DEFAULT_LLM_MODEL",
    }
    env_var = env_map.get(purpose, "DEFAULT_LLM_MODEL")
    env_value = os.getenv(env_var)
    if env_value:
        return env_value

    # Defaults by purpose (updated to frontier models from leaderboard)
    # Top models (2025): gemini-3-pro, claude-opus-4.5, grok-4.1-thinking
    # Note: OpenRouter model IDs use dots, not dashes (e.g., claude-opus-4.5)
    # Defaults by purpose (updated Dec 2025 based on latest research)
    # Latest: GPT-5.2 (Dec 2025) - better structured output, code generation, agentic work
    # GPT-5.2: 10.9% hallucination rate (vs 12.7% for GPT-5.1), better coding/science/math
    # Top models: GPT-5.2 (#1), Gemini 3 Pro (#2, 91.9), Claude Opus 4.5 (#5, 87)
    # Claude Sonnet 4.5 (83.4) best for coding/real-world tasks
    defaults = {
        "judge": "openai/gpt-5.2",  # Latest (Dec 2025), best structured output, 10.9% hallucination
        "annotator": "openai/gpt-5.2",  # Latest, best for annotations with improved accuracy
        "validator": "openai/gpt-5.2",  # Latest, best accuracy (lower hallucination rate)
        "general": "anthropic/claude-sonnet-4.5",  # Best for coding/real-world (83.4), cost-effective
    }
    return defaults.get(purpose, defaults["general"])


def run_with_tracking(
    agent: Agent,
    prompt: str,
    model: str | None = None,
    provider: str = "openrouter",
    operation: str = "unknown",
    cache_hit: bool = False,
    max_retries: int = 3,
    fallback_models: list[str] | None = None,
) -> Any:
    """
    Run agent with automatic cost tracking.

    Args:
        agent: Pydantic AI agent
        prompt: Input prompt
        model: Model name (extracted from agent if not provided)
        provider: Provider name
        operation: Operation type for tracking
        cache_hit: Whether this is a cache hit
        max_retries: Maximum number of retries
        fallback_models: List of fallback models to try

    Returns:
        Agent result
    """
    if not HAS_PYDANTIC_AI:
        raise ImportError("pydantic-ai required")

    # Extract model from agent if not provided
    if model is None:
        agent_str = str(agent)
        # Try to extract model from agent string
        if "/" in agent_str:
            parts = agent_str.split("/")
            if len(parts) >= 2:
                model = parts[-1]
        else:
            model = "unknown"

    # Run agent
    result = agent.run_sync(prompt)

    # Track usage if tracker available
    if HAS_COST_TRACKER and get_global_tracker:
        try:
            tracker = get_global_tracker()
            tracker.record_usage(
                result=result,
                model=model,
                provider=provider,
                operation=operation,
                cache_hit=cache_hit,
            )
        except Exception:
            # Best-effort tracking, don't fail on errors
            # Silently continue if cost tracking fails
            pass

    return result


if __name__ == "__main__":
    print("🧪 Testing Pydantic AI helpers")
    if not HAS_PYDANTIC_AI:
        print("Error: pydantic-ai not installed")
        exit(1)

    from pydantic import BaseModel, Field

    class TestModel(BaseModel):
        message: str = Field(description="Test message")

    # Test agent creation
    agent = make_agent("openai/gpt-4o-mini", TestModel, "You are a test agent")
    assert agent is not None
    print("✅ make_agent() works")

    # Test model selection
    for purpose in ["judge", "annotator", "validator", "general"]:
        model = get_default_model(purpose)
        print(f"  {purpose}: {model}")

    print("\n✅ All helper functions work")
