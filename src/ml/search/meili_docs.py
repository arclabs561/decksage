"""Build Meilisearch documents from card metadata.

One builder shared by the API's first-boot auto-index and the reindex script.
Before this, only name/text/type/keywords plus four filter fields reached
Meilisearch, so power, toughness, archetype, hp, atk/def, effect types and the
other attributes the catalogs carry were invisible to filters and agents.
"""

from __future__ import annotations

from typing import Any


# Attributes worth storing: either filter/sort fields or fields an agent
# reads from a hit. Keep the list explicit; dumping every column bloats the
# index with enrichment-only text.
CARD_FIELDS = (
    "colors",
    "cmc",
    "rarity",
    "set_name",
    "power",
    "toughness",
    "mana_cost",
    "hp",
    "retreat_cost",
    "atk",
    "def_stat",
    "level_rank_link",
    "supertype",
    "subtypes",
    "archetype",
    "attribute",
    "race",
    "card_category",
    "monster_type",
    "effect_types",
    "regulation_mark",
    "weakness_type",
    "resistance_type",
    "set_release_date",
)


def plain(value: Any) -> Any:
    """Convert numpy scalars/NaN/lists into JSON-safe Meilisearch values."""
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if item is not None]
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return value


def card_document(name: str, meta: dict[str, Any], game: str, id_value: str) -> dict[str, Any]:
    document: dict[str, Any] = {
        "id": id_value,
        "name": name,
        "game": game,
        "text": str(meta.get("oracle_text") or meta.get("text") or "")[:2000],
        "type_line": str(meta.get("type_line") or meta.get("type") or ""),
        "keywords": str(meta.get("keywords") or ""),
    }
    for field in CARD_FIELDS:
        value = plain(meta.get(field))
        if value is not None:
            document[field] = value
    return document
