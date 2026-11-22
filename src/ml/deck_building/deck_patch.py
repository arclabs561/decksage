"""
Deck patching system for applying modifications to decks.

DATA LINEAGE: Order 1 (depends on Order 1: Exported Decks)
- Input: Deck dictionary (Order 1)
- Output: Modified deck dictionary (Order 1)
- Can be regenerated from Order 1 data
"""

from collections import Counter
from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, Field

from .constants import MAGIC_BASIC_LANDS, POKEMON_BASIC_ENERGY


class DeckPatchOp(BaseModel):
    """A single deck patch operation."""

    op: Literal["add_card", "remove_card", "replace_card", "move_card"] = Field(
        ..., description="Operation type: add_card, remove_card, replace_card, move_card"
    )
    partition: str = Field(..., description="Partition name (e.g., 'Main', 'Sideboard')")
    card: str = Field(..., description="Card name")
    count: int = Field(1, gt=0, description="Number of cards")
    target_partition: str | None = Field(None, description="Target partition for move operations")
    replacement_card: str | None = Field(
        None, description="Replacement card for replace operations"
    )


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
    modified_deck = deepcopy(deck)
    partitions = modified_deck.setdefault("partitions", [])

    def get_partition(name: str) -> dict:
        for part in partitions:
            if part["name"] == name:
                return part
        part = {"name": name, "cards": []}
        partitions.append(part)
        return part

    def add_copies(cards: list[dict], record: dict, count: int) -> None:
        # Keep printing-specific metadata together when moving copies.
        for card in cards:
            if {k: v for k, v in card.items() if k != "count"} == record:
                card["count"] += count
                return
        cards.append({**record, "count": count})

    for op in patch.ops:
        source = next((p for p in partitions if p["name"] == op.partition), None)
        rows = [c for c in source["cards"] if c["name"] == op.card] if source else []
        if op.op == "add_card":
            if rows:
                rows[0]["count"] += op.count
            else:
                get_partition(op.partition)["cards"].append({"name": op.card, "count": op.count})
            continue

        if op.op in {"move_card", "replace_card"}:
            target = op.target_partition if op.op == "move_card" else op.replacement_card
            available = sum(c["count"] for c in rows)
            if not target or not target.strip():
                error = f"{op.op} requires a target for '{op.card}'"
            elif available < op.count:
                error = f"Requested {op.count} copies of '{op.card}' in {op.partition}, found {available}"
            else:
                error = None
            if error:
                return DeckPatchResult(deck=deck, is_valid=False, errors=[error])
            if (op.op == "move_card" and target == op.partition) or (
                op.op == "replace_card" and target == op.card
            ):
                continue

        remaining = op.count
        for row in rows:
            taken = min(row["count"], remaining)
            row["count"] -= taken
            if row["count"] == 0:
                source["cards"].remove(row)
            if op.op == "move_card":
                record = {k: v for k, v in row.items() if k != "count"}
                add_copies(get_partition(op.target_partition)["cards"], record, taken)
            elif op.op == "replace_card":
                add_copies(source["cards"], {"name": op.replacement_card}, taken)
            remaining -= taken
            if remaining == 0:
                break

    # Validate deck
    errors: list[str] = []
    warnings: list[str] = []

    def _norm(s: str | None) -> str:
        return (s or "").strip().lower()

    def _partition_size(*names: str) -> int:
        want = {_norm(n) for n in names if n and n.strip()}
        total = 0
        for p in modified_deck.get("partitions", []) or []:
            pname = _norm(p.get("name"))
            if pname in want:
                for card in p.get("cards", []) or []:
                    total += int(card.get("count", 0) or 0)
        return total

    def _total_size() -> int:
        total = 0
        for p in modified_deck.get("partitions", []) or []:
            for card in p.get("cards", []) or []:
                total += int(card.get("count", 0) or 0)
        return total

    # The same card may occur in several partitions or printing-specific rows.
    if game in {"magic", "pokemon", "yugioh"}:
        limit = 3 if game == "yugioh" else 4
        exempt = {"magic": MAGIC_BASIC_LANDS, "pokemon": POKEMON_BASIC_ENERGY}.get(game, set())
        counts: Counter[str] = Counter()
        for part in partitions:
            for card in part["cards"]:
                counts[card["name"]] += card["count"]
        for name, count in counts.items():
            if count > limit and name not in exempt:
                errors.append(f"Card '{name}' exceeds {limit}-copy limit (has {count})")

    if not lenient_size:
        # Check size constraints
        if game == "magic":
            main_deck_size = _partition_size("main", "mainboard")
            sideboard_size = _partition_size("sideboard", "side board")

            if main_deck_size < 60:
                errors.append(f"Main deck requires at least 60 cards (has {main_deck_size})")
            if sideboard_size > 15:
                errors.append(f"Sideboard cannot exceed 15 cards (has {sideboard_size})")

        elif game == "yugioh":
            main_deck_size = _partition_size("main deck", "main")
            extra_deck_size = _partition_size("extra deck", "extra")
            side_deck_size = _partition_size("side deck", "sideboard", "side")

            if main_deck_size < 40:
                errors.append(f"Main Deck requires at least 40 cards (has {main_deck_size})")
            elif main_deck_size > 60:
                errors.append(f"Main Deck cannot exceed 60 cards (has {main_deck_size})")
            if extra_deck_size > 15:
                errors.append(f"Extra Deck cannot exceed 15 cards (has {extra_deck_size})")
            if side_deck_size > 15:
                errors.append(f"Side Deck cannot exceed 15 cards (has {side_deck_size})")

        elif game == "pokemon":
            total = _total_size()
            if total != 60:
                errors.append(f"Pokémon deck requires exactly 60 total cards (has {total})")

    # Deterministic ban list / legality checking (optional, fail-closed if requested)
    if check_legality:
        try:
            from ..validation.validators.legality import check_deck_legality

            issues = check_deck_legality(modified_deck, game=game)
            if issues:
                errors.extend(issues)
        except Exception as e:
            errors.append(f"Legality check failed/unavailable: {e}")

    is_valid = len(errors) == 0

    return DeckPatchResult(
        deck=modified_deck,
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
    )
