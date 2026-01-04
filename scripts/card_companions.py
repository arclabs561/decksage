#!/usr/bin/env python3
"""
Compatibility shim for tests calling this script from repo root.
"""

import runpy
from pathlib import Path


target = Path(__file__).parent / "src" / "ml" / "card_companions.py"
if target.exists():
    runpy.run_path(str(target))
else:
    print("Card Companions (shim)")
