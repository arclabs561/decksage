"""Reprint-family construction: normalization and grouping rules."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "reprint_families", ROOT / "scripts/data/reprint_families.py"
)
reprints = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(reprints)


def card(name, text, type_line="Instant", cost="{1}{W}", power=None, toughness=None):
    out = {
        "object": "card",
        "name": name,
        "oracle_text": text,
        "type_line": type_line,
        "mana_cost": cost,
    }
    if power is not None:
        out["power"] = power
        out["toughness"] = toughness
    return out


def test_name_is_normalized_away():
    a = card("Shock", "Shock deals 2 damage to any target.")
    b = card("Zap", "Zap deals 2 damage to any target.")
    assert reprints.family_key(a)[0] == reprints.family_key(b)[0]


def test_reminder_text_is_stripped():
    a = card("Shock", "Deal 2 damage. (This is reminder text.)")
    b = card("Zap", "Deal 2 damage.")
    assert reprints.family_key(a)[0] == reprints.family_key(b)[0]


def test_cost_must_match():
    a = card("Shock", "Deal 2 damage.", cost="{R}")
    b = card("Zap", "Deal 2 damage.", cost="{1}{R}")
    assert reprints.family_key(a) != reprints.family_key(b)


def test_type_line_must_match():
    a = card("Shock", "Deal 2 damage.", type_line="Instant")
    b = card("Zap", "Deal 2 damage.", type_line="Sorcery")
    assert reprints.family_key(a) != reprints.family_key(b)


def test_theme_and_art_cards_are_excluded():
    theme = card("Aang", "(Theme color: {W})", type_line="Card")
    assert not reprints.is_eligible(theme)


def test_vanilla_cards_are_excluded():
    vanilla = card("Bear", "", type_line="Creature — Bear", cost="{1}{G}")
    assert not reprints.is_eligible(vanilla)


def test_grouping_keeps_only_real_families():
    # Names must be longer than one letter: normalisation replaces the card's
    # own name with "~", and a single-letter name would shred the text.
    cards = [
        card("Shock", "Deal 3 damage to any target."),
        card("Zap", "Deal 3 damage to any target."),
        card("Insight", "Draw two cards."),
    ]
    families = reprints.build_families(cards)
    assert len(families) == 1
    assert families[0]["members"] == ["Shock", "Zap"]
