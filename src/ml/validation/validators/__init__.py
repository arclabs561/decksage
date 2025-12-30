"""Data validators for multi-game card collections."""

# Optional loader import - may not exist
try:
    from .loader import (
        iter_decks_validated,
        load_decks_lenient,
        load_decks_strict,
        load_decks_validated,
        stream_decks_lenient,
    )
except ImportError:
    # Fallback if loader module doesn't exist
    iter_decks_validated = None
    load_decks_lenient = None
    load_decks_strict = None
    load_decks_validated = None
    stream_decks_lenient = None

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
