"""Data validators for multi-game card collections.

These are **deterministic** validators. If imports fail, that is a real
environment/config error and should not be silently papered over.
"""

from .loader import (
    iter_decks_validated,
    load_decks_lenient,
    load_decks_strict,
    load_decks_validated,
    stream_decks_lenient,
)
from .models import (
    BASIC_LANDS,
    CardDesc,
    Collection,
    MTGDeck,
    Partition,
    PokemonDeck,
    YugiohDeck,
)


__all__ = [
    "BASIC_LANDS",
    "CardDesc",
    "Collection",
    "MTGDeck",
    "Partition",
    "PokemonDeck",
    "YugiohDeck",
    "iter_decks_validated",
    "load_decks_lenient",
    "load_decks_strict",
    "load_decks_validated",
    "stream_decks_lenient",
]
