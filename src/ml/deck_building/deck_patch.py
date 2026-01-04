"""
Deck patching system for applying modifications to decks.

DATA LINEAGE: Order 1 (depends on Order 1: Exported Decks)
- Input: Deck dictionary (Order 1)
- Output: Modified deck dictionary (Order 1)
- Can be regenerated from Order 1 data
"""

from pydantic import BaseModel, Field


class DeckPatchOp(BaseModel):
    """A single deck patch operation."""
    op: str = Field(..., description="Operation type: add_card, remove_card, replace_card, move_card")
    partition: str = Field(..., description="Partition name (e.g., 'Main', 'Sideboard')")
    card: str = Field(..., description="Card name")
    count: int = Field(1, description="Number of cards")
    target_partition: str | None = Field(None, description="Target partition for move operations")
    replacement_card: str | None = Field(None, description="Replacement card for replace operations")


class DeckPatch(BaseModel):
    """A collection of deck patch operations."""
    ops: list[DeckPatchOp] = Field(..., description="List of operations to apply")


class DeckPatchResult(BaseModel):
    """Result of applying a deck patch."""
    deck: dict = Field(..., description="Modified deck")
    is_valid: bool = Field(..., description="Whether the deck is valid after patching")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")


def apply_deck_patch(
    game: str,
    deck: dict,
    patch: DeckPatch,
    lenient_size: bool = True,
    check_legality: bool = False,
) -> DeckPatchResult:
    """
    Apply a deck patch to a deck.
    
    Args:
        game: Game type (magic, yugioh, pokemon)
        deck: Deck dictionary with partitions
        patch: Patch operations to apply
        lenient_size: If False, enforce size constraints
        check_legality: If True, check card legality
        
    Returns:
        DeckPatchResult with modified deck and validation status
    """
    # Create a deep copy of the deck
    import copy
    modified_deck = copy.deepcopy(deck)
    
    # Ensure partitions exist
    if "partitions" not in modified_deck:
        modified_deck["partitions"] = []
    
    # Apply each operation
    for op in patch.ops:
        if op.op == "add_card":
            # Find or create partition
            partition = None
            for p in modified_deck["partitions"]:
                if p["name"] == op.partition:
                    partition = p
                    break
            
            if partition is None:
                partition = {"name": op.partition, "cards": []}
                modified_deck["partitions"].append(partition)
            
            # Add card
            card_found = False
            for card in partition["cards"]:
                if card["name"] == op.card:
                    card["count"] += op.count
                    card_found = True
                    break
            
            if not card_found:
                partition["cards"].append({"name": op.card, "count": op.count})
        
        elif op.op == "remove_card":
            # Find partition
            for p in modified_deck["partitions"]:
                if p["name"] == op.partition:
                    # Remove card
                    for i, card in enumerate(p["cards"]):
                        if card["name"] == op.card:
                            card["count"] -= op.count
                            if card["count"] <= 0:
                                p["cards"].pop(i)
                            break
                    break
        
        elif op.op == "replace_card":
            # Find partition
            for p in modified_deck["partitions"]:
                if p["name"] == op.partition:
                    # Replace card
                    for card in p["cards"]:
                        if card["name"] == op.card:
                            card["name"] = op.replacement_card or op.card
                            break
                    break
        
        elif op.op == "move_card":
            # Find source partition
            source_partition = None
            for p in modified_deck["partitions"]:
                if p["name"] == op.partition:
                    source_partition = p
                    break
            
            # Find target partition
            target_partition = None
            for p in modified_deck["partitions"]:
                if p["name"] == op.target_partition:
                    target_partition = p
                    break
            
            if target_partition is None:
                target_partition = {"name": op.target_partition, "cards": []}
                modified_deck["partitions"].append(target_partition)
            
            # Move card
            if source_partition:
                for i, card in enumerate(source_partition["cards"]):
                    if card["name"] == op.card:
                        # Remove from source
                        card["count"] -= op.count
                        if card["count"] <= 0:
                            source_partition["cards"].pop(i)
                        
                        # Add to target
                        card_found = False
                        for target_card in target_partition["cards"]:
                            if target_card["name"] == op.card:
                                target_card["count"] += op.count
                                card_found = True
                                break
                        
                        if not card_found:
                            target_partition["cards"].append({"name": op.card, "count": op.count})
                        break
    
    # Validate deck
    errors = []
    warnings = []
    
    # Check copy limits (4-of rule in Magic, etc.)
    if game == "magic":
        # Check 4-of rule (except basic lands)
        BASIC_LANDS = {"Forest", "Island", "Mountain", "Plains", "Swamp", "Wastes", "Snow-Covered Forest", "Snow-Covered Island", "Snow-Covered Mountain", "Snow-Covered Plains", "Snow-Covered Swamp"}
        for p in modified_deck["partitions"]:
            for card in p["cards"]:
                if card["name"] not in BASIC_LANDS and card["count"] > 4:
                    errors.append(f"Card '{card['name']}' exceeds 4-copy limit (has {card['count']})")
    
    elif game == "yugioh":
        # Check 3-of rule
        for p in modified_deck["partitions"]:
            for card in p["cards"]:
                if card["count"] > 3:
                    errors.append(f"Card '{card['name']}' exceeds 3-copy limit (has {card['count']})")
    
    elif game == "pokemon":
        # Check 4-of rule (except basic Energy)
        BASIC_ENERGY = {"Grass Energy", "Fire Energy", "Water Energy", "Lightning Energy", "Psychic Energy", "Fighting Energy", "Darkness Energy", "Metal Energy", "Fairy Energy"}
        for p in modified_deck["partitions"]:
            for card in p["cards"]:
                if card["name"] not in BASIC_ENERGY and card["count"] > 4:
                    errors.append(f"Card '{card['name']}' exceeds 4-copy limit (has {card['count']})")
    
    if not lenient_size:
        # Check size constraints
        if game == "magic":
            main_deck_size = 0
            for p in modified_deck["partitions"]:
                if p["name"] == "Main":
                    for card in p["cards"]:
                        main_deck_size += card["count"]
            
            if main_deck_size < 60:
                errors.append(f"Main deck requires at least 60 cards (has {main_deck_size})")
        
        elif game == "yugioh":
            main_deck_size = 0
            for p in modified_deck["partitions"]:
                if p["name"] == "Main":
                    for card in p["cards"]:
                        main_deck_size += card["count"]
            
            if main_deck_size < 40:
                errors.append(f"Main deck requires at least 40 cards (has {main_deck_size})")
            elif main_deck_size > 60:
                errors.append(f"Main deck cannot exceed 60 cards (has {main_deck_size})")
        
        elif game == "pokemon":
            main_deck_size = 0
            for p in modified_deck["partitions"]:
                if p["name"] == "Main":
                    for card in p["cards"]:
                        main_deck_size += card["count"]
            
            if main_deck_size != 60:
                errors.append(f"Main deck requires exactly 60 cards (has {main_deck_size})")
    
    is_valid = len(errors) == 0
    
    return DeckPatchResult(
        deck=modified_deck,
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
    )

