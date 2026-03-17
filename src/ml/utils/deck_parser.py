"""Parse common deck list text formats into DeckSage's internal partition format.

Supported formats:
  1. Arena/MTGO (section headers like "Deck", "Sideboard")
  2. Simple count ("4x Card Name", "4 Card Name", "Card Name x4")
  3. Plain list (one card per line, count=1)
  4. YGO (section headers like "Main Deck:", "Extra Deck:", "Side Deck:")
  5. Pokemon (section headers like "Pokemon - 12", "Trainer - 28", "Energy - 10")

No external dependencies.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Partition name mappings per game
# ---------------------------------------------------------------------------

_MAGIC_PARTITIONS: dict[str, str] = {
    "deck": "Main",
    "main": "Main",
    "main deck": "Main",
    "maindeck": "Main",
    "sideboard": "Sideboard",
    "side": "Sideboard",
    "sb": "Sideboard",
    "companion": "Sideboard",
}

_YGO_PARTITIONS: dict[str, str] = {
    "main": "Main Deck",
    "main deck": "Main Deck",
    "monster": "Main Deck",
    "monsters": "Main Deck",
    "spell": "Main Deck",
    "spells": "Main Deck",
    "trap": "Main Deck",
    "traps": "Main Deck",
    "extra": "Extra Deck",
    "extra deck": "Extra Deck",
    "side": "Side Deck",
    "side deck": "Side Deck",
    "sideboard": "Side Deck",
}

_POKEMON_PARTITIONS: dict[str, str] = {
    "pokemon": "Pokemon",
    "pokémon": "Pokemon",
    "trainer": "Trainer",
    "trainers": "Trainer",
    "energy": "Energy",
    "main": "Deck",
    "main deck": "Deck",
    "deck": "Deck",
}

_PARTITION_MAPS: dict[str, dict[str, str]] = {
    "magic": _MAGIC_PARTITIONS,
    "yugioh": _YGO_PARTITIONS,
    "pokemon": _POKEMON_PARTITIONS,
}

_DEFAULT_PARTITION: dict[str, str] = {
    "magic": "Main",
    "yugioh": "Main Deck",
    "pokemon": "Deck",
}


# ---------------------------------------------------------------------------
# Line-level regexes
# ---------------------------------------------------------------------------

# Section header: "Main Deck:" or "Sideboard" or "Pokemon - 12" or "Deck"
_SECTION_RE = re.compile(
    r"^(?P<name>[A-Za-zÉé][A-Za-zÉé /]+?)"  # section name
    r"(?:\s*[-:]\s*\d+)?$"  # optional " - 12" or ":" suffix
)

# Count prefix: "4 Card Name" or "4x Card Name"
_COUNT_PREFIX_RE = re.compile(r"^(?P<count>\d+)\s*[xX]?\s+(?P<name>.+)$")

# Count suffix: "Card Name x4" or "Card Name X4"
_COUNT_SUFFIX_RE = re.compile(r"^(?P<name>.+?)\s+[xX](?P<count>\d+)$")

# Pokemon set code + collector number suffix: "SV3 6", "SVI 189", "SVE 2", "CRZ 1"
# Matches 2-5 uppercase letters optionally followed by digits, then a space and number
_POKEMON_SET_RE = re.compile(r"\s+[A-Z]{2,5}\d{0,2}\s+\d+$")

# YGO card ID pattern (standalone numeric ID line like "12345678")
_YGO_ID_LINE_RE = re.compile(r"^\d{5,10}$")

# Comment or empty line
_SKIP_RE = re.compile(r"^\s*(?:#.*|//.*)$")


# ---------------------------------------------------------------------------
# Stripping helpers
# ---------------------------------------------------------------------------


def _strip_set_codes(name: str, game: str) -> str:
    """Remove set codes, collector numbers, and card IDs from card names."""
    if game == "pokemon":
        # Remove trailing set code + collector number (e.g. "SV3 6")
        name = _POKEMON_SET_RE.sub("", name)
    # Strip trailing whitespace that removal may leave
    return name.strip()


def _is_section_header(line: str, game: str) -> str | None:
    """Return the canonical partition name if *line* is a section header, else None."""
    pmap = _PARTITION_MAPS.get(game, _MAGIC_PARTITIONS)

    # Try exact match first (case-insensitive, strip colon/dash/count suffix)
    cleaned = re.sub(r"\s*[-:]\s*\d*\s*$", "", line).strip()
    key = cleaned.lower()
    if key in pmap:
        return pmap[key]

    # Also try the regex for less clean headers
    m = _SECTION_RE.match(line)
    if m:
        key2 = m.group("name").strip().lower()
        if key2 in pmap:
            return pmap[key2]

    return None


def _parse_card_line(line: str, game: str) -> tuple[str, int] | None:
    """Parse a single card line, returning (card_name, count) or None."""
    # Skip YGO standalone card ID lines
    if game == "yugioh" and _YGO_ID_LINE_RE.match(line.strip()):
        return None

    # Try count prefix: "4 Lightning Bolt" or "4x Lightning Bolt"
    m = _COUNT_PREFIX_RE.match(line)
    if m:
        count = int(m.group("count"))
        name = _strip_set_codes(m.group("name").strip(), game)
        if name:
            return name, count

    # Try count suffix: "Lightning Bolt x4"
    m = _COUNT_SUFFIX_RE.match(line)
    if m:
        count = int(m.group("count"))
        name = _strip_set_codes(m.group("name").strip(), game)
        if name:
            return name, count

    # Plain name (count = 1)
    name = _strip_set_codes(line.strip(), game)
    if name:
        return name, 1

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_deck_text(text: str, game: str = "magic") -> dict[str, Any]:
    """Parse a deck list from plain text into DeckSage partition format.

    Parameters
    ----------
    text:
        Raw deck list text (one card per line, optional section headers).
    game:
        Game identifier: "magic", "yugioh", or "pokemon".

    Returns
    -------
    dict with "partitions" key on success, or {"error": "..."} on failure.
    """
    game = game.strip().lower()
    if game not in _DEFAULT_PARTITION:
        return {"error": f"Unsupported game: {game!r}. Expected magic, yugioh, or pokemon."}

    if not text or not text.strip():
        return {"error": "Empty input."}

    lines = text.splitlines()
    default_part = _DEFAULT_PARTITION[game]
    current_partition = default_part

    # Accumulate cards per partition: {partition_name: {card_name: count}}
    partitions: dict[str, dict[str, int]] = {}
    card_count = 0

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        # Skip comments
        if _SKIP_RE.match(raw_line):
            continue

        # Check for section header
        section = _is_section_header(line, game)
        if section is not None:
            current_partition = section
            continue

        # Parse card line
        parsed = _parse_card_line(line, game)
        if parsed is None:
            continue

        card_name, count = parsed
        if current_partition not in partitions:
            partitions[current_partition] = {}
        bucket = partitions[current_partition]
        bucket[card_name] = bucket.get(card_name, 0) + count
        card_count += count

    if card_count == 0:
        return {"error": "No cards found in input."}

    # Build output
    result_partitions: list[dict[str, Any]] = []
    for part_name, cards in partitions.items():
        card_list = [{"name": name, "count": cnt} for name, cnt in cards.items()]
        result_partitions.append({"name": part_name, "cards": card_list})

    return {"partitions": result_partitions}
