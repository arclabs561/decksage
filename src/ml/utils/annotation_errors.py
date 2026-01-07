"""Enhanced error handling for annotation operations.

Provides context-rich error messages and error categorization.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class AnnotationErrorType(Enum):
    """Categories of annotation errors."""
    
    MISSING_FIELD = "missing_field"
    INVALID_VALUE = "invalid_value"
    TYPE_MISMATCH = "type_mismatch"
    RANGE_VIOLATION = "range_violation"
    FORMAT_ERROR = "format_error"
    DUPLICATE = "duplicate"
    INCONSISTENT = "inconsistent"
    UNKNOWN = "unknown"


class AnnotationError(Exception):
    """Enhanced annotation error with context."""
    
    def __init__(
        self,
        message: str,
        error_type: AnnotationErrorType = AnnotationErrorType.UNKNOWN,
        annotation: dict[str, Any] | None = None,
        field: str | None = None,
        context: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.annotation = annotation
        self.field = field
        self.context = context or {}
    
    def __str__(self) -> str:
        """Format error message with context."""
        parts = [f"[{self.error_type.value}] {super().__str__()}"]
        
        if self.field:
            parts.append(f"Field: {self.field}")
        
        if self.annotation:
            card1 = self.annotation.get("card1", "?")
            card2 = self.annotation.get("card2", "?")
            parts.append(f"Annotation: {card1} <-> {card2}")
        
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        
        return " | ".join(parts)


def create_validation_error(
    message: str,
    annotation: dict[str, Any],
    field: str | None = None,
    **context: Any,
) -> AnnotationError:
    """Create a validation error with context."""
    # Determine error type from message
    error_type = AnnotationErrorType.UNKNOWN
    msg_lower = message.lower()
    
    if "missing" in msg_lower or "required" in msg_lower:
        error_type = AnnotationErrorType.MISSING_FIELD
    elif "invalid" in msg_lower or "not valid" in msg_lower:
        error_type = AnnotationErrorType.INVALID_VALUE
    elif "type" in msg_lower and "mismatch" in msg_lower:
        error_type = AnnotationErrorType.TYPE_MISMATCH
    elif "range" in msg_lower or "must be" in msg_lower:
        error_type = AnnotationErrorType.RANGE_VIOLATION
    elif "format" in msg_lower or "parse" in msg_lower:
        error_type = AnnotationErrorType.FORMAT_ERROR
    elif "duplicate" in msg_lower:
        error_type = AnnotationErrorType.DUPLICATE
    
    return AnnotationError(
        message=message,
        error_type=error_type,
        annotation=annotation,
        field=field,
        context=context,
    )


def format_error_message(
    error: Exception,
    annotation: dict[str, Any] | None = None,
    operation: str | None = None,
) -> str:
    """Format error message with helpful context and suggestions."""
    
    if isinstance(error, AnnotationError):
        # Already has context
        return str(error)
    
    # Build context-rich message
    parts = [f"Error: {str(error)}"]
    
    if operation:
        parts.append(f"Operation: {operation}")
    
    if annotation:
        card1 = annotation.get("card1", "?")
        card2 = annotation.get("card2", "?")
        source = annotation.get("source", "?")
        parts.append(f"Annotation: {card1} <-> {card2} (source: {source})")
    
    # Add suggestions based on error type
    error_str = str(error).lower()
    
    if "missing" in error_str or "required" in error_str:
        parts.append("Suggestion: Ensure all required fields (card1, card2, similarity_score, source) are present")
    elif "similarity_score" in error_str or "score" in error_str:
        parts.append("Suggestion: similarity_score must be a float in range [0.0, 1.0]")
    elif "json" in error_str or "parse" in error_str:
        parts.append("Suggestion: Check JSON syntax and ensure file is valid JSONL")
    elif "import" in error_str or "module" in error_str:
        parts.append("Suggestion: Install required dependencies (pydantic, pyyaml)")
    
    return " | ".join(parts)


