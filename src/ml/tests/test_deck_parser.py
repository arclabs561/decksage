"""Tests for deck list text parser (src/ml/utils/deck_parser.py)."""

from __future__ import annotations

import pytest

from ..utils.deck_parser import parse_deck_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cards(result: dict, partition: str) -> dict[str, int]:
    """Extract {name: count} from a parsed result for a given partition."""
    for p in result.get("partitions", []):
        if p["name"] == partition:
            return {c["name"]: c["count"] for c in p["cards"]}
    return {}


def _total(result: dict) -> int:
    """Total card count across all partitions."""
    return sum(c["count"] for p in result.get("partitions", []) for c in p["cards"])


# ---------------------------------------------------------------------------
# Format 1: Arena / MTGO
# ---------------------------------------------------------------------------


class TestArenaFormat:
    def test_basic_deck_and_sideboard(self):
        text = """\
Deck
4 Lightning Bolt
4 Monastery Swiftspear
20 Mountain

Sideboard
2 Smash to Smithereens
1 Tormod's Crypt
"""
        result = parse_deck_text(text, game="magic")
        assert "partitions" in result
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4
        assert main["Monastery Swiftspear"] == 4
        assert main["Mountain"] == 20
        sb = _cards(result, "Sideboard")
        assert sb["Smash to Smithereens"] == 2
        assert sb["Tormod's Crypt"] == 1

    def test_no_sideboard_section(self):
        text = """\
Deck
4 Lightning Bolt
20 Mountain
"""
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4
        assert "Sideboard" not in [p["name"] for p in result["partitions"]]

    def test_deck_keyword_missing_defaults_to_main(self):
        text = """\
4 Lightning Bolt
4 Monastery Swiftspear
"""
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4


# ---------------------------------------------------------------------------
# Format 2: Simple count (4x / x4)
# ---------------------------------------------------------------------------


class TestSimpleCountFormat:
    def test_count_prefix_with_x(self):
        text = """\
4x Lightning Bolt
2x Monastery Swiftspear
"""
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4
        assert main["Monastery Swiftspear"] == 2

    def test_count_suffix(self):
        text = """\
Lightning Bolt x4
Monastery Swiftspear x2
"""
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4
        assert main["Monastery Swiftspear"] == 2

    def test_count_prefix_no_x(self):
        text = "4 Lightning Bolt\n"
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4

    def test_uppercase_X(self):
        text = "4X Lightning Bolt\n"
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4


# ---------------------------------------------------------------------------
# Format 3: Plain list (no counts)
# ---------------------------------------------------------------------------


class TestPlainListFormat:
    def test_plain_names(self):
        text = """\
Lightning Bolt
Monastery Swiftspear
Mountain
"""
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 1
        assert main["Monastery Swiftspear"] == 1
        assert main["Mountain"] == 1

    def test_duplicate_names_accumulate(self):
        text = """\
Lightning Bolt
Lightning Bolt
Lightning Bolt
"""
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 3


# ---------------------------------------------------------------------------
# Format 4: YGO
# ---------------------------------------------------------------------------


class TestYGOFormat:
    def test_main_and_extra_deck(self):
        text = """\
Main Deck:
3x Ash Blossom & Joyous Spring
2x Maxx "C"

Extra Deck:
1x Accesscode Talker
"""
        result = parse_deck_text(text, game="yugioh")
        main = _cards(result, "Main Deck")
        assert main["Ash Blossom & Joyous Spring"] == 3
        assert main['Maxx "C"'] == 2
        extra = _cards(result, "Extra Deck")
        assert extra["Accesscode Talker"] == 1

    def test_side_deck(self):
        text = """\
Main Deck:
3x Ash Blossom & Joyous Spring

Side Deck:
2x Nibiru, the Primal Being
"""
        result = parse_deck_text(text, game="yugioh")
        side = _cards(result, "Side Deck")
        assert side["Nibiru, the Primal Being"] == 2

    def test_standalone_card_ids_skipped(self):
        text = """\
Main Deck:
3x Ash Blossom & Joyous Spring
14558127
"""
        result = parse_deck_text(text, game="yugioh")
        main = _cards(result, "Main Deck")
        assert len(main) == 1
        assert "14558127" not in main

    def test_ygo_default_partition(self):
        text = "3 Ash Blossom & Joyous Spring\n"
        result = parse_deck_text(text, game="yugioh")
        main = _cards(result, "Main Deck")
        assert main["Ash Blossom & Joyous Spring"] == 3


# ---------------------------------------------------------------------------
# Format 5: Pokemon
# ---------------------------------------------------------------------------


class TestPokemonFormat:
    def test_pokemon_sections_with_set_codes(self):
        text = """\
Pokemon - 12
4 Charizard ex SV3 6
2 Charmander SV3 4

Trainer - 28
4 Professor's Research SVI 189

Energy - 10
10 Fire Energy SVE 2
"""
        result = parse_deck_text(text, game="pokemon")
        pokemon = _cards(result, "Pokemon")
        assert pokemon["Charizard ex"] == 4
        assert pokemon["Charmander"] == 2
        trainer = _cards(result, "Trainer")
        assert trainer["Professor's Research"] == 4
        energy = _cards(result, "Energy")
        assert energy["Fire Energy"] == 10

    def test_pokemon_no_sections_goes_to_main(self):
        text = """\
4 Charizard ex SV3 6
2 Charmander SV3 4
"""
        result = parse_deck_text(text, game="pokemon")
        main = _cards(result, "Main Deck")
        assert main["Charizard ex"] == 4
        assert main["Charmander"] == 2


# ---------------------------------------------------------------------------
# Special characters
# ---------------------------------------------------------------------------


class TestSpecialCharacters:
    def test_apostrophe(self):
        text = "4 Professor's Research\n"
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Professor's Research"] == 4

    def test_ampersand(self):
        text = "3 Ash Blossom & Joyous Spring\n"
        result = parse_deck_text(text, game="yugioh")
        main = _cards(result, "Main Deck")
        assert main["Ash Blossom & Joyous Spring"] == 3

    def test_quotes_in_name(self):
        text = '2 Maxx "C"\n'
        result = parse_deck_text(text, game="yugioh")
        main = _cards(result, "Main Deck")
        assert main['Maxx "C"'] == 2

    def test_comma_in_name(self):
        text = "2 Nibiru, the Primal Being\n"
        result = parse_deck_text(text, game="yugioh")
        main = _cards(result, "Main Deck")
        assert main["Nibiru, the Primal Being"] == 2

    def test_hyphen_in_name(self):
        text = "4 Lava Coil\n1 Fire-Lit Thicket\n"
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Fire-Lit Thicket"] == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_input(self):
        result = parse_deck_text("", game="magic")
        assert "error" in result

    def test_whitespace_only(self):
        result = parse_deck_text("   \n\n  \n", game="magic")
        assert "error" in result

    def test_comments_only(self):
        result = parse_deck_text("# This is a comment\n// Another comment\n", game="magic")
        assert "error" in result

    def test_unknown_game(self):
        result = parse_deck_text("4 Lightning Bolt", game="hearthstone")
        assert "error" in result
        assert "hearthstone" in result["error"].lower()

    def test_blank_lines_ignored(self):
        text = """\
4 Lightning Bolt

4 Mountain

"""
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4
        assert main["Mountain"] == 4

    def test_mixed_formats_in_one_list(self):
        """Mix of count-prefix, count-suffix, and plain."""
        text = """\
4 Lightning Bolt
Monastery Swiftspear x2
Mountain
"""
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4
        assert main["Monastery Swiftspear"] == 2
        assert main["Mountain"] == 1

    def test_duplicate_entries_merge(self):
        text = """\
2 Lightning Bolt
2 Lightning Bolt
"""
        result = parse_deck_text(text, game="magic")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4

    def test_game_case_insensitive(self):
        result = parse_deck_text("4 Lightning Bolt", game="MAGIC")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4

    def test_game_whitespace_stripped(self):
        result = parse_deck_text("4 Lightning Bolt", game="  magic  ")
        main = _cards(result, "Main")
        assert main["Lightning Bolt"] == 4

    def test_total_count_correct(self):
        text = """\
Deck
4 Lightning Bolt
20 Mountain

Sideboard
2 Smash to Smithereens
"""
        result = parse_deck_text(text, game="magic")
        assert _total(result) == 26

    def test_section_header_colon_no_count(self):
        text = """\
Main Deck:
3 Ash Blossom & Joyous Spring
"""
        result = parse_deck_text(text, game="yugioh")
        main = _cards(result, "Main Deck")
        assert main["Ash Blossom & Joyous Spring"] == 3

    def test_pokemon_set_code_variations(self):
        """Different set code lengths should all be stripped."""
        text = """\
Pokemon - 3
1 Pikachu V SWSH 43
1 Mew VMAX FST 114
1 Arceus VSTAR BRS 123
"""
        result = parse_deck_text(text, game="pokemon")
        pokemon = _cards(result, "Pokemon")
        assert "Pikachu V" in pokemon
        assert "Mew VMAX" in pokemon
        assert "Arceus VSTAR" in pokemon
