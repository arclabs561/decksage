"""Multilingual card name translations.

Supports translation from multiple languages to English for proper game detection.
Currently supports: Spanish, French, German, Italian, Portuguese, Japanese, Chinese, Korean, Russian.
"""

from __future__ import annotations

import re
from typing import Literal

# Language detection patterns
JAPANESE_PATTERN = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')
CHINESE_PATTERN = re.compile(r'[\u4E00-\u9FFF]')
KOREAN_PATTERN = re.compile(r'[\uAC00-\uD7AF]')
FRENCH_PATTERN = re.compile(r'[àâäéèêëïîôùûüÿçÀÂÄÉÈÊËÏÎÔÙÛÜŸÇ]')
GERMAN_PATTERN = re.compile(r'[äöüßÄÖÜ]')
ITALIAN_PATTERN = re.compile(r'[àèéìíîòóùúÀÈÉÌÍÎÒÓÙÚ]')
PORTUGUESE_PATTERN = re.compile(r'[àáâãéêíóôõúÀÁÂÃÉÊÍÓÔÕÚ]')
RUSSIAN_PATTERN = re.compile(r'[А-Яа-яЁё]')
SPANISH_PATTERN = re.compile(r'[áéíóúñüÁÉÍÓÚÑÜ]')

# Scryfall language codes
SCRYFALL_LANG_CODES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ja": "Japanese",
    "zhs": "Simplified Chinese",
    "zht": "Traditional Chinese",
    "ko": "Korean",
    "ru": "Russian",
}

# Common translations (will be expanded via API research)
# Spanish translations (from existing file)
from .spanish_card_translations import SPANISH_TO_ENGLISH

# French translations (common Magic cards)
FRENCH_TO_ENGLISH: dict[str, str] = {
    "forêt": "forest",
    "marais": "swamp",
    "plaine": "plains",
    "montagne": "mountain",
    "île": "island",
    "géant des collines": "hill giant",
    "ange de serra": "serra angel",
    "dragon shivan": "shivan dragon",
    "croissance géante": "giant growth",
    "contresort": "counterspell",
    "geyser cérébral": "brain geyser",
    "vivacité": "vitality",
    "rétroaction": "feedback",
    "mur d'épées": "wall of swords",
    "licorne nacrée": "pearl unicorn",
    "prisme céleste": "celestial prism",
    "pégase de mesa": "mesa pegasus",
    # Additional French cards found in data
    "géant": "giant",
    "cérébral": "cerebral",
    "épées": "swords",
    "nacrée": "pearl",
    "céleste": "celestial",
    # Additional French cards from data
    "geyser cérébral": "brain geyser",
    "vivacité": "vitality",
    "rétroaction": "feedback",
    "mur d'épées": "wall of swords",
    "licorne nacrée": "pearl unicorn",
    "prisme céleste": "celestial prism",
    "pégase de mesa": "mesa pegasus",
    "géant de pierre": "stone giant",
    "géant des collines": "hill giant",
    "convulsion cérébrale": "brainstorm",
    "araignée géante": "giant spider",
    "force de géant": "giant strength",
    "tortue marine géante": "giant sea turtle",
    "bombe cérébrale": "mind bomb",
}

# German translations (common Magic cards)
GERMAN_TO_ENGLISH: dict[str, str] = {
    "wald": "forest",
    "sumpf": "swamp",
    "ebene": "plains",
    "berg": "mountain",
    "insel": "island",
    "riese der hügel": "hill giant",
    "serra engel": "serra angel",
    "shivan drache": "shivan dragon",
    "riesenwachstum": "giant growth",
    "gegenspruch": "counterspell",
}

# Italian translations (common Magic cards)
ITALIAN_TO_ENGLISH: dict[str, str] = {
    "foresta": "forest",
    "palude": "swamp",
    "pianura": "plains",
    "montagna": "mountain",
    "isola": "island",
    "gigante delle colline": "hill giant",
    "angelo di serra": "serra angel",
    "drago shivan": "shivan dragon",
    "crescita gigante": "giant growth",
    "contrastare": "counterspell",
    # Additional Italian/Spanish cards found in data
    "artillería": "artillery",
    "mortívoro": "death eater",
    "orca": "orca",
}

# Portuguese translations (common Magic cards)
PORTUGUESE_TO_ENGLISH: dict[str, str] = {
    "floresta": "forest",
    "pântano": "swamp",
    "planície": "plains",
    "montanha": "mountain",
    "ilha": "island",
    "gigante das colinas": "hill giant",
    "anjo de serra": "serra angel",
    "dragão shivan": "shivan dragon",
    "crescimento gigante": "giant growth",
    "contramágica": "counterspell",
    "parálisis": "paralysis",
    "relámpago": "lightning",
    "lazo arcáico": "arcane binding",
}

# Yu-Gi-Oh specific translations
YUGIOH_SPANISH_TO_ENGLISH: dict[str, str] = {
    "jinetes élficos": "elven riders",
    "señuelo": "decoy",
    "telaraña": "cobweb",
    "gul carroñero": "scavenging ghoul",
}

YUGIOH_FRENCH_TO_ENGLISH: dict[str, str] = {
    "jinetes élficos": "elven riders",
    "flujo energético": "energy stream",
    "tétravo": "tetravo",
    "sombra gélida": "frozen shadow",
    "àspid de nafs": "nafs asp",
    "gigante pétreo": "stone giant",
}

YUGIOH_ITALIAN_TO_ENGLISH: dict[str, str] = {
    "vínculo espiritual": "spiritual binding",
    "immolcaión": "immolation",
    "inundación": "inundation",
    "trisquelión": "triskelion",
    "sierpe dragón": "dragon serpent",
    "tierra vírgen": "virgin land",
    "horror cósmico": "cosmic horror",
}

YUGIOH_PORTUGUESE_TO_ENGLISH: dict[str, str] = {
    "parálisis": "paralysis",
    "relámpago": "lightning",
    "lazo arcáico": "arcane binding",
    "fulgor de maná": "mana flash",
}


def detect_language(card_name: str) -> str | None:
    """
    Detect the language of a card name.
    
    Returns:
        Language code ("es", "fr", "de", "it", "pt", "ja", "zh", "ko", "ru") or None
    """
    if not card_name:
        return None
    
    if JAPANESE_PATTERN.search(card_name):
        return "ja"
    elif CHINESE_PATTERN.search(card_name):
        return "zh"
    elif KOREAN_PATTERN.search(card_name):
        return "ko"
    elif RUSSIAN_PATTERN.search(card_name):
        return "ru"
    elif FRENCH_PATTERN.search(card_name):
        return "fr"
    elif GERMAN_PATTERN.search(card_name):
        return "de"
    elif ITALIAN_PATTERN.search(card_name):
        return "it"
    elif PORTUGUESE_PATTERN.search(card_name):
        return "pt"
    elif SPANISH_PATTERN.search(card_name):
        return "es"
    
    return None


def translate_card_name(
    card_name: str, 
    from_lang: str | None = None,
    use_api: bool = False
) -> str | None:
    """
    Translate card name from any language to English.
    
    Uses multiple strategies:
    1. Exact dictionary match
    2. Partial word matching (for multi-word names)
    3. Case-insensitive matching
    
    Args:
        card_name: Card name in any language
        from_lang: Language code (auto-detected if None)
        use_api: If True, use Scryfall API for translation (not implemented here)
        
    Returns:
        English name if translation found, None otherwise
    """
    if not card_name:
        return None
    
    # Auto-detect language if not provided
    if from_lang is None:
        from_lang = detect_language(card_name)
    
    if from_lang is None:
        return None
    
    name_lower = card_name.lower().strip()
    
    # Try dictionary translation first (exact match)
    translation = None
    dictionary = None
    if from_lang == "es":
        dictionary = SPANISH_TO_ENGLISH
    elif from_lang == "fr":
        dictionary = FRENCH_TO_ENGLISH
    elif from_lang == "de":
        dictionary = GERMAN_TO_ENGLISH
    elif from_lang == "it":
        dictionary = ITALIAN_TO_ENGLISH
    elif from_lang == "pt":
        dictionary = PORTUGUESE_TO_ENGLISH
    
    if dictionary:
        # Try exact match
        translation = dictionary.get(name_lower)
        
        # Try partial matches for multi-word names
        if not translation:
            words = name_lower.split()
            if len(words) > 1:
                # Try matching first word
                if words[0] in dictionary:
                    translation = dictionary[words[0]]
                # Try matching last word
                elif words[-1] in dictionary:
                    translation = dictionary[words[-1]]
                # Try matching longest word
                else:
                    longest_word = max(words, key=len)
                    if longest_word in dictionary:
                        translation = dictionary[longest_word]
        
        # Try case variations
        if not translation:
            for key, value in dictionary.items():
                if key in name_lower or name_lower in key:
                    # Check if it's a reasonable match (not too short)
                    if len(key) >= 3 and len(value) >= 3:
                        translation = value
                        break
    
    # Japanese, Chinese, Korean, Russian require API lookup
    # (handled separately in fix_multilingual_cards_with_api.py)
    
    return translation


def get_scryfall_lang_code(language: str) -> str | None:
    """Get Scryfall language code for a language."""
    lang_map = {
        "es": "es",
        "fr": "fr",
        "de": "de",
        "it": "it",
        "pt": "pt",
        "ja": "ja",
        "zh": "zhs",  # Default to simplified
        "ko": "ko",
        "ru": "ru",
    }
    return lang_map.get(language.lower())


def translate_yugioh_card_name(card_name: str) -> str | None:
    """
    Translate a Yu-Gi-Oh card name to English using dictionary lookups.
    
    Args:
        card_name: Card name in source language
        
    Returns:
        English card name if found, None otherwise
    """
    if not card_name:
        return None
    
    card_name_lower = card_name.lower().strip()
    
    # Check Spanish
    for spanish, english in YUGIOH_SPANISH_TO_ENGLISH.items():
        if spanish.lower() == card_name_lower or card_name_lower in spanish.lower():
            return english
    
    # Check French
    for french, english in YUGIOH_FRENCH_TO_ENGLISH.items():
        if french.lower() == card_name_lower or card_name_lower in french.lower():
            return english
    
    # Check Italian
    for italian, english in YUGIOH_ITALIAN_TO_ENGLISH.items():
        if italian.lower() == card_name_lower or card_name_lower in italian.lower():
            return english
    
    # Check Portuguese
    for portuguese, english in YUGIOH_PORTUGUESE_TO_ENGLISH.items():
        if portuguese.lower() == card_name_lower or card_name_lower in portuguese.lower():
            return english
    
    return None


def is_multilingual_name(card_name: str) -> bool:
    """Check if card name appears to be in a non-English language."""
    return detect_language(card_name) is not None

