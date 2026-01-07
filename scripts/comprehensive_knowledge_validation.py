#!/usr/bin/env python3
"""Comprehensive validation of the entire knowledge injection system."""

import json
import sys
from pathlib import Path


def validate_json_structure():
    """Validate JSON file structure."""
    print("1. Validating JSON structure...")
    project_root = Path(__file__).parent.parent
    knowledge_dir = project_root / "data" / "game_knowledge"
    
    files = list(knowledge_dir.glob("*.json"))
    all_valid = True
    
    for f in files:
        try:
            with open(f, encoding="utf-8") as file:
                data = json.load(file)
            
            # Check required fields
            required = ["game", "mechanics", "archetypes", "formats"]
            for field in required:
                if field not in data:
                    print(f"  ✗ {f.name}: Missing {field}")
                    all_valid = False
                    continue
            
            # Check data types
            if not isinstance(data["game"], str):
                print(f"  ✗ {f.name}: 'game' must be string")
                all_valid = False
            if not isinstance(data["archetypes"], list) or len(data["archetypes"]) == 0:
                print(f"  ✗ {f.name}: 'archetypes' must be non-empty array")
                all_valid = False
            if not isinstance(data["formats"], list) or len(data["formats"]) == 0:
                print(f"  ✗ {f.name}: 'formats' must be non-empty array")
                all_valid = False
            
            if all_valid:
                print(f"  ✓ {f.name}: Structure valid")
        except Exception as e:
            print(f"  ✗ {f.name}: {e}")
            all_valid = False
    
    return all_valid


def validate_content_quality():
    """Validate content quality and completeness."""
    print("\n2. Validating content quality...")
    project_root = Path(__file__).parent.parent
    knowledge_dir = project_root / "data" / "game_knowledge"
    
    files = list(knowledge_dir.glob("*.json"))
    all_valid = True
    
    for f in files:
        with open(f, encoding="utf-8") as file:
            data = json.load(file)
        
        game = data.get("game", "")
        
        # Check mechanics completeness
        mechanics = data.get("mechanics", {})
        if not mechanics.get("mana_system") and not mechanics.get("energy_system"):
            print(f"  ⚠ {f.name}: Missing resource system description")
        
        # Check archetype completeness
        archetypes = data.get("archetypes", [])
        for i, arch in enumerate(archetypes):
            if not arch.get("core_cards"):
                print(f"  ⚠ {f.name}: Archetype '{arch.get('name')}' has no core cards")
        
        # Check format completeness
        formats = data.get("formats", [])
        for i, fmt in enumerate(formats):
            if not fmt.get("meta_context"):
                print(f"  ⚠ {f.name}: Format '{fmt.get('name')}' has no meta context")
        
        # Check examples
        examples = data.get("examples", [])
        if len(examples) < 2:
            print(f"  ⚠ {f.name}: Only {len(examples)} examples (recommend 3+)")
        
        print(f"  ✓ {f.name}: Content quality acceptable")
    
    return True


def validate_integration():
    """Validate integration points."""
    print("\n3. Validating integration points...")
    project_root = Path(__file__).parent.parent
    
    integration_files = [
        project_root / "src" / "ml" / "annotation" / "llm_annotator.py",
        project_root / "src" / "ml" / "scripts" / "generate_labels_enhanced.py",
    ]
    
    all_valid = True
    for f in integration_files:
        if not f.exists():
            print(f"  ✗ {f.name}: File not found")
            all_valid = False
            continue
        
        content = f.read_text(encoding="utf-8")
        
        # Check for knowledge import
        if "retrieve_game_knowledge" not in content and "GameKnowledgeBase" not in content:
            print(f"  ⚠ {f.name}: No knowledge injection found")
        elif "try:" in content and "except" in content:
            print(f"  ✓ {f.name}: Has error handling")
        else:
            print(f"  ⚠ {f.name}: Missing error handling")
    
    return all_valid


def validate_file_sizes():
    """Validate file sizes are reasonable."""
    print("\n4. Validating file sizes...")
    project_root = Path(__file__).parent.parent
    knowledge_dir = project_root / "data" / "game_knowledge"
    
    files = list(knowledge_dir.glob("*.json"))
    all_valid = True
    
    for f in files:
        size = f.stat().st_size
        if size > 1_000_000:  # 1MB
            print(f"  ⚠ {f.name}: Large file ({size:,} bytes)")
        elif size < 100:  # 100 bytes
            print(f"  ⚠ {f.name}: Very small file ({size:,} bytes)")
        else:
            print(f"  ✓ {f.name}: Size OK ({size:,} bytes)")
    
    return all_valid


def main():
    """Run all validations."""
    print("=" * 60)
    print("Comprehensive Knowledge System Validation")
    print("=" * 60)
    print()
    
    results = [
        validate_json_structure(),
        validate_content_quality(),
        validate_integration(),
        validate_file_sizes(),
    ]
    
    print("\n" + "=" * 60)
    if all(results):
        print("✓ All validations passed")
        sys.exit(0)
    else:
        print("✗ Some validations failed or have warnings")
        sys.exit(1)


if __name__ == "__main__":
    main()

