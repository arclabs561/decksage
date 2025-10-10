#!/usr/bin/env python3
"""
Deck patch schema and atomic interpreter.

Provides a JSON-patch-esque action interface for deck editing across games
using the validated Pydantic models in validators.models. All ops are applied
transactionally: either the full set of operations results in a valid deck
state, or the changes are rejected with detailed errors.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Literal, Union, cast

from pydantic import BaseModel, Field, ValidationError
from pydantic.config import ConfigDict

from ..validation.validators.models import (
    CardDesc,
    MTGDeck,
    Partition,
    PokemonDeck,
    YugiohDeck,
)


# ----------------------------------------------------------------------------
# Patch operation models (discriminated union on op)
# ----------------------------------------------------------------------------


class AddCardOp(BaseModel):
    op: Literal["add_card"]
    partition: str
    card: str
    count: int = Field(1, ge=1)


class RemoveCardOp(BaseModel):
    op: Literal["remove_card"]
    partition: str
    card: str
    count: int = Field(1, ge=1)


class ReplaceCardOp(BaseModel):
    op: Literal["replace_card"]
    partition: str
    from_card: str = Field(..., alias="from")
    from_count: int = Field(1, ge=1, alias="from_count")
    to_card: str = Field(..., alias="to")
    to_count: int = Field(1, ge=1, alias="to_count")

    model_config = ConfigDict(populate_by_name=True)


class MoveCardOp(BaseModel):
    op: Literal["move_card"]
    from_partition: str
    to_partition: str
    card: str
    count: int = Field(1, ge=1)


class SetFormatOp(BaseModel):
    op: Literal["set_format"]
    value: str


class SetArchetypeOp(BaseModel):
    op: Literal["set_archetype"]
    value: str | None = None


PatchOp = Annotated[
    Union[AddCardOp, RemoveCardOp, ReplaceCardOp, MoveCardOp, SetFormatOp, SetArchetypeOp],
    Field(discriminator="op"),
]


class DeckPatch(BaseModel):
    ops: list[PatchOp]


class ErrorDetail(BaseModel):
    code: str
    message: str
    loc: list[str] | None = None


class DeckPatchResult(BaseModel):
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    deck: dict | None = None
    details: list[ErrorDetail] | None = None
    constraints_relaxed: list[str] | None = None


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _canonical_partition_name(game: Literal["magic", "yugioh", "pokemon"], name: str) -> str:
    n = name.strip().lower()
    if game == "magic":
        if n in {"main", "main deck", "md"}:
            return "Main"
        if n in {"side", "sb", "sideboard"}:
            return "Sideboard"
        return name
    if game == "yugioh":
        if n in {"main", "main deck", "md"}:
            return "Main Deck"
        if n in {"extra", "extra deck", "ed"}:
            return "Extra Deck"
        if n in {"side", "side deck", "sd", "sb"}:
            return "Side Deck"
        return name
    # pokemon
    if n in {"main", "main deck", "md"}:
        return "Main Deck"
    return name


def _find_partition_idx(data: dict, name: str) -> int | None:
    for i, p in enumerate(data.get("partitions", [])):
        if p.get("name") == name:
            return i
    return None


def _get_or_create_partition(data: dict, name: str) -> dict:
    idx = _find_partition_idx(data, name)
    if idx is not None:
        return data["partitions"][idx]
    p = {"name": name, "cards": []}
    data.setdefault("partitions", []).append(p)
    return p


def _add_card(partition: dict, card: str, count: int) -> None:
    for c in partition["cards"]:
        if c["name"] == card:
            c["count"] += count
            return
    partition["cards"].append({"name": card, "count": count})


def _remove_card(partition: dict, card: str, count: int) -> None:
    for i, c in enumerate(partition["cards"]):
        if c["name"] == card:
            c["count"] -= count
            if c["count"] <= 0:
                del partition["cards"][i]
            return


def _cleanup_empty_partitions(data: dict) -> None:
    parts = data.get("partitions", [])
    data["partitions"] = [p for p in parts if p.get("cards")]


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------


def _is_size_error(game: Literal["magic", "yugioh", "pokemon"], msg: str) -> bool:
    m = msg.lower()
    if game == "magic":
        return (
            "requires at least" in m and "main deck" in m
        ) or (
            "requires exactly" in m and "main deck" in m
        )
    if game == "yugioh":
        return "main deck must be 40-60 cards" in m
    if game == "pokemon":
        return "must be exactly 60 cards" in m
    return False


def _copy_limit_violations(game: Literal["magic", "yugioh", "pokemon"], data: dict) -> list[str]:
    # Count totals across all partitions
    counts: dict[str, int] = {}
    for p in data.get("partitions", []) or []:
        for c in p.get("cards", []) or []:
            name = str(c.get("name"))
            cnt = int(c.get("count", 0))
            counts[name] = counts.get(name, 0) + cnt

    errors: list[str] = []

    if game == "yugioh":
        for name, cnt in counts.items():
            if cnt > 3:
                errors.append(f"Yu-Gi-Oh! allows max 3 copies per card, {name} appears {cnt} times")
        return errors

    if game == "pokemon":
        BASIC_ENERGY = {
            "Grass Energy",
            "Fire Energy",
            "Water Energy",
            "Lightning Energy",
            "Psychic Energy",
            "Fighting Energy",
            "Darkness Energy",
            "Metal Energy",
            "Fairy Energy",
        }
        for name, cnt in counts.items():
            if name in BASIC_ENERGY:
                continue
            if cnt > 4:
                errors.append(f"Pokemon allows max 4 copies per card, {name} appears {cnt} times")
        return errors

    # magic
    BASIC_LANDS = {
        "Plains",
        "Island",
        "Swamp",
        "Mountain",
        "Forest",
        "Wastes",
        "Snow-Covered Plains",
        "Snow-Covered Island",
        "Snow-Covered Swamp",
        "Snow-Covered Mountain",
        "Snow-Covered Forest",
    }
    fmt = (data.get("format") or "").strip()
    singleton_formats = {"Commander", "cEDH", "Brawl", "Duel Commander"}
    limit = 1 if fmt in singleton_formats else 4
    for name, cnt in counts.items():
        if name in BASIC_LANDS:
            continue
        if cnt > limit:
            if limit == 1:
                errors.append(f"{fmt} is singleton format, but {name} appears {cnt} times")
            else:
                errors.append(f"{fmt} allows max {limit} copies per card, but {name} appears {cnt} times")
    return errors


def apply_deck_patch(
    game: Literal["magic", "yugioh", "pokemon"],
    deck: dict,
    patch: DeckPatch,
    *,
    lenient_size: bool = True,
    check_legality: bool = False,
) -> DeckPatchResult:
    """
    Apply all ops atomically; return validated deck or errors.
    """
    # Work on a deep copy of raw deck dict
    data = deepcopy(deck)

    # Normalize partition names up-front
    for p in data.get("partitions", []) or []:
        p["name"] = _canonical_partition_name(game, p.get("name", ""))

    try:
        for op in patch.ops:
            if isinstance(op, AddCardOp):
                part_name = _canonical_partition_name(game, op.partition)
                part = _get_or_create_partition(data, part_name)
                _add_card(part, op.card, op.count)

            elif isinstance(op, RemoveCardOp):
                part_name = _canonical_partition_name(game, op.partition)
                idx = _find_partition_idx(data, part_name)
                if idx is not None:
                    _remove_card(data["partitions"][idx], op.card, op.count)

            elif isinstance(op, ReplaceCardOp):
                part_name = _canonical_partition_name(game, op.partition)
                part = _get_or_create_partition(data, part_name)
                _remove_card(part, op.from_card, op.from_count)
                _add_card(part, op.to_card, op.to_count)

            elif isinstance(op, MoveCardOp):
                from_name = _canonical_partition_name(game, op.from_partition)
                to_name = _canonical_partition_name(game, op.to_partition)
                from_p = _get_or_create_partition(data, from_name)
                to_p = _get_or_create_partition(data, to_name)
                _remove_card(from_p, op.card, op.count)
                _add_card(to_p, op.card, op.count)

            elif isinstance(op, SetFormatOp):
                data["format"] = op.value

            elif isinstance(op, SetArchetypeOp):
                # Allow clearing archetype by setting None
                if op.value is None:
                    data.pop("archetype", None)
                else:
                    data["archetype"] = op.value

        # Remove any empty partitions before validation (partition must be non-empty)
        _cleanup_empty_partitions(data)

        # Validate by game and obtain typed deck
        deck_obj = None
        if game == "magic":
            deck_obj = MTGDeck.model_validate(data)
        elif game == "yugioh":
            deck_obj = YugiohDeck.model_validate(data)
        elif game == "pokemon":
            deck_obj = PokemonDeck.model_validate(data)
        else:
            return DeckPatchResult(is_valid=False, errors=[f"Unknown game: {game}"])

        # Optional legality checks (banlists, etc.)
        if check_legality and deck_obj is not None:
            try:
                from ..validation.validators.legality import check_deck_legality  # type: ignore

                legality_errors = check_deck_legality(deck_obj)  # type: ignore[arg-type]
                if legality_errors:
                    return DeckPatchResult(
                        is_valid=False,
                        errors=[f"(): {m}" for m in legality_errors],
                        warnings=[],
                        deck=None,
                        details=[ErrorDetail(code="legality", message=m) for m in legality_errors],
                    )
            except Exception:
                # If legality subsystem unavailable, proceed without failing
                pass

        return DeckPatchResult(is_valid=True, errors=[], warnings=[], deck=data)

    except ValidationError as e:
        # Allow partial decks by ignoring deck-size errors when lenient_size=True
        raw_msgs = [str(err.get("msg", "")) for err in e.errors()]
        if lenient_size:
            filtered = [m for m in raw_msgs if not _is_size_error(game, m)]
            if not filtered:
                # No non-size errors reported; ensure copy limits still enforced
                copy_errors = _copy_limit_violations(game, data)
                if copy_errors:
                    return DeckPatchResult(
                        is_valid=False,
                        errors=[f"(): {m}" for m in copy_errors],
                        warnings=["lenient_size"],
                        deck=None,
                        details=[ErrorDetail(code="copy_limit", message=m) for m in copy_errors],
                        constraints_relaxed=["size"],
                    )
                return DeckPatchResult(
                    is_valid=True,
                    errors=[],
                    warnings=["lenient_size"],
                    deck=data,
                    constraints_relaxed=["size"],
                )
            msgs = [f"(): {m}" for m in filtered]
            return DeckPatchResult(
                is_valid=False,
                errors=msgs,
                warnings=["lenient_size"],
                deck=None,
                details=[ErrorDetail(code="validation", message=m) for m in filtered],
                constraints_relaxed=["size"],
            )
        msgs = [f"(): {m}" for m in raw_msgs]
        return DeckPatchResult(
            is_valid=False,
            errors=msgs,
            warnings=[],
            deck=None,
            details=[ErrorDetail(code="validation", message=m) for m in raw_msgs],
        )
    except Exception as e:  # pragma: no cover - safety net
        return DeckPatchResult(is_valid=False, errors=[str(e)], warnings=[], deck=None)


__all__ = [
    "DeckPatch",
    "DeckPatchResult",
    "apply_deck_patch",
    "ErrorDetail",
    "AddCardOp",
    "RemoveCardOp",
    "ReplaceCardOp",
    "MoveCardOp",
    "SetFormatOp",
    "SetArchetypeOp",
]


