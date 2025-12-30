#!/usr/bin/env python3
"""
LLM Cost Tracking and Reporting

Tracks API usage, token counts, and costs across all LLM operations.
Integrates with Pydantic AI and provides detailed reporting.

Usage:
    tracker = LLMCostTracker()
    with tracker.track_call(model="openai/gpt-4o", provider="openrouter"):
        result = agent.run_sync(prompt)
        tracker.record_usage(result, model="openai/gpt-4o")
    
    tracker.print_summary()
    tracker.save_report("cost_report.json")
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Pricing data (per 1M tokens) - updated 2025
# Sources: OpenRouter pricing, OpenAI pricing, Anthropic pricing
PRICING_DATA = {
    # OpenAI models
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai/gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "openai/gpt-4": {"input": 30.00, "output": 60.00},
    "openai/gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    
    # Anthropic models
    "anthropic/claude-opus-4.5": {"input": 15.00, "output": 75.00},
    "anthropic/claude-sonnet-4.5": {"input": 3.00, "output": 15.00},
    "anthropic/claude-haiku-4": {"input": 0.25, "output": 1.25},
    "anthropic/claude-3-opus": {"input": 15.00, "output": 75.00},
    "anthropic/claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "anthropic/claude-3-haiku": {"input": 0.25, "output": 1.25},
    
    # Google models
    "google/gemini-3-pro": {"input": 1.25, "output": 5.00},
    "google/gemini-2.0-flash-exp": {"input": 0.075, "output": 0.30},
    "google/gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    
    # xAI models
    "x-ai/grok-4.1-thinking": {"input": 5.00, "output": 15.00},
    "x-ai/grok-beta": {"input": 0.50, "output": 1.50},
    
    # Meta models
    "meta-llama/llama-3.1-405b": {"input": 2.70, "output": 2.70},
    "meta-llama/llama-3.1-70b": {"input": 0.59, "output": 0.79},
    
    # Default fallback (conservative estimate)
    "default": {"input": 1.00, "output": 3.00},
}


@dataclass
class UsageRecord:
    """Single API call usage record."""
    timestamp: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit: bool = False
    cost_usd: float = 0.0
    operation: str = "unknown"  # e.g., "label_generation", "query_generation"
    error: str | None = None


@dataclass
class CostSummary:
    """Aggregated cost summary."""
    total_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_operation: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: int = 0


class LLMCostTracker:
    """Track LLM API usage and costs."""
    
    def __init__(self, session_name: str | None = None):
        """
        Initialize cost tracker.
        
        Args:
            session_name: Optional name for this tracking session
        """
        self.session_name = session_name or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.records: list[UsageRecord] = []
        self._current_operation: str = "unknown"
        self._cache_hit: bool = False
    
    def get_pricing(self, model: str) -> dict[str, float]:
        """Get pricing for a model (per 1M tokens)."""
        # Try exact match first
        if model in PRICING_DATA:
            return PRICING_DATA[model]
        
        # Try provider prefix match
        for key, pricing in PRICING_DATA.items():
            if model.startswith(key.split("/")[0] + "/"):
                return pricing
        
        # Try partial match (e.g., "gpt-4o" matches "openai/gpt-4o")
        model_lower = model.lower()
        for key, pricing in PRICING_DATA.items():
            if "/" in key:
                _, model_part = key.split("/", 1)
                if model_part in model_lower or model_lower in model_part:
                    return pricing
        
        # Fallback to default
        return PRICING_DATA["default"]
    
    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_hit: bool = False,
    ) -> float:
        """Calculate cost for a call."""
        if cache_hit:
            return 0.0
        
        pricing = self.get_pricing(model)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost
    
    def record_usage(
        self,
        result: Any,
        model: str,
        provider: str = "openrouter",
        operation: str | None = None,
        cache_hit: bool = False,
        error: str | None = None,
    ) -> UsageRecord:
        """
        Record usage from a Pydantic AI result.
        
        Args:
            result: Pydantic AI result object (has .usage or .data.usage)
            model: Model name
            provider: Provider name
            operation: Operation type (defaults to current operation)
            cache_hit: Whether this was a cache hit
            error: Error message if call failed
        """
        # Extract usage from result
        input_tokens = 0
        output_tokens = 0
        
        # Pydantic AI stores usage in result.usage or result.data.usage
        usage = None
        if hasattr(result, "usage"):
            usage = result.usage
        elif hasattr(result, "data") and hasattr(result.data, "usage"):
            usage = result.data.usage
        elif isinstance(result, dict) and "usage" in result:
            usage = result["usage"]
        
        if usage:
            if isinstance(usage, dict):
                input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
                output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
            elif hasattr(usage, "input_tokens"):
                input_tokens = usage.input_tokens
                output_tokens = usage.output_tokens
        
        cost = self.calculate_cost(model, input_tokens, output_tokens, cache_hit)
        
        record = UsageRecord(
            timestamp=datetime.now().isoformat(),
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit=cache_hit,
            cost_usd=cost,
            operation=operation or self._current_operation,
            error=error,
        )
        
        self.records.append(record)
        return record
    
    @contextmanager
    def track_call(self, model: str, provider: str = "openrouter", operation: str = "unknown"):
        """Context manager to track a single call."""
        old_operation = self._current_operation
        self._current_operation = operation
        self._cache_hit = False
        try:
            yield
        finally:
            self._current_operation = old_operation
    
    def mark_cache_hit(self):
        """Mark the current call as a cache hit."""
        self._cache_hit = True
    
    def get_summary(self) -> CostSummary:
        """Generate cost summary."""
        summary = CostSummary()
        
        for record in self.records:
            summary.total_calls += 1
            if record.cache_hit:
                summary.cache_hits += 1
            else:
                summary.cache_misses += 1
                summary.total_input_tokens += record.input_tokens
                summary.total_output_tokens += record.output_tokens
                summary.total_cost_usd += record.cost_usd
            
            if record.error:
                summary.errors += 1
            
            # Aggregate by model
            if record.model not in summary.by_model:
                summary.by_model[record.model] = {
                    "calls": 0,
                    "cache_hits": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
            model_stats = summary.by_model[record.model]
            model_stats["calls"] += 1
            if record.cache_hit:
                model_stats["cache_hits"] += 1
            else:
                model_stats["input_tokens"] += record.input_tokens
                model_stats["output_tokens"] += record.output_tokens
                model_stats["cost_usd"] += record.cost_usd
            
            # Aggregate by operation
            if record.operation not in summary.by_operation:
                summary.by_operation[record.operation] = {
                    "calls": 0,
                    "cache_hits": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
            op_stats = summary.by_operation[record.operation]
            op_stats["calls"] += 1
            if record.cache_hit:
                op_stats["cache_hits"] += 1
            else:
                op_stats["input_tokens"] += record.input_tokens
                op_stats["output_tokens"] += record.output_tokens
                op_stats["cost_usd"] += record.cost_usd
        
        return summary
    
    def print_summary(self):
        """Print a formatted cost summary."""
        summary = self.get_summary()
        
        print("\n" + "=" * 70)
        print("LLM COST SUMMARY")
        print("=" * 70)
        print(f"Session: {self.session_name}")
        print(f"Total Calls: {summary.total_calls}")
        print(f"Cache Hits: {summary.cache_hits} ({summary.cache_hits/summary.total_calls*100:.1f}%)" if summary.total_calls > 0 else "Cache Hits: 0")
        print(f"Cache Misses: {summary.cache_misses}")
        print(f"Total Input Tokens: {summary.total_input_tokens:,}")
        print(f"Total Output Tokens: {summary.total_output_tokens:,}")
        print(f"Total Cost: ${summary.total_cost_usd:.4f}")
        if summary.errors > 0:
            print(f"Errors: {summary.errors}")
        
        if summary.by_model:
            print("\nBy Model:")
            for model, stats in sorted(summary.by_model.items(), key=lambda x: x[1]["cost_usd"], reverse=True):
                print(f"  {model}:")
                print(f"    Calls: {stats['calls']} (hits: {stats['cache_hits']})")
                print(f"    Tokens: {stats['input_tokens']:,} in, {stats['output_tokens']:,} out")
                print(f"    Cost: ${stats['cost_usd']:.4f}")
        
        if summary.by_operation:
            print("\nBy Operation:")
            for op, stats in sorted(summary.by_operation.items(), key=lambda x: x[1]["cost_usd"], reverse=True):
                print(f"  {op}:")
                print(f"    Calls: {stats['calls']} (hits: {stats['cache_hits']})")
                print(f"    Tokens: {stats['input_tokens']:,} in, {stats['output_tokens']:,} out")
                print(f"    Cost: ${stats['cost_usd']:.4f}")
        
        print("=" * 70 + "\n")
    
    def save_report(self, output_path: str | Path):
        """Save detailed report to JSON."""
        summary = self.get_summary()
        
        report = {
            "session_name": self.session_name,
            "timestamp": datetime.now().isoformat(),
            "summary": asdict(summary),
            "records": [asdict(r) for r in self.records],
        }
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        
        return output_path


# Global tracker instance (can be used across scripts)
_global_tracker: LLMCostTracker | None = None


def get_global_tracker() -> LLMCostTracker:
    """Get or create global cost tracker."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = LLMCostTracker()
    return _global_tracker


def reset_global_tracker():
    """Reset global tracker (useful for new sessions)."""
    global _global_tracker
    _global_tracker = None

