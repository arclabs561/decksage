#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Update scraping targets with better coverage thresholds.

Based on statistical analysis:
- Minimum viable: 20 decks (can train basic model)
- Good coverage: 50 decks (statistical significance)  
- Excellent: 100+ decks (robust training)
- For rare/niche archetypes: 20 is acceptable
"""

import json
import sys
from pathlib import Path
from typing import Any


def calculate_target(current: int, format: str, archetype: str) -> int:
    """Calculate target based on current coverage and format popularity."""
    # Base targets by format popularity
    format_targets = {
        "Modern": 100,      # Most popular, need robust training
        "Legacy": 80,       # Popular competitive format
        "Standard": 80,     # Rotating but important
        "Pioneer": 70,      # Growing format
        "Pauper": 60,       # Budget format, good coverage
        "Vintage": 50,      # Niche but important
        "Premodern": 50,    # Niche format
        "cEDH": 50,         # Competitive Commander (many archetypes)
        "Duel Commander": 50,  # 1v1 Commander
        "Peasant": 30,      # Very niche
        "Highlander": 30,    # Very niche
    }
    
    # Base target from format
    base_target = format_targets.get(format, 50)
    
    # Adjust for current coverage
    if current == 0:
        # New archetype - aim for minimum viable
        return 20
    elif current < 10:
        # Very low coverage - prioritize to minimum viable
        return 20
    elif current < 20:
        # Below minimum - get to minimum
        return 20
    elif current < 50:
        # Below good coverage - aim for good
        return min(50, base_target)
    elif current < 100:
        # Below excellent - aim for excellent if format supports it
        return min(100, base_target)
    else:
        # Already well covered - maintain or slight increase
        return min(current + 20, base_target)


def update_targets(input_path: Path, output_path: Path | None = None) -> int:
    """Update scraping targets with better thresholds."""
    if output_path is None:
        output_path = input_path
    
    with open(input_path) as f:
        targets = json.load(f)
    
    updated = 0
    for target in targets:
        old_needed = target["needed"]
        new_needed = calculate_target(
            target["current"],
            target["format"],
            target["archetype"]
        )
        
        if new_needed != old_needed:
            target["needed"] = new_needed
            updated += 1
        
        # Update priority based on gap
        gap = new_needed - target["current"]
        if gap >= 30:
            target["priority"] = "critical"
        elif gap >= 15:
            target["priority"] = "high"
        elif gap >= 5:
            target["priority"] = "moderate"
        else:
            target["priority"] = "low"
    
    with open(output_path, "w") as f:
        json.dump(targets, f, indent=2)
    
    print(f"Updated {updated} targets")
    print(f"Priority distribution:")
    priorities = {}
    for t in targets:
        priorities[t["priority"]] = priorities.get(t["priority"], 0) + 1
    for prio, count in sorted(priorities.items()):
        print(f"  {prio}: {count}")
    
    return 0


if __name__ == "__main__":
    input_path = Path("data/scraping_targets.json")
    if len(sys.argv) > 1:
        input_path = Path(sys.argv[1])
    
    sys.exit(update_targets(input_path))

