"""
Deck patching system for applying modifications to decks.

DATA LINEAGE: Order 1 (depends on Order 1: Exported Decks)
- Input: Deck dictionary (Order 1)
- Output: Modified deck dictionary (Order 1)
- Can be regenerated from Order 1 data
"""

from copy import deepcopy
from typing import Literal

from pydantic import BaseModel, Field

from ..validation.deck_rules import canonical_name, construction_errors, partition_key


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

    def rejected(errors: list[str]) -> DeckPatchResult:
        return DeckPatchResult(deck=deepcopy(deck), is_valid=False, errors=errors)

    def named(value: object) -> bool:
        return isinstance(value, str) and bool(canonical_name(value))

    if deck.get("format") is not None and not isinstance(deck["format"], str):
        return rejected(["Expected a format name"])
    parts = deck.get("partitions", [])
    if not isinstance(parts, list):
        return rejected(["Expected a list of partitions"])
    for part in parts:
        if (
            not isinstance(part, dict)
            or not named(part.get("name"))
            or not isinstance(part.get("cards"), list)
        ):
            return rejected(["Expected a named partition with a list of cards"])
        for row in part["cards"]:
            if (
                not isinstance(row, dict)
                or not named(row.get("name"))
                or type(row.get("count")) is not int
                or row["count"] <= 0
            ):
                return rejected(["Expected a named card with a positive integer count"])

    modified_deck = deepcopy(deck)
    partitions = modified_deck.setdefault("partitions", [])

    def get_partition(name: str) -> dict:
        for part in partitions:
            if partition_key(part["name"]) == partition_key(name):
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
        if not named(op.partition) or not named(op.card):
            return rejected(["Expected a partition and card name"])
        rows = [
            (p, c)
            for p in partitions
            if partition_key(p["name"]) == partition_key(op.partition)
            for c in p["cards"]
            if canonical_name(c["name"]) == canonical_name(op.card)
        ]
        if op.op == "add_card":
            if rows:
                rows[0][1]["count"] += op.count
            else:
                get_partition(op.partition)["cards"].append({"name": op.card, "count": op.count})
            continue

        if op.op in {"move_card", "replace_card"}:
            target = op.target_partition if op.op == "move_card" else op.replacement_card
            available = sum(c["count"] for _, c in rows)
            if not target or not target.strip():
                error = f"{op.op} requires a target for '{op.card}'"
            elif available < op.count:
                error = f"Requested {op.count} copies of '{op.card}' in {op.partition}, found {available}"
            else:
                error = None
            if error:
                return rejected([error])
            if (op.op == "move_card" and partition_key(target) == partition_key(op.partition)) or (
                op.op == "replace_card" and canonical_name(target) == canonical_name(op.card)
            ):
                continue

        remaining = op.count
        for source, row in rows:
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

    errors = construction_errors(
        game,
        modified_deck.get("format"),
        ((p["name"], ((c["name"], c["count"]) for c in p["cards"])) for p in partitions),
        check_size=not lenient_size,
    )

    # Deterministic ban list / legality checking (optional, fail-closed if requested)
    if check_legality:
        try:
            from ..validation.validators.legality import check_deck_legality

            issues = check_deck_legality(modified_deck, game=game)
            if issues:
                errors.extend(issues)
        except Exception as e:
            errors.append(f"Legality check failed/unavailable: {e}")

    if errors:
        return rejected(errors)
    return DeckPatchResult(deck=modified_deck, is_valid=True)
