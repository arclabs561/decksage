"""Construction rules shared by import, editing, and incremental completion."""

from collections import Counter
from collections.abc import Iterable
from unicodedata import normalize

from ..deck_building.constants import MAGIC_BASIC_LANDS, POKEMON_BASIC_ENERGY


_MAIN = {"main", "mainboard", "main deck", "deck"}
_SIDE = {"sideboard", "side board", "side deck", "side"}
_EXTRA = {"extra deck", "extra"}
_COMMANDER = {"commander", "cedh", "duel commander"}
_SINGLETON = _COMMANDER | {"brawl"}


def canonical_name(name: str) -> str:
    return normalize("NFKC", name).strip()


def partition_key(name: str) -> str:
    key = canonical_name(name).lower()
    if key in _MAIN:
        return "main"
    if key in _SIDE:
        return "side"
    if key in _EXTRA:
        return "extra"
    return key


def copy_limit(game: str, fmt: str | None, card: str) -> int | None:
    """None means that this card has no construction copy limit."""
    if game == "magic":
        if canonical_name(card) in MAGIC_BASIC_LANDS:
            return None
        return 1 if canonical_name(fmt or "").lower() in _SINGLETON else 4
    if game == "pokemon":
        return None if canonical_name(card) in POKEMON_BASIC_ENERGY else 4
    if game == "yugioh":
        return 3
    raise ValueError(f"Unsupported game: {game}")


def construction_errors(
    game: str,
    fmt: str | None,
    partitions: Iterable[tuple[str, Iterable[tuple[str, int]]]],
    *,
    check_size: bool = True,
) -> list[str]:
    """Check counted rows without changing the caller's deck representation."""
    if game not in {"magic", "pokemon", "yugioh"}:
        return [f"Unsupported game: {game}"]
    counts: Counter[str] = Counter()
    sizes: Counter[str] = Counter()
    for partition, cards in partitions:
        name = partition_key(partition)
        sizes.setdefault(name, 0)
        for card, count in cards:
            counts[canonical_name(card)] += count
            sizes[name] += count

    errors = []
    if check_size:
        main = sizes["main"]
        if sizes and "main" not in sizes:
            # Historical exports sometimes use a custom name for their main partition.
            first = next(iter(sizes))
            if first not in {"side", "extra"}:
                main = sizes[first]
        side = sizes["side"]
        extra = sizes["extra"]
        format_name = canonical_name(fmt or "")
        if game == "magic":
            singleton = format_name.lower() in _SINGLETON
            if singleton:
                size = 60 if format_name.lower() == "brawl" else 100
                if main != size:
                    errors.append(
                        f"{format_name} requires exactly {size} cards in Main (has {main})"
                    )
                if side:
                    errors.append(f"{format_name} expects no Sideboard (has {side})")
            else:
                if main < 60:
                    errors.append(f"Main deck requires at least 60 cards (has {main})")
                if side > 15:
                    errors.append(f"Sideboard cannot exceed 15 cards (has {side})")
        elif game == "yugioh":
            if not 40 <= main <= 60:
                errors.append(f"Yu-Gi-Oh! main deck must be 40-60 cards (has {main})")
            if extra > 15:
                errors.append(f"Extra Deck cannot exceed 15 cards (has {extra})")
            if side > 15:
                errors.append(f"Side Deck cannot exceed 15 cards (has {side})")
        elif (total := sum(sizes.values())) != 60:
            errors.append(f"Pokémon deck requires exactly 60 total cards (has {total})")

    for card, count in counts.items():
        limit = copy_limit(game, fmt, card)
        if limit is not None and count > limit:
            errors.append(f"Card '{card}' exceeds {limit}-copy limit (has {count})")
    return errors
