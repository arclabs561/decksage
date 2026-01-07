"""
Pydantic models for deck export schema validation.

Defines the schema for deck exports from Go backend, enabling cross-language
validation and versioning.
"""

from __future__ import annotations


try:
    from pydantic import BaseModel, Field, field_validator

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

    # Create minimal stubs for type checking
    class BaseModel:
        pass

    def Field(*args, **kwargs):
        return None

    def field_validator(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


class CardInDeck(BaseModel):
    """Card in deck structure matching Go export format."""

    name: str = Field(..., description="Card name")
    count: int = Field(..., ge=1, description="Number of copies")
    partition: str = Field(..., description="Deck partition (mainboard, sideboard, etc.)")


class DeckExport(BaseModel):
    """
    Deck export schema matching Go backend output.

    This model validates the JSONL format exported by Go export-hetero tool.
    Used for cross-language schema validation and versioning.
    """

    deck_id: str = Field(..., description="Unique deck identifier")
    archetype: str | None = Field(None, description="Deck archetype")
    format: str | None = Field(None, description="Format name")
    url: str | None = Field(None, description="Source URL")
    source: str | None = Field(None, description="Data source")
    player: str | None = Field(None, description="Player name")
    event: str | None = Field(None, description="Event name")
    placement: int | None = Field(None, ge=0, description="Tournament placement")
    event_date: str | None = Field(None, description="Event date (ISO format)")
    scraped_at: str = Field(..., description="Scrape timestamp (ISO format)")
    cards: list[CardInDeck] = Field(..., min_length=1, description="Cards in deck")

    # Backward compatibility aliases (Go exports these)
    timestamp: str | None = Field(None, description="Alias for scraped_at (backward compat)")
    created_at: str | None = Field(None, description="Alias for scraped_at (backward compat)")

    # Export version metadata (added for schema validation)
    export_version: str = Field("1.0", description="Export format version")

    @field_validator("cards")
    @classmethod
    def validate_cards_not_empty(cls, v: list[CardInDeck]) -> list[CardInDeck]:
        """Ensure deck has at least one card."""
        if not v:
            raise ValueError("Deck must have at least one card")
        return v

    @classmethod
    def model_json_schema(cls) -> dict:
        """Generate JSON Schema for cross-language validation."""
        if not HAS_PYDANTIC:
            return {}
        return super().model_json_schema()

    model_config = {
        # Allow backward compatibility aliases
        "populate_by_name": True,
        # Allow extra fields for forward compatibility
        "extra": "allow",
    }


def validate_deck_record(
    record: dict, strict: bool = False
) -> tuple[bool, str | None, dict | None]:
    """
    Validate deck record against schema.

    Args:
        record: Deck record dictionary from JSONL
        strict: If True, return error on validation failure. If False, log warning.

    Returns:
        Tuple of (is_valid, error_message, validated_record)
        - is_valid: True if validation passed
        - error_message: Error description if validation failed, None otherwise
        - validated_record: Validated and normalized record if valid, None otherwise
    """
    if not HAS_PYDANTIC:
        # Without Pydantic, do basic validation
        required = ["deck_id", "scraped_at", "cards"]
        missing = [f for f in required if f not in record]
        if missing:
            return False, f"Missing required fields: {missing}", None

        if not isinstance(record.get("cards"), list) or len(record.get("cards", [])) == 0:
            return False, "Cards must be a non-empty list", None

        return True, None, record

    try:
        # Handle backward compatibility aliases
        if "timestamp" in record and "scraped_at" not in record:
            record["scraped_at"] = record["timestamp"]
        if "created_at" in record and "scraped_at" not in record:
            record["scraped_at"] = record["created_at"]

        # Add default export_version if missing
        if "export_version" not in record:
            record["export_version"] = "1.0"

        validated = DeckExport(**record)
        return True, None, validated.model_dump(exclude_none=False)
    except Exception as e:
        if strict:
            return False, str(e), None
        else:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Schema validation warning: {e}")
            return True, None, record  # Return original record in non-strict mode
