#!/usr/bin/env python3
"""
Add cost tracking to all LLM scripts.

This script modifies all LLM-using scripts to include cost tracking.
Run this once to update all scripts, or manually integrate tracking.
"""

from __future__ import annotations

import re
from pathlib import Path

LLM_SCRIPTS = [
    "src/ml/scripts/generate_labels_enhanced.py",
    "src/ml/scripts/generate_queries_enhanced.py",
    "src/ml/scripts/generate_substitution_pairs_llm.py",
    "src/ml/scripts/generate_labels_multi_judge.py",
    "src/ml/scripts/expand_test_set_with_llm.py",
    "src/ml/scripts/batch_label_existing_queries.py",
]

IMPORT_BLOCK = """
# Import cost tracker
try:
    from ml.utils.llm_cost_tracker import get_global_tracker, LLMCostTracker
    from ml.utils.pydantic_ai_helpers import run_with_tracking
    HAS_COST_TRACKER = True
except ImportError:
    HAS_COST_TRACKER = False
    get_global_tracker = None
    run_with_tracking = None
"""

def add_cost_tracking_to_script(script_path: Path):
    """Add cost tracking imports and usage to a script."""
    if not script_path.exists():
        print(f"⚠️  Script not found: {script_path}")
        return False
    
    content = script_path.read_text()
    
    # Check if already has cost tracking
    if "llm_cost_tracker" in content:
        print(f"✓ Already has cost tracking: {script_path}")
        return True
    
    # Add imports after sys.path setup
    if "sys.path.insert" in content and IMPORT_BLOCK not in content:
        # Find the last sys.path.insert block
        pattern = r'(sys\.path\.insert\([^)]+\)\s*\n)'
        matches = list(re.finditer(pattern, content))
        if matches:
            last_match = matches[-1]
            insert_pos = last_match.end()
            content = content[:insert_pos] + IMPORT_BLOCK + content[insert_pos:]
            print(f"✓ Added imports to: {script_path}")
        else:
            # Add at top after existing imports
            if "# Fix import path" in content:
                insert_pos = content.find("# Fix import path")
                content = content[:insert_pos] + IMPORT_BLOCK + "\n" + content[insert_pos:]
                print(f"✓ Added imports to: {script_path}")
            else:
                print(f"⚠️  Could not find insertion point: {script_path}")
                return False
    
    # Replace agent.run_sync with run_with_tracking
    old_pattern = r'result\s*=\s*agent\.run_sync\(([^)]+)\)'
    new_pattern = r'''result = run_with_tracking(
                agent=agent,
                prompt=\1,
                model=model_name,
                provider=provider,
                operation="\2",
            ) if (HAS_COST_TRACKER and run_with_tracking) else agent.run_sync(\1)'''
    
    # This is complex - better to do manual replacements per script
    # For now, just add the imports
    
    script_path.write_text(content)
    return True


def main():
    """Add cost tracking to all LLM scripts."""
    print("Adding cost tracking to LLM scripts...\n")
    
    for script_rel in LLM_SCRIPTS:
        script_path = Path(script_path)
        if script_path.exists():
            add_cost_tracking_to_script(script_path)
        else:
            print(f"⚠️  Not found: {script_path}")
    
    print("\n✅ Done! Manual integration may be needed for agent.run_sync calls.")


if __name__ == "__main__":
    main()

