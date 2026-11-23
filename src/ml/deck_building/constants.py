"""Shared constants for deck building modules."""

POKEMON_BASIC_ENERGY: set[str] = {
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

MAGIC_BASIC_LANDS: set[str] = {
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

# Printed deck-construction exceptions. Basic lands use their separate rule.
MAGIC_COPY_LIMIT_OVERRIDES: dict[str, int | None] = {
    "Cid, Timeless Artificer": None,
    "Dragon's Approach": None,
    "Hare Apparent": None,
    "Nazgûl": 9,
    "Once More with Feeling": 1,
    "Persistent Petitioners": None,
    "Rat Colony": None,
    "Relentless Rats": None,
    "Seven Dwarves": 7,
    "Shadowborn Apostle": None,
    "Slime Against Humanity": None,
    "Sphinx's Approach": None,
    "Tempest Hawk": None,
    "Templar Knight": None,
}
