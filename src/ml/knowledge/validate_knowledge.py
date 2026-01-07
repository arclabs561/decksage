#!/usr/bin/env python3
"""Validate game knowledge JSON files."""

import json
import sys
from pathlib import Path

# Allow running as script
if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Add src to path
    src_path = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(src_path))

from ml.knowledge.models import GameKnowledge


def validate_knowledge_file(knowledge_file: Path) -> tuple[bool, list[str]]:
    """
    Validate a game knowledge JSON file.

    Args:
        knowledge_file: Path to knowledge JSON file

    Returns:
        Tuple of (is_valid, list of errors)
    """
    errors: list[str] = []

    if not knowledge_file.exists():
        return False, [f"File not found: {knowledge_file}"]

    try:
        with open(knowledge_file) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]

    try:
        knowledge = GameKnowledge(**data)
    except Exception as e:
        return False, [f"Invalid structure: {e}"]

    # Additional validation
    if not knowledge.game:
        errors.append("Game name is required")

    if not knowledge.mechanics:
        errors.append("Mechanics are required")

    if not knowledge.archetypes:
        errors.append("At least one archetype is required")

    if not knowledge.formats:
        errors.append("At least one format is required")

    # Validate archetypes
    for i, arch in enumerate(knowledge.archetypes):
        if not arch.name:
            errors.append(f"Archetype {i} missing name")
        if not arch.description:
            errors.append(f"Archetype {i} missing description")
        if not arch.strategy:
            errors.append(f"Archetype {i} missing strategy")

    # Validate formats
    for i, fmt in enumerate(knowledge.formats):
        if not fmt.name:
            errors.append(f"Format {i} missing name")

    return len(errors) == 0, errors


def main():
    """Validate all knowledge files."""
    import os
    from pathlib import Path
    
    # Find knowledge directory without importing PATHS
    env_root = os.getenv("DECKSAGE_ROOT")
    if env_root:
        knowledge_dir = Path(env_root) / "data" / "game_knowledge"
    else:
        # Try relative to this file
        current = Path(__file__).parent.parent.parent.parent
        knowledge_dir = current / "data" / "game_knowledge"

    if not knowledge_dir.exists():
        print(f"Knowledge directory not found: {knowledge_dir}")
        sys.exit(1)

    all_valid = True
    for knowledge_file in knowledge_dir.glob("*.json"):
        print(f"Validating {knowledge_file.name}...")
        is_valid, errors = validate_knowledge_file(knowledge_file)

        if is_valid:
            print(f"  ✓ {knowledge_file.name} is valid")
        else:
            print(f"  ✗ {knowledge_file.name} has errors:")
            for error in errors:
                print(f"    - {error}")
            all_valid = False

    if all_valid:
        print("\n✓ All knowledge files are valid")
        sys.exit(0)
    else:
        print("\n✗ Some knowledge files have errors")
        sys.exit(1)


if __name__ == "__main__":
    main()

