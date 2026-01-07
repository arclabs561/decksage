#!/usr/bin/env python3
"""Validate knowledge injection integration points."""

import ast
import re
import sys
from pathlib import Path


def check_imports(file_path: Path) -> list[str]:
    """Check if file imports knowledge module correctly."""
    errors: list[str] = []
    
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        
        # Check for knowledge import
        if "retrieve_game_knowledge" in content or "GameKnowledgeBase" in content:
            # Check import style
            if "from ..knowledge import" in content or "from ml.knowledge import" in content:
                # Check error handling
                if "try:" in content and "except" in content:
                    # Check if exception handling is around knowledge retrieval
                    lines = content.split("\n")
                    in_try = False
                    has_knowledge_in_try = False
                    for i, line in enumerate(lines):
                        if "try:" in line:
                            in_try = True
                        elif "except" in line:
                            in_try = False
                        elif in_try and ("retrieve_game_knowledge" in line or "GameKnowledgeBase" in line):
                            has_knowledge_in_try = True
                    
                    if not has_knowledge_in_try:
                        errors.append("Knowledge retrieval should be in try/except block")
                else:
                    errors.append("Knowledge retrieval should have error handling")
            else:
                errors.append("Should import from ml.knowledge or ..knowledge")
        
        return errors
    except Exception as e:
        return [f"Error checking file: {e}"]


def validate_integration_points():
    """Validate all integration points."""
    project_root = Path(__file__).parent.parent
    integration_files = [
        project_root / "src" / "ml" / "annotation" / "llm_annotator.py",
        project_root / "src" / "ml" / "scripts" / "generate_labels_enhanced.py",
    ]
    
    print("Validating knowledge injection integration points...\n")
    
    all_valid = True
    for file_path in integration_files:
        if not file_path.exists():
            print(f"✗ File not found: {file_path}")
            all_valid = False
            continue
        
        print(f"Checking {file_path.name}...")
        errors = check_imports(file_path)
        
        if errors:
            print(f"  ✗ Issues found:")
            for error in errors:
                print(f"    - {error}")
            all_valid = False
        else:
            print(f"  ✓ Integration looks good")
        print()
    
    return all_valid


def check_knowledge_files_exist():
    """Check that knowledge files exist."""
    project_root = Path(__file__).parent.parent
    knowledge_dir = project_root / "data" / "game_knowledge"
    
    required_files = ["magic.json", "pokemon.json", "yugioh.json"]
    missing = []
    
    for filename in required_files:
        if not (knowledge_dir / filename).exists():
            missing.append(filename)
    
    if missing:
        print(f"✗ Missing knowledge files: {', '.join(missing)}")
        return False
    else:
        print(f"✓ All required knowledge files exist")
        return True


if __name__ == "__main__":
    print("=" * 60)
    print("Knowledge Integration Validation")
    print("=" * 60)
    print()
    
    files_ok = check_knowledge_files_exist()
    print()
    
    integration_ok = validate_integration_points()
    
    print("=" * 60)
    if files_ok and integration_ok:
        print("✓ All validations passed")
        sys.exit(0)
    else:
        print("✗ Some validations failed")
        sys.exit(1)

