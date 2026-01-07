#!/usr/bin/env python3
"""Standalone validator for game knowledge JSON files."""

import json
import sys
from pathlib import Path


def validate_structure(data: dict, path: str = "") -> list[str]:
    """Validate knowledge file structure recursively."""
    errors: list[str] = []
    
    # Required top-level fields
    required_fields = ["game", "mechanics", "archetypes", "formats"]
    for field in required_fields:
        if field not in data:
            errors.append(f"{path}Missing required field: {field}")
    
    # Validate game
    if "game" in data and not isinstance(data["game"], str):
        errors.append(f"{path}Field 'game' must be a string")
    
    # Validate mechanics
    if "mechanics" in data:
        if not isinstance(data["mechanics"], dict):
            errors.append(f"{path}Field 'mechanics' must be an object")
        else:
            mech = data["mechanics"]
            if "mana_system" not in mech and "energy_system" not in mech:
                errors.append(f"{path}mechanics: Missing resource system description")
    
    # Validate archetypes
    if "archetypes" in data:
        if not isinstance(data["archetypes"], list):
            errors.append(f"{path}Field 'archetypes' must be an array")
        elif len(data["archetypes"]) == 0:
            errors.append(f"{path}At least one archetype is required")
        else:
            for i, arch in enumerate(data["archetypes"]):
                arch_path = f"{path}archetypes[{i}]."
                if not isinstance(arch, dict):
                    errors.append(f"{arch_path}Must be an object")
                    continue
                for field in ["name", "description", "strategy"]:
                    if field not in arch:
                        errors.append(f"{arch_path}Missing required field: {field}")
                    elif not isinstance(arch[field], str) or not arch[field].strip():
                        errors.append(f"{arch_path}Field '{field}' must be a non-empty string")
    
    # Validate formats
    if "formats" in data:
        if not isinstance(data["formats"], list):
            errors.append(f"{path}Field 'formats' must be an array")
        elif len(data["formats"]) == 0:
            errors.append(f"{path}At least one format is required")
        else:
            for i, fmt in enumerate(data["formats"]):
                fmt_path = f"{path}formats[{i}]."
                if not isinstance(fmt, dict):
                    errors.append(f"{fmt_path}Must be an object")
                    continue
                if "name" not in fmt:
                    errors.append(f"{fmt_path}Missing required field: name")
                elif not isinstance(fmt["name"], str) or not fmt["name"].strip():
                    errors.append(f"{fmt_path}Field 'name' must be a non-empty string")
    
    # Validate examples (optional but should be array if present)
    if "examples" in data:
        if not isinstance(data["examples"], list):
            errors.append(f"{path}Field 'examples' must be an array")
        else:
            for i, ex in enumerate(data["examples"]):
                ex_path = f"{path}examples[{i}]."
                if not isinstance(ex, dict):
                    errors.append(f"{ex_path}Must be an object")
                    continue
                # Check for required fields in examples
                if "card1" not in ex or "card2" not in ex:
                    errors.append(f"{ex_path}Missing card1 or card2")
                if "score" in ex and not isinstance(ex["score"], (int, float)):
                    errors.append(f"{ex_path}Field 'score' must be a number")
                if "score" in ex and (ex["score"] < 0 or ex["score"] > 1):
                    errors.append(f"{ex_path}Field 'score' must be between 0 and 1")
    
    # Validate temporal_context (optional)
    if "temporal_context" in data and not isinstance(data["temporal_context"], dict):
        errors.append(f"{path}Field 'temporal_context' must be an object")
    
    return errors


def validate_file(knowledge_file: Path) -> tuple[bool, list[str]]:
    """Validate a single knowledge file."""
    errors: list[str] = []
    
    if not knowledge_file.exists():
        return False, [f"File not found: {knowledge_file}"]
    
    try:
        with open(knowledge_file, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]
    except Exception as e:
        return False, [f"Error reading file: {e}"]
    
    errors.extend(validate_structure(data))
    
    return len(errors) == 0, errors


def main():
    """Validate all knowledge files."""
    # Find knowledge directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    knowledge_dir = project_root / "data" / "game_knowledge"
    
    if not knowledge_dir.exists():
        print(f"Knowledge directory not found: {knowledge_dir}")
        sys.exit(1)
    
    files = list(knowledge_dir.glob("*.json"))
    if not files:
        print(f"No JSON files found in {knowledge_dir}")
        sys.exit(1)
    
    print(f"Validating {len(files)} knowledge files in {knowledge_dir}\n")
    
    all_valid = True
    for knowledge_file in sorted(files):
        print(f"Validating {knowledge_file.name}...")
        is_valid, errors = validate_file(knowledge_file)
        
        if is_valid:
            print(f"  ✓ {knowledge_file.name} is valid")
        else:
            print(f"  ✗ {knowledge_file.name} has errors:")
            for error in errors:
                print(f"    - {error}")
            all_valid = False
        print()
    
    if all_valid:
        print("✓ All knowledge files are valid")
        sys.exit(0)
    else:
        print("✗ Some knowledge files have errors")
        sys.exit(1)


if __name__ == "__main__":
    main()

