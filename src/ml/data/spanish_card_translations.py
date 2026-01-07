"""Spanish Magic card name translations.

Maps Spanish card names to English names for proper game detection.
"""

from __future__ import annotations

# Common Spanish Magic card name translations
# Based on official Spanish printings
SPANISH_TO_ENGLISH: dict[str, str] = {
    # Basic lands
    "bosque": "forest",
    "pantano": "swamp",
    "llanura": "plains",
    "montaña": "mountain",
    "isla": "island",
    # Common cards (add more as discovered)
    "huracán": "hurricane",
    "ornitóptero": "ornithopter",
    "fuerza impía": "unholy strength",
    "mina aullante": "howling mine",
    "muro de ramas": "wall of branches",
    "fuerza sagrada": "holy strength",
    "muro de lanzas": "wall of spears",
    "ángel de serra": "serra angel",
    "jinetes élficos": "elvish riders",
    "vampiro de sengir": "sengir vampire",
    "lobos de la tundra": "tundra wolves",
    "volumen de jayemdae": "jayemdae tome",
    "gigante de las colinas": "hill giant",
    "el potro": "the rack",
    "djinn mahamoti": "mahamoti djinn",
    "dragón shivano": "shivan dragon",
    "crecimiento gigante": "giant growth",
    "elemental de tierra": "earth elemental",
    "esqueletos esclavos": "skeleton crew",
    "araña gigante": "giant spider",
    "anular invocación": "counterspell",
    "ankh de mishra": "mishra's ankh",
    # Snow-covered lands
    "bosque nevado": "snow-covered forest",
    "pantano nevado": "snow-covered swamp",
    "llanura nevada": "snow-covered plains",
    "montaña nevada": "snow-covered mountain",
    "isla nevada": "snow-covered island",
    # Common Spanish card names found in data
    "humo": "smoke",
    "sino": "if not",
    "volar": "fly",
    "tio istvan": "uncle istvan",
    "drenar vida": "drain life",
    "barco pirata": "pirate ship",
    "bomba mental": "mind bomb",
    "ave mecánica": "mechanical bird",
    "bola de fuego": "fireball",
    "bola de rayos": "lightning bolt",
    "cavernícolas": "cave people",
    "contrahechizo": "counterspell",
    "druida de lei": "druid of lei",
    "barco fantasma": "ghost ship",
    "cavar túneles": "tunnel",
    "chacal de hurr": "hurr jackal",
    "cofre de maná": "mana vault",
    "copa de marfil": "ivory cup",
    "doncella alada": "winged maiden",
    "buitres de osai": "osai vultures",
    "forma gaseosa": "gaseous form",
    # Additional Spanish cards found in data
    "ave mecánica": "mechanical bird",
    "druida de lei": "druid of lei",
    "canto de sirena": "siren song",
    "choque de maná": "mana clash",
    "descarga astral": "astral projection",
    "efrit de junún": "junún efreet",
    "bestia mecánica": "mechanical beast",
    "caballero blanco": "white knight",
    "canto de titania": "titania's song",
    "coloso de sardia": "sardian colossus",
    "cría de dragón": "dragon whelp",
    "dragón de vapor": "steam dragon",
    "drenaje de poder": "power drain",
    "escasez de maná": "mana shortage",
    "esfera de madera": "wooden sphere",
    "espinas de maná": "mana thorns",
    "aves del paraíso": "birds of paradise",
    "baquete de tawnos": "tawnos's wand",
    "caballo de ébano": "ebony horse",
    "campana de kormus": "kormus bell",
    "derivación vital": "vital drain",
    "descarga de maná": "mana drain",
    "duendes voladores": "flying goblins",
    "caballero negro": "black knight",
    "barro primordial": "primordial ooze",
    "ciudad sumergida": "sunken city",
    "cetro disruptor": "disrupting scepter",
    "exatraer energia": "extract energy",
    # Common words that might be part of card names
    "sino": "if not",  # This might need context - could be part of a longer name
}


def translate_spanish_name(spanish_name: str) -> str | None:
    """
    Translate Spanish card name to English.
    
    Args:
        spanish_name: Spanish card name (case-insensitive)
    
    Returns:
        English name if translation found, original name otherwise
    """
    if not spanish_name:
        return None
    
    name_lower = spanish_name.lower().strip()
    translated = SPANISH_TO_ENGLISH.get(name_lower)
    
    # If no direct translation, try partial matches (for multi-word names)
    if not translated:
        # Try matching first word
        first_word = name_lower.split()[0] if name_lower.split() else ""
        if first_word in SPANISH_TO_ENGLISH:
            translated = SPANISH_TO_ENGLISH[first_word]
    
    return translated if translated else None


def is_spanish_name(card_name: str) -> bool:
    """Check if card name appears to be Spanish."""
    # Simple heuristic: contains Spanish-specific characters or common Spanish words
    spanish_chars = "áéíóúñü"
    spanish_words = ["de", "el", "la", "los", "las", "del"]
    
    name_lower = card_name.lower()
    
    # Check for Spanish characters
    if any(char in name_lower for char in spanish_chars):
        return True
    
    # Check for common Spanish words (but not too common English words)
    words = name_lower.split()
    if any(word in spanish_words and len(words) > 1 for word in words):
        return True
    
    return False


def normalize_split_card_name(name: str) -> str:
    """
    Normalize split card name spacing.
    
    Handles variations like:
    - "Fire // Ice"
    - "Fire//Ice"
    - "Fire //Ice"
    - "Fire// Ice"
    
    Returns normalized version with consistent spacing.
    """
    if "//" in name:
        # Normalize spacing around //
        parts = [p.strip() for p in name.split("//")]
        return " // ".join(parts)
    return name


