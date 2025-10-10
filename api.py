"""
Compatibility shim for legacy imports.

Allows `import api` to resolve to `src.ml.api.api` (the FastAPI module) so
relative imports work and tests that set module-level globals continue to function.
"""

import importlib
import sys

try:
    # Prefer the explicit module containing FastAPI app
    _real = importlib.import_module("src.ml.api.api")
except ModuleNotFoundError:
    # Fallback when installed as a package: import from top-level `ml`
    _real = importlib.import_module("ml.api.api")

sys.modules[__name__] = _real





