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

try:
    from .models import (
        BASIC_LANDS,
        CardDesc,
        Collection,
        MTGDeck,
        Partition,
        PokemonDeck,
        YugiohDeck,
    )
except ImportError:
    # Models file doesn't exist - create minimal stubs for compatibility
    from pydantic import BaseModel, Field
    from typing import Optional
    
    class CardDesc(BaseModel):
        name: str
        count: int
    
    class Partition(BaseModel):
        name: str
        cards: list[CardDesc]
        
        def total_cards(self) -> int:
            return sum(c.count for c in self.cards)
    
    class MTGDeck(BaseModel):
        deck_id: str
        format: str
        archetype: Optional[str] = None
        partitions: list[Partition]
        
        def get_all_cards(self) -> list[CardDesc]:
            return [c for p in self.partitions for c in p.cards]
        
        def get_main_deck(self) -> Partition:
            for p in self.partitions:
                if p.name == "Main":
                    return p
            return self.partitions[0] if self.partitions else Partition(name="Main", cards=[])
        
        def get_sideboard(self) -> Partition:
            for p in self.partitions:
                if p.name == "Sideboard":
                    return p
            return Partition(name="Sideboard", cards=[])
    
    class YugiohDeck(BaseModel):
        deck_id: str
        format: str
        archetype: Optional[str] = None
        partitions: list[Partition]
        
        def get_all_cards(self) -> list[CardDesc]:
            return [c for p in self.partitions for c in p.cards]
        
        def get_main_deck(self) -> Partition:
            for p in self.partitions:
                if "Main" in p.name:
                    return p
            return self.partitions[0] if self.partitions else Partition(name="Main Deck", cards=[])
    
    class PokemonDeck(BaseModel):
        deck_id: str
        format: str
        archetype: Optional[str] = None
        partitions: list[Partition]
        
        def get_all_cards(self) -> list[CardDesc]:
            return [c for p in self.partitions for c in p.cards]
        
        def get_main_deck(self) -> Partition:
            for p in self.partitions:
                if "Main" in p.name:
                    return p
            return self.partitions[0] if self.partitions else Partition(name="Main Deck", cards=[])
    
    class Collection(BaseModel):
        id: str
        partitions: list[Partition]
    
    BASIC_LANDS = {"Mountain", "Plains", "Island", "Swamp", "Forest"}

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
