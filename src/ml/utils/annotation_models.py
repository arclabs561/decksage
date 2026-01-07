"""Pydantic models for annotation validation and structure.

Provides runtime validation for annotation data structures.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from pydantic import BaseModel, Field, field_validator

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseModel = object  # type: ignore
    Field = lambda **kwargs: lambda x: x  # type: ignore
    field_validator = lambda *args, **kwargs: lambda x: x  # type: ignore


class UnifiedAnnotation(BaseModel):
    """Unified annotation model for runtime validation.
    
    Validates annotations from all sources (hand, LLM, user feedback, etc.)
    """

    card1: str = Field(description="First card name")
    card2: str = Field(description="Second card name")
    similarity_score: float = Field(
        ge=0.0, le=1.0, description="Similarity score (0-1)"
    )
    source: str = Field(description="Annotation source (hand_annotation, llm_generated, etc.)")
    
    # Optional fields
    similarity_type: str | None = Field(
        default=None,
        description="Type: functional, synergy, manabase, archetype, unrelated",
    )
    is_substitute: bool | None = Field(
        default=None, description="Can card2 replace card1?"
    )
    relevance: int | None = Field(
        default=None, ge=0, le=4, description="Relevance score (0-4) for hand annotations"
    )
    reasoning: str | None = Field(default=None, description="Explanation for similarity")
    notes: str | None = Field(default=None, description="Additional notes")
    
    # Metadata
    metadata: dict[str, Any] | None = Field(
        default=None, description="Source-specific metadata"
    )
    timestamp: str | None = Field(default=None, description="ISO timestamp")
    annotator_id: str | None = Field(default=None, description="Annotator/judge ID")
    model_name: str | None = Field(default=None, description="LLM model used")
    
    @field_validator("card1", "card2")
    @classmethod
    def validate_card_name(cls, v: str) -> str:
        """Validate and normalize card name."""
        if not v or not v.strip():
            raise ValueError("Card name cannot be empty")
        return v.strip()
    
    @field_validator("similarity_score")
    @classmethod
    def validate_similarity_score(cls, v: float) -> float:
        """Validate similarity score is in valid range."""
        if not isinstance(v, (int, float)):
            raise ValueError(f"Similarity score must be numeric, got {type(v)}")
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Similarity score must be in [0, 1], got {v}")
        return float(v)
    
    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        """Validate source is recognized."""
        # Normalize common variations
        if v == "llm":
            return "llm_generated"
        
        valid_sources = {
            "hand_annotation",
            "llm_generated",
            "llm_judgment",
            "user_feedback",
            "multi_judge",
            "browser_annotation",
            "synthetic",
        }
        if v not in valid_sources:
            # Warn but allow unknown sources
            import warnings
            warnings.warn(f"Unknown annotation source: {v}")
        return v
    
    @field_validator("similarity_type")
    @classmethod
    def validate_similarity_type(cls, v: str | None) -> str | None:
        """Validate similarity type if provided."""
        if v is None:
            return v
        valid_types = {
            "functional",
            "synergy",
            "manabase",
            "archetype",
            "unrelated",
            "substitute",
            "similar_function",
        }
        if v not in valid_types:
            import warnings
            warnings.warn(f"Unknown similarity type: {v}")
        return v
    
    def model_dump_for_storage(self) -> dict[str, Any]:
        """Export to dict format for JSONL storage."""
        data = self.model_dump(exclude_none=False)
        # Ensure all required fields are present
        assert "card1" in data
        assert "card2" in data
        assert "similarity_score" in data
        assert "source" in data
        return data


def validate_annotation(annotation: dict[str, Any]) -> tuple[bool, str | None, dict[str, Any] | None]:
    """Validate annotation dictionary against UnifiedAnnotation model.
    
    Args:
        annotation: Annotation dictionary to validate
        
    Returns:
        Tuple of (is_valid, error_message, validated_annotation)
        - is_valid: True if validation passed
        - error_message: Error description if validation failed, None otherwise
        - validated_annotation: Validated UnifiedAnnotation model if valid, None otherwise
    """
    if not HAS_PYDANTIC:
        # Without Pydantic, do basic validation
        required = ["card1", "card2", "similarity_score", "source"]
        missing = [f for f in required if f not in annotation]
        if missing:
            return False, f"Missing required fields: {missing}", None
        
        score = annotation.get("similarity_score")
        if not isinstance(score, (int, float)) or not (0.0 <= score <= 1.0):
            return False, f"Invalid similarity_score: {score}", None
        
        return True, None, annotation
    
    try:
        validated = UnifiedAnnotation(**annotation)
        return True, None, validated.model_dump_for_storage()
    except Exception as e:
        return False, str(e), None


def validate_annotations_batch(
    annotations: list[dict[str, Any]],
    strict: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Validate a batch of annotations.
    
    Args:
        annotations: List of annotation dictionaries
        strict: If True, only return validated annotations. If False, return all with validation status.
        
    Returns:
        Tuple of (valid_annotations, invalid_annotations, error_messages)
    """
    valid = []
    invalid = []
    errors = []
    
    for i, ann in enumerate(annotations):
        is_valid, error_msg, validated = validate_annotation(ann)
        
        if is_valid and validated:
            valid.append(validated)
        else:
            invalid.append(ann)
            error_msg = error_msg or "Unknown validation error"
            errors.append(f"Annotation {i}: {error_msg}")
    
    return valid, invalid, errors


