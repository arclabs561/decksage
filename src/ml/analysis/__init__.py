"""Analysis tools for scientific evaluation and improvement."""

from .measure_signal_performance import measure_signal_performance
from .analyze_failures import analyze_failures, categorize_failure
from .weight_sensitivity import analyze_weight_sensitivity, suggest_weight_adjustments

__all__ = [
    "measure_signal_performance",
    "analyze_failures",
    "categorize_failure",
    "analyze_weight_sensitivity",
    "suggest_weight_adjustments",
]







