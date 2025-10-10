#!/usr/bin/env python3
"""
Pydantic AI Helpers

Shared utilities for working with Pydantic AI agents across the codebase.
Reduces duplication and centralizes common patterns.
"""

import os

try:
    from pydantic_ai import Agent

    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False
    Agent = None


__all__ = ["make_agent", "get_default_model", "HAS_PYDANTIC_AI"]


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

    # Defaults by purpose
    defaults = {
        "judge": "openai/gpt-4o-mini",  # Cost-effective + JSON mode
        "annotator": "anthropic/claude-4.5-sonnet",  # Quality for annotations
        "validator": "anthropic/claude-4.5-sonnet",  # Quality for validation
        "general": "openai/gpt-4o-mini",  # Cost-effective default
    }

    return defaults.get(purpose, defaults["general"])


if __name__ == "__main__":
    print("🧪 Testing Pydantic AI helpers")

    if not HAS_PYDANTIC_AI:
        print("❌ pydantic-ai not installed")
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
        print(f"   {purpose}: {model}")

    print("\n✅ All helper functions work")
