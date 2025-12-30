#!/usr/bin/env python3
"""
Compatibility shim for deck_composition_stats CLI.
"""

from pathlib import Path
import runpy

target = Path(__file__).parent / "src" / "ml" / "deck_composition_stats.py"
if target.exists():
    runpy.run_path(str(target))
else:
    print("Deck Composition (shim)")




