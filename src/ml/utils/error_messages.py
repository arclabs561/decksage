#!/usr/bin/env python3
"""
Standardized error messages for consistent error handling across the codebase.
"""

from __future__ import annotations


class ErrorMessages:
    """Standardized error messages."""

    # Embedding errors
    EMBEDDINGS_NOT_LOADED = "Embeddings not loaded"
    EMBEDDINGS_NOT_AVAILABLE = "Embeddings not available"
    CARD_NOT_IN_EMBEDDINGS = "Card not found in embeddings"

    # Graph errors
    GRAPH_NOT_LOADED = "Graph data not loaded"
    GRAPH_NOT_AVAILABLE = "Graph data not available"
    CARD_NOT_IN_GRAPH = "Card not found in graph"

    # Tagger errors
    TAGGER_NOT_AVAILABLE = "Functional tagger not available"
    TAGGER_LOAD_FAILED = "Failed to load functional tagger"

    # Fusion errors
    FUSION_NOT_AVAILABLE = "Fusion system not available"
    FUSION_LOAD_FAILED = "Failed to load fusion system"
    INVALID_FUSION_WEIGHTS = "Invalid fusion weights"

    # Deck errors
    DECK_NOT_FOUND = "Deck not found"
    DECK_INVALID = "Invalid deck format"
    DECK_EMPTY = "Deck is empty"
    DECK_COMPLETION_FAILED = "Deck completion failed"
    DECK_PATCH_NOT_AVAILABLE = "deck_patch module not available"

    # Validation errors
    VALIDATION_FAILED = "Validation failed"
    TEMPORAL_SPLIT_VIOLATION = "Temporal split violation detected - potential data leakage"
    TEST_SET_TOO_SMALL = "Test set too small"
    TEST_SET_MALFORMED = "Test set malformed"

    # Asset loading errors
    ASSETS_LOAD_FAILED = "Failed to load trained assets"
    EMBEDDINGS_LOAD_FAILED = "Failed to load embeddings"
    GRAPH_LOAD_FAILED = "Failed to load graph"
    TEXT_EMBEDDINGS_LOAD_FAILED = "Failed to load text embeddings"
    GNN_EMBEDDINGS_LOAD_FAILED = "Failed to load GNN embeddings"

    # API errors
    API_NOT_READY = "API not ready"
    API_EMBEDDINGS_MISSING = "Embeddings not loaded"
    API_GRAPH_MISSING = "Graph data not loaded"

    # File errors
    FILE_NOT_FOUND = "File not found"
    FILE_READ_ERROR = "Error reading file"
    FILE_WRITE_ERROR = "Error writing file"
    FILE_PERMISSION_ERROR = "Permission denied"

    # Data errors
    DATA_LEAKAGE_DETECTED = "Data leakage detected"
    INVALID_DATA_FORMAT = "Invalid data format"
    MISSING_REQUIRED_FIELD = "Missing required field"

    @classmethod
    def format(cls, message: str, **kwargs: str) -> str:
        """
        Format error message with keyword arguments.

        Args:
            message: Error message template or key
            **kwargs: Format arguments

        Returns:
            Formatted error message

        Examples:
            >>> ErrorMessages.format("Card {card} not found", card="Lightning Bolt")
            'Card Lightning Bolt not found'
        """
        if hasattr(cls, message):
            template = getattr(cls, message)
        else:
            template = message

        try:
            return template.format(**kwargs)
        except KeyError:
            # If formatting fails, return template as-is
            return template


def get_error_message(key: str, **kwargs: str) -> str:
    """
    Get standardized error message.

    Args:
        key: Error message key (attribute name from ErrorMessages)
        **kwargs: Format arguments

    Returns:
        Formatted error message

    Examples:
        >>> get_error_message("EMBEDDINGS_NOT_LOADED")
        'Embeddings not loaded'
    """
    return ErrorMessages.format(key, **kwargs)




