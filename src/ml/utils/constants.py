"""Shared constants for multi-game experiments."""

# Game-specific filter sets for common cards that dominate co-occurrence
# These typically add little signal (lands, energy cards, etc.)

GAME_FILTERS = {
    "magic": {
        "basic_lands": {"Plains", "Island", "Swamp", "Mountain", "Forest"},
        "common_lands": {
            "Plains",
            "Island",
            "Swamp",
            "Mountain",
            "Forest",
            "Snow-Covered Plains",
            "Snow-Covered Island",
            "Snow-Covered Swamp",
            "Snow-Covered Mountain",
            "Snow-Covered Forest",
            "Wastes",
        },
        "staples": {
            "Command Tower",
            "Evolving Wilds",
            "Terramorphic Expanse",
            "Sol Ring",
            "Arcane Signet",  # Universal colorless staples
        },
    },
    "yugioh": {
        # YGO doesn't have lands, but has common staples
        "staples": set(),  # Could add generic staples if needed
    },
    "pokemon": {
        "basic_energy": {
            "Grass Energy",
            "Fire Energy",
            "Water Energy",
            "Lightning Energy",
            "Psychic Energy",
            "Fighting Energy",
            "Darkness Energy",
            "Metal Energy",
            "Fairy Energy",
        },
        "special_energy": set(),  # Could populate with common ones
    },
}


def get_filter_set(game: str, level: str = "basic") -> set:
    """
    Get filter set for a game.

    Args:
        game: 'magic', 'yugioh', or 'pokemon'
        level: 'basic', 'common', 'staples', etc. (game-specific)

    Returns:
        Set of card names to filter
    """
    game_lower = game.lower()

    if game_lower == "magic":
        if level == "basic":
            return GAME_FILTERS["magic"]["basic_lands"]
        elif level == "common":
            return GAME_FILTERS["magic"]["common_lands"]
        elif level == "all":
            return GAME_FILTERS["magic"]["common_lands"] | GAME_FILTERS["magic"]["staples"]

    elif game_lower == "pokemon":
        if level in ("basic", "energy"):
            return GAME_FILTERS["pokemon"]["basic_energy"]
        elif level == "all":
            return (
                GAME_FILTERS["pokemon"]["basic_energy"] | GAME_FILTERS["pokemon"]["special_energy"]
            )

    elif game_lower == "yugioh":
        return GAME_FILTERS["yugioh"]["staples"]

    return set()


# Relevance weights for test set evaluation (game-agnostic)
RELEVANCE_WEIGHTS = {
    "highly_relevant": 1.0,
    "relevant": 0.75,
    "somewhat_relevant": 0.5,
    "marginally_relevant": 0.25,
    "irrelevant": 0.0,
}
