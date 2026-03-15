"""Re-export from canonical location: similarity.fusion_improvements."""

from ..similarity.fusion_improvements import (
    compute_component_confidence,
    create_query_adaptive_weights,
    create_task_specific_weights,
)

__all__ = [
    "compute_component_confidence",
    "create_query_adaptive_weights",
    "create_task_specific_weights",
]
