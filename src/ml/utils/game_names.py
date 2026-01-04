"""
Game name normalization utilities.

Standardizes game names between different formats:
- Lowercase: "magic", "pokemon", "yugioh" (used in Python/deck JSONL)
- Uppercase: "MTG", "PKM", "YGO" (used in Go tools/pairs CSV)
"""

from typing import Literal

# Game name mappings
GAME_NAME_MAP = {
    # Lowercase -> Uppercase
    "magic": "MTG",
    "pokemon": "PKM",
    "yugioh": "YGO",
    "digimon": "DIG",
    "onepiece": "OPC",
    "riftbound": "RFT",
    # Uppercase -> Lowercase
    "MTG": "magic",
    "PKM": "pokemon",
    "YGO": "yugioh",
    "DIG": "digimon",
    "OPC": "onepiece",
    "RFT": "riftbound",
    # Aliases
    "mtg": "MTG",
    "pkm": "PKM",
    "ygo": "YGO",
    "yugioh!": "YGO",
    "yugioh": "YGO",
    "dig": "DIG",
    "digimon": "DIG",
    "opc": "OPC",
    "opcg": "OPC",
    "onepiece": "OPC",
    "one piece": "OPC",
    "riftbound": "RFT",
    "rift": "RFT",
}

# Canonical formats
LOWERCASE_GAMES = {"magic", "pokemon", "yugioh", "digimon", "onepiece", "riftbound"}
UPPERCASE_GAMES = {"MTG", "PKM", "YGO", "DIG", "OPC", "RFT"}


def normalize_game_name(
    name: str,
    to_format: Literal["lowercase", "uppercase"] = "lowercase",
) -> str:
    """
    Normalize game name to specified format.
    
    Args:
        name: Game name in any format
        to_format: Target format ("lowercase" or "uppercase")
        
    Returns:
        Normalized game name
        
    Examples:
        >>> normalize_game_name("MTG", "lowercase")
        'magic'
        >>> normalize_game_name("magic", "uppercase")
        'MTG'
        >>> normalize_game_name("pokemon", "uppercase")
        'PKM'
    """
    if not name:
        return ""
    
    name_lower = name.lower().strip()
    
    # Direct mapping
    if name_lower in GAME_NAME_MAP:
        mapped = GAME_NAME_MAP[name_lower]
    elif name.upper() in GAME_NAME_MAP:
        mapped = GAME_NAME_MAP[name.upper()]
    else:
        # Try fuzzy matching
        if "magic" in name_lower or "mtg" in name_lower:
            mapped = "MTG" if to_format == "uppercase" else "magic"
        elif "pokemon" in name_lower or "pkm" in name_lower:
            mapped = "PKM" if to_format == "uppercase" else "pokemon"
        elif "yugioh" in name_lower or "ygo" in name_lower:
            mapped = "YGO" if to_format == "uppercase" else "yugioh"
        elif "digimon" in name_lower or "dig" in name_lower:
            mapped = "DIG" if to_format == "uppercase" else "digimon"
        elif "onepiece" in name_lower or "opcg" in name_lower or "opc" in name_lower or "one piece" in name_lower:
            mapped = "OPC" if to_format == "uppercase" else "onepiece"
        elif "riftbound" in name_lower or "rift" in name_lower or "rft" in name_lower:
            mapped = "RFT" if to_format == "uppercase" else "riftbound"
        else:
            # Unknown - return as-is
            return name
    
    # Convert to target format
    if to_format == "lowercase":
        return GAME_NAME_MAP.get(mapped, mapped.lower())
    else:  # uppercase
        return GAME_NAME_MAP.get(mapped, mapped.upper())


def is_valid_game_name(name: str) -> bool:
    """Check if name is a valid game name."""
    name_lower = name.lower().strip()
    return name_lower in LOWERCASE_GAMES or name.upper() in UPPERCASE_GAMES


def get_all_game_names(format: Literal["lowercase", "uppercase"] = "lowercase") -> list[str]:
    """Get all valid game names in specified format."""
    if format == "lowercase":
        return list(LOWERCASE_GAMES)
    else:
        return list(UPPERCASE_GAMES)

