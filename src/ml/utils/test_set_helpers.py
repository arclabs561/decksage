#!/usr/bin/env python3
"""
Test Set Helper Utilities

Integrated utilities for test set management that work with existing scripts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .data_loading import load_test_set
from .paths import PATHS

logger = logging.getLogger(__name__)


def ensure_test_set_has_metadata(
    test_set_path: Path,
    game: str = "magic",
    auto_add: bool = False,
) -> Path:
    """
    Ensure test set has format/archetype metadata.
    
    If metadata is missing and auto_add=True, adds it automatically.
    Returns path to test set (may be different if metadata was added).
    """
    # Load test set
    data = load_test_set(path=test_set_path)
    queries = data.get("queries", data) if isinstance(data, dict) else data
    
    # Check if metadata exists
    has_metadata = False
    for query_data in queries.values():
        if isinstance(query_data, dict) and ("format" in query_data or "archetype" in query_data):
            has_metadata = True
            break
    
    if has_metadata:
        return test_set_path
    
    if not auto_add:
        logger.warning(f"Test set {test_set_path} lacks format/archetype metadata")
        return test_set_path
    
    # Add metadata
    logger.info(f"Adding format/archetype metadata to {test_set_path}...")
    try:
        from ..scripts.add_format_metadata_to_test_set import add_metadata_to_test_set
        
        metadata_path = test_set_path.parent / f"{test_set_path.stem}_with_metadata.json"
        add_metadata_to_test_set(
            test_set_path=test_set_path,
            output_path=metadata_path,
            game=game,
        )
        return metadata_path
    except Exception as e:
        logger.warning(f"Failed to add metadata: {e}, using original test set")
        return test_set_path


def ensure_test_set_size(
    test_set_path: Path,
    game: str = "magic",
    min_size: int = 100,
    auto_expand: bool = False,
) -> Path:
    """
    Ensure test set meets minimum size requirement.
    
    If too small and auto_expand=True, expands it automatically.
    Returns path to test set (may be different if expansion occurred).
    """
    # Load test set
    data = load_test_set(path=test_set_path)
    queries = data.get("queries", data) if isinstance(data, dict) else data
    current_size = len(queries)
    
    if current_size >= min_size:
        return test_set_path
    
    if not auto_expand:
        logger.warning(f"Test set {test_set_path} has only {current_size} queries (minimum: {min_size})")
        return test_set_path
    
    # Expand test set
    logger.info(f"Expanding test set from {current_size} to {min_size} queries...")
    try:
        if game == "pokemon":
            from ..scripts.expand_pokemon_test_set import expand_pokemon_test_set
            
            expanded_path = test_set_path.parent / f"{test_set_path.stem}_expanded.json"
            expand_pokemon_test_set(
                existing_test_set_path=test_set_path,
                output_path=expanded_path,
                target_size=min_size,
            )
            return expanded_path
        else:
            logger.warning(f"Auto-expansion not yet implemented for {game}")
            return test_set_path
    except Exception as e:
        logger.warning(f"Failed to expand test set: {e}, using original")
        return test_set_path


def load_test_set_with_validation(
    test_set_path: Path,
    game: str = "magic",
    min_queries: int = 100,
    min_labels: int = 5,
    auto_fix: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Load test set with validation and optional auto-fixing.
    
    Returns:
        (test_set_data, validation_results)
    
    Note: This function loads the test set directly (not via load_test_set) to avoid
    circular dependency when validation is enabled.
    """
    # Load test set directly (avoid circular dependency with load_test_set(validate=True))
    if not test_set_path.exists():
        return {}, {"valid": False, "error": f"Test set not found: {test_set_path}"}
    
    try:
        import json
        with open(test_set_path) as f:
            test_set_data = json.load(f)
        
        # Handle both formats
        queries = test_set_data.get("queries", test_set_data) if isinstance(test_set_data, dict) else test_set_data
        if not queries or (isinstance(queries, dict) and len(queries) == 0):
            return {}, {"valid": False, "error": "Test set is empty"}
    except Exception as e:
        return {}, {"valid": False, "error": f"Failed to load test set: {e}"}
    
    # Validate
    try:
        from ..evaluation.test_set_validation import validate_test_set_coverage
        
        validation_result = validate_test_set_coverage(
            test_set_path=test_set_path,
            min_queries=min_queries,
            min_labels_per_query=min_labels,
        )
        
        # Auto-fix if requested and issues found
        if auto_fix and not validation_result["valid"]:
            # Try to expand if too small
            current_size = validation_result["stats"]["total_queries"]
            if current_size < min_queries:
                expanded_path = ensure_test_set_size(
                    test_set_path=test_set_path,
                    game=game,
                    min_size=min_queries,
                    auto_expand=True,
                )
                if expanded_path != test_set_path:
                    # Reload from expanded path (directly, not via load_test_set to avoid circular dependency)
                    try:
                        import json
                        with open(expanded_path) as f:
                            expanded_data = json.load(f)
                        queries = expanded_data.get("queries", expanded_data) if isinstance(expanded_data, dict) else expanded_data
                        test_set_data = expanded_data if isinstance(expanded_data, dict) and "queries" in expanded_data else {"queries": queries}
                    except Exception as e:
                        logger.warning(f"Failed to reload expanded test set: {e}")
                        # Continue with original data
                    # Re-validate
                    validation_result = validate_test_set_coverage(
                        test_set_path=expanded_path,
                        min_queries=min_queries,
                        min_labels_per_query=min_labels,
                    )
        
        return test_set_data, validation_result
    except Exception as e:
        logger.warning(f"Test set validation failed: {e}")
        return test_set_data, {"valid": False, "error": str(e)}


def get_test_set_path(
    game: str = "magic",
    prefer_expanded: bool = True,
    prefer_with_metadata: bool = True,
) -> Path:
    """
    Get best available test set path for a game.
    
    Prefers expanded versions and versions with metadata if available.
    """
    try:
        base_path = getattr(PATHS, f"test_{game}")
    except AttributeError:
        # Fallback: construct path manually
        base_path = PATHS.experiments / f"test_set_unified_{game}.json"
    
    # Check for expanded version
    if prefer_expanded:
        expanded_path = base_path.parent / f"{base_path.stem}_expanded.json"
        if expanded_path.exists():
            base_path = expanded_path
    
    # Check for metadata version
    if prefer_with_metadata:
        metadata_path = base_path.parent / f"{base_path.stem}_with_metadata.json"
        if metadata_path.exists():
            base_path = metadata_path
    
    return base_path

