#!/usr/bin/env python3
"""
Tests for card enrichment process.

Tests:
- Scryfall API integration
- Field extraction
- Rate limiting
- Error handling
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

try:
    import pandas as pd
    import requests
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False
    pytestmark = pytest.mark.skip("Missing dependencies")


def test_extract_attributes_from_scryfall():
    """Test extracting attributes from Scryfall card data."""
    from ml.scripts.enrich_attributes_with_scryfall_optimized import extract_attributes_from_scryfall
    
    # Sample Scryfall card data
    card_data = {
        "name": "Lightning Bolt",
        "type_line": "Instant",
        "mana_cost": "{R}",
        "cmc": 1.0,
        "colors": ["R"],
        "rarity": "common",
        "power": None,
        "toughness": None,
        "set": "lea",
        "set_name": "Limited Edition Alpha",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        "keywords": ["fast"],
    }
    
    attrs = extract_attributes_from_scryfall(card_data)
    
    assert attrs["type"] == "Instant"
    assert attrs["mana_cost"] == "{R}"
    assert attrs["cmc"] == 1.0
    assert attrs["colors"] == "R"
    assert attrs["rarity"] == "common"
    assert attrs["set"] == "lea"
    assert attrs["set_name"] == "Limited Edition Alpha"
    assert attrs["oracle_text"] == "Lightning Bolt deals 3 damage to any target."
    assert attrs["keywords"] == "fast"


def test_extract_attributes_creature():
    """Test extracting attributes for a creature card."""
    from ml.scripts.enrich_attributes_with_scryfall_optimized import extract_attributes_from_scryfall
    
    card_data = {
        "name": "Grizzly Bears",
        "type_line": "Creature — Bear",
        "mana_cost": "{1}{G}",
        "cmc": 2.0,
        "colors": ["G"],
        "rarity": "common",
        "power": "2",
        "toughness": "2",
        "set": "lea",
        "set_name": "Limited Edition Alpha",
        "oracle_text": "",
        "keywords": [],
    }
    
    attrs = extract_attributes_from_scryfall(card_data)
    
    assert attrs["power"] == "2"
    assert attrs["toughness"] == "2"
    assert attrs["type"] == "Creature — Bear"


def test_name_variants():
    """Test name variant generation for retry."""
    from ml.scripts.retry_failed_enrichments import get_name_variants
    
    # Split card
    variants = get_name_variants("Lightning Bolt // Shock")
    assert "Lightning Bolt" in variants
    assert "Shock" in variants
    
    # Card with parentheses
    variants = get_name_variants("Card Name (Set Name)")
    assert "Card Name" in variants
    
    # Unicode
    variants = get_name_variants("Forêt")
    assert any("Foret" in v or "Forêt" in v for v in variants)


def test_normalize_card_name():
    """Test card name normalization."""
    from ml.scripts.retry_failed_enrichments import normalize_card_name
    
    assert normalize_card_name("  Lightning  Bolt  ") == "Lightning Bolt"
    assert normalize_card_name("Lightning-Bolt") == "Lightning-Bolt"
    assert normalize_card_name("Lightning.Bolt") == "LightningBolt"


@pytest.mark.skip("Requires API access")
def test_get_card_from_scryfall():
    """Test fetching card from Scryfall API."""
    from ml.scripts.enrich_attributes_with_scryfall_optimized import get_card_from_scryfall
    
    card_data, delay = get_card_from_scryfall("Lightning Bolt")
    
    assert card_data is not None
    assert card_data["name"] == "Lightning Bolt"
    assert delay >= 0.05


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

