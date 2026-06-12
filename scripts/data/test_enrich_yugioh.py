#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Tests for enrich_yugioh_cards.py functions."""

from __future__ import annotations

import sys
from pathlib import Path


# Add scripts/data to path so we can import the module
sys.path.insert(0, str(Path(__file__).parent))

from enrich_yugioh_cards import (
    build_oracle_text_enriched,
    classify_card_category,
    classify_effect_types,
    classify_monster_type,
    extract_summoning_requirements,
)


# --- classify_monster_type ---


class TestClassifyMonsterType:
    def test_effect_monster(self):
        assert classify_monster_type("Effect Monster") == "Effect"

    def test_normal_monster(self):
        assert classify_monster_type("Normal Monster") == "Normal"

    def test_fusion(self):
        assert classify_monster_type("Fusion Monster") == "Fusion"

    def test_synchro_tuner(self):
        assert classify_monster_type("Synchro Tuner Monster") == "Synchro Tuner"

    def test_link(self):
        assert classify_monster_type("Link Monster") == "Link"

    def test_pendulum_effect_fusion(self):
        assert classify_monster_type("Pendulum Effect Fusion Monster") == "Pendulum Effect Fusion"

    def test_xyz(self):
        assert classify_monster_type("XYZ Monster") == "XYZ"

    def test_spell_card(self):
        assert classify_monster_type("Spell Card") == ""

    def test_trap_card(self):
        assert classify_monster_type("Trap Card") == ""

    def test_bare_monster(self):
        # Edge case: just "Monster" with no prefix
        assert classify_monster_type("Monster") == "Normal"


# --- classify_card_category ---


class TestClassifyCardCategory:
    def test_monster(self):
        assert classify_card_category("Effect Monster") == "Monster"

    def test_spell(self):
        assert classify_card_category("Spell Card") == "Spell"

    def test_trap(self):
        assert classify_card_category("Trap Card") == "Trap"

    def test_token(self):
        assert classify_card_category("Token") == "Token"

    def test_fusion_monster(self):
        assert classify_card_category("Fusion Monster") == "Monster"

    def test_unknown(self):
        assert classify_card_category("Weird Type") == "Weird Type"


# --- extract_summoning_requirements ---


class TestExtractSummoningRequirements:
    def test_fusion_named_materials(self):
        desc = '"ABC-Dragon Buster" + "XYZ-Dragon Cannon"\nMust be Special Summoned...'
        result = extract_summoning_requirements(desc, "Fusion Monster")
        assert result == '"ABC-Dragon Buster" + "XYZ-Dragon Cannon"'

    def test_synchro_generic(self):
        desc = "1 Tuner + 1+ non-Tuner monsters\nIf this card is Synchro Summoned..."
        result = extract_summoning_requirements(desc, "Synchro Monster")
        assert result == "1 Tuner + 1+ non-Tuner monsters"

    def test_xyz_generic(self):
        desc = "2 Level 4 monsters\nWhile this card has a material attached..."
        result = extract_summoning_requirements(desc, "Xyz Monster")
        assert result == "2 Level 4 monsters"

    def test_link_with_requirement(self):
        desc = "2+ monsters, including a Fiend monster\nDuring the Main Phase..."
        result = extract_summoning_requirements(desc, "Link Monster")
        assert result == "2+ monsters, including a Fiend monster"

    def test_ritual_with_spell(self):
        desc = 'You can Ritual Summon this card with "Mitsurugi Ritual". Monsters your opponent controls...'
        result = extract_summoning_requirements(desc, "Ritual Monster")
        assert result == 'Ritual Spell: "Mitsurugi Ritual"'

    def test_effect_monster_returns_empty(self):
        desc = "When this card is Normal Summoned: You can target 1 monster..."
        result = extract_summoning_requirements(desc, "Effect Monster")
        assert result == ""

    def test_spell_returns_empty(self):
        desc = "Destroy all monsters on the field."
        result = extract_summoning_requirements(desc, "Spell Card")
        assert result == ""

    def test_empty_desc(self):
        assert extract_summoning_requirements("", "Fusion Monster") == ""

    def test_fusion_no_material_line(self):
        # Some fusion cards don't list materials on the first line
        desc = "A massive dragon born from the fusion of many dragons."
        result = extract_summoning_requirements(desc, "Fusion Monster")
        assert result == ""

    def test_synchro_with_carriage_return(self):
        desc = "1 Tuner + 1+ non-Tuner monsters\r\nIf this card is Synchro Summoned..."
        result = extract_summoning_requirements(desc, "Synchro Monster")
        assert result == "1 Tuner + 1+ non-Tuner monsters"


# --- classify_effect_types ---


class TestClassifyEffectTypes:
    def test_quick_effect(self):
        desc = "During the Main Phase (Quick Effect): You can discard 1 card..."
        result = classify_effect_types(desc)
        assert "Quick Effect" in result

    def test_flip(self):
        desc = "FLIP: Destroy all Level 4 monsters your opponent controls."
        result = classify_effect_types(desc)
        assert "Flip" in result

    def test_trigger(self):
        desc = "If this card is sent to the GY: You can draw 1 card."
        result = classify_effect_types(desc)
        assert "Trigger" in result

    def test_continuous(self):
        desc = "While this card is face-up on the field, all Dragon monsters gain 300 ATK."
        result = classify_effect_types(desc)
        assert "Continuous" in result

    def test_ritual_pattern(self):
        desc = 'You can Ritual Summon this card with "Black Luster Ritual".'
        result = classify_effect_types(desc)
        assert "Ritual" in result

    def test_multiple_types(self):
        desc = (
            "FLIP: Draw 1 card.\n"
            "If this card is destroyed: You can target 1 card; destroy it.\n"
            "(Quick Effect): You can banish this card from the GY..."
        )
        result = classify_effect_types(desc)
        assert "Flip" in result
        assert "Quick Effect" in result
        assert "Trigger" in result

    def test_empty(self):
        assert classify_effect_types("") == ""

    def test_vanilla_monster(self):
        desc = "A ferocious dragon with a deadly attack."
        result = classify_effect_types(desc)
        assert result == ""

    def test_gains_for_each(self):
        desc = "This card gains 500 ATK for each Dragon monster in your GY."
        result = classify_effect_types(desc)
        assert "Continuous" in result

    def test_once_per_turn(self):
        desc = "Once per turn, you can flip this card into face-down Defense Position."
        result = classify_effect_types(desc)
        assert "Once Per Turn" in result

    def test_optional_you_can(self):
        desc = "Once per turn: You can target 1 LIGHT monster in your GY; add it to your hand."
        result = classify_effect_types(desc)
        assert "Optional" in result
        assert "Quick Effect" not in result

    def test_conditional_must_be(self):
        desc = "Must be Special Summoned (from your Extra Deck) by sending the above cards..."
        result = classify_effect_types(desc)
        assert "Conditional" in result

    def test_conditional_can_only_be(self):
        desc = "Can only be Special Summoned by Tributing 3 monsters."
        result = classify_effect_types(desc)
        assert "Conditional" in result

    def test_protective_unaffected(self):
        desc = "Unaffected by other cards' effects."
        result = classify_effect_types(desc)
        assert "Protective" in result

    def test_quick_effect_not_optional(self):
        """Quick Effect cards should not also get the Optional tag."""
        desc = "During the Main Phase (Quick Effect): You can discard 1 card; draw 1 card."
        result = classify_effect_types(desc)
        assert "Quick Effect" in result
        assert "Optional" not in result


# --- build_oracle_text_enriched ---


class TestBuildOracleTextEnriched:
    def test_basic_monster(self):
        card = {
            "type": "Effect Monster",
            "desc": "When this card is summoned: draw 1 card.",
            "atk": 1800,
            "def": 1200,
            "level": 4,
            "attribute": "DARK",
            "race": "Spellcaster",
        }
        result = build_oracle_text_enriched(card)
        assert "When this card is summoned: draw 1 card." in result
        assert "ATK 1800" in result
        assert "DEF 1200" in result
        assert "Level 4" in result
        assert "Spellcaster" in result

    def test_pendulum_monster(self):
        card = {
            "type": "Pendulum Effect Monster",
            "pend_desc": "You can Special Summon 1 monster.",
            "monster_desc": "When this card attacks: gain 500 ATK.",
            "desc": "Full description here.",
            "atk": 2500,
            "def": 2000,
            "level": 7,
            "attribute": "FIRE",
            "race": "Dragon",
        }
        result = build_oracle_text_enriched(card)
        assert "[Pendulum Effect]" in result
        assert "[Monster Effect]" in result
        assert "You can Special Summon 1 monster." in result
        assert "When this card attacks: gain 500 ATK." in result

    def test_link_monster(self):
        card = {
            "type": "Link Monster",
            "desc": "2+ Effect Monsters\nThis card gains effects...",
            "atk": 2800,
            "def": None,
            "linkval": 4,
            "attribute": "DARK",
            "race": "Fiend",
        }
        result = build_oracle_text_enriched(card)
        assert "Link-4" in result
        assert "ATK 2800" in result

    def test_xyz_monster(self):
        card = {
            "type": "XYZ Monster",
            "desc": "2 Level 4 monsters\nOnce per turn: detach...",
            "atk": 1700,
            "def": 1100,
            "level": 4,
            "attribute": "WATER",
            "race": "Sea Serpent",
        }
        result = build_oracle_text_enriched(card)
        assert "Rank 4" in result

    def test_spell_card(self):
        card = {
            "type": "Spell Card",
            "desc": "Draw 2 cards.",
        }
        result = build_oracle_text_enriched(card)
        assert result == "Draw 2 cards."

    def test_empty_desc(self):
        card = {"type": "Effect Monster", "desc": ""}
        result = build_oracle_text_enriched(card)
        # Should still have stats if available
        assert result == "" or "---" in result
