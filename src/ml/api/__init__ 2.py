"""API package for DeckSage.

Exposes the FastAPI app and helpers via the `api` module.
"""

# Re-export common entrypoints for convenience
from .api import app, get_state  # noqa: F401
