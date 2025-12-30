#!/usr/bin/env python3
"""
Compatibility shim to aid test subprocess invocations.
Delegates to src/ml/archetype_staples.py if present.
"""

from pathlib import Path
import runpy

target = Path(__file__).parent / "src" / "ml" / "archetype_staples.py"
if target.exists():
    runpy.run_path(str(target))
else:
    print("Analyzing archetype staples (shim)")




