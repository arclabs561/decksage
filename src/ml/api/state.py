"""
Runtime state helpers for the DeckSage API.

Extracted from models.py to break the circular import between models.py and api.py.
models.py defines types; state.py accesses runtime state (app.state).
"""

import os

from fastapi import HTTPException

from .models import SUPPORTED_GAMES, ApiState


def _normalize_game(game: str | None) -> str | None:
    if game is None:
        return None
    g = str(game).strip().lower()
    return g or None


def _default_game() -> str:
    # Lazy import: app is defined in api.py
    from .api import app

    try:
        g = getattr(app.state, "default_game", None)
        if isinstance(g, str) and g.strip():
            return g.strip().lower()
    except AttributeError:
        pass
    return os.getenv("DECKSAGE_DEFAULT_GAME", "magic").strip().lower() or "magic"


def _configured_games() -> list[str]:
    """Return configured games from app state (fallback: [default_game])."""
    # Lazy import: app is defined in api.py
    from .api import app

    try:
        games = getattr(app.state, "games", None)
        if isinstance(games, list) and games:
            return [str(g).strip().lower() for g in games if str(g).strip()]
    except AttributeError:
        pass
    # Fallback to a single default game
    return [_default_game()]


def _require_game(game: str | None) -> str:
    """
    Require an explicit game in multi-game mode.

    - If only one game is configured, default to it.
    - If multiple games are configured, require request to specify it.
    """
    cfg = _configured_games()
    g = _normalize_game(game)
    if g is None:
        if len(cfg) == 1:
            g = cfg[0]
        else:
            raise HTTPException(
                status_code=400,
                detail=f"game is required (configured_games={cfg})",
            )
    if g not in SUPPORTED_GAMES:
        raise HTTPException(status_code=400, detail=f"Unknown game: {game}")
    return g


def get_state(game: str | None = None) -> ApiState:
    """
    Get (or create) the API state for a specific game.

    In single-game mode, callers may omit `game` and the default game is used.
    In multi-game mode, request handlers should call `_require_game(...)` and
    pass the resolved game here.
    """
    # Lazy import: app is defined in api.py
    from .api import app

    # Store per-game state in app.state
    by_game = getattr(app.state, "api_by_game", None)
    if by_game is None:
        by_game = {}
        app.state.api_by_game = by_game

    g = _normalize_game(game) or _default_game()
    if g not in SUPPORTED_GAMES:
        # Keep this as ValueError (not HTTPException) so non-request call sites
        # don't accidentally turn into 4xx responses.
        raise ValueError(f"Unknown game: {game}")

    state = by_game.get(g)
    if state is None:
        state = ApiState()
        by_game[g] = state
    return state
