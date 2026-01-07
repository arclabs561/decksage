#!/usr/bin/env python3
"""
Tests for tagger utilities (extract_tag_dict, extract_tag_set).

Covers edge cases for dataclasses, regular classes, dicts, and error scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ..utils.tagger_utils import extract_tag_dict, extract_tag_set


class TestExtractTagDict:
    """Tests for extract_tag_dict function."""

    def test_none_returns_empty_dict(self):
        """Test that None input returns empty dict."""
        assert extract_tag_dict(None) == {}

    def test_dict_returns_as_is(self):
        """Test that dict input is returned unchanged."""
        d = {"card_name": "Bolt", "removal": True}
        assert extract_tag_dict(d) is d

    def test_dataclass_basic(self):
        """Test dataclass extraction."""

        @dataclass
        class Tags:
            card_name: str
            removal: bool = False
            draw: bool = False

        tags = Tags("Lightning Bolt", removal=True)
        result = extract_tag_dict(tags)
        assert result == {"card_name": "Lightning Bolt", "removal": True, "draw": False}
        assert isinstance(result, dict)

    def test_dataclass_nested(self):
        """Test dataclass with nested structures."""

        @dataclass
        class NestedTags:
            card_name: str
            tags: dict[str, bool]

        tags = NestedTags("Bolt", {"removal": True, "draw": False})
        result = extract_tag_dict(tags)
        assert result["card_name"] == "Bolt"
        assert result["tags"] == {"removal": True, "draw": False}

    def test_regular_class_with_dict(self):
        """Test regular class with __dict__."""

        class RegularTags:
            def __init__(self):
                self.card_name = "Bolt"
                self.removal = True
                self.draw = False

        tags = RegularTags()
        result = extract_tag_dict(tags)
        assert result == {"card_name": "Bolt", "removal": True, "draw": False}

    def test_regular_class_empty(self):
        """Test regular class with no attributes."""
        class EmptyTags:
            pass

        tags = EmptyTags()
        result = extract_tag_dict(tags)
        assert result == {}

    def test_class_without_dict_fallback(self):
        """Test class without __dict__ uses dir() fallback."""

        class SlotsTags:
            __slots__ = ("card_name", "removal")

            def __init__(self):
                self.card_name = "Bolt"
                self.removal = True

        tags = SlotsTags()
        result = extract_tag_dict(tags)
        # Should use dir() fallback, may include methods
        assert "card_name" in result
        assert result["card_name"] == "Bolt"

    def test_empty_dict(self):
        """Test empty dict input."""
        assert extract_tag_dict({}) == {}

    def test_mixed_types_in_dict(self):
        """Test dict with mixed value types."""
        d = {
            "card_name": "Bolt",
            "removal": True,
            "count": 4,
            "price": 0.5,
            "tags": ["instant", "damage"],
        }
        result = extract_tag_dict(d)
        assert result == d


class TestExtractTagSet:
    """Tests for extract_tag_set function."""

    def test_none_returns_empty_set(self):
        """Test that None input returns empty set."""
        assert extract_tag_set(None) == set()

    def test_dataclass_basic(self):
        """Test extracting tags from dataclass."""

        @dataclass
        class Tags:
            card_name: str
            removal: bool = True
            draw: bool = False
            ramp: bool = True

        tags = Tags("Bolt", removal=True, draw=False, ramp=True)
        result = extract_tag_set(tags)
        assert result == {"removal", "ramp"}
        assert "card_name" not in result  # Excluded by default
        assert "draw" not in result  # False, not included

    def test_dict_input(self):
        """Test extracting tags from dict."""
        d = {
            "card_name": "Bolt",
            "removal": True,
            "draw": False,
            "ramp": True,
            "count": 4,  # Non-bool, should be ignored
        }
        result = extract_tag_set(d)
        assert result == {"removal", "ramp"}

    def test_all_false_tags(self):
        """Test when all tags are False."""
        d = {"card_name": "Bolt", "removal": False, "draw": False}
        assert extract_tag_set(d) == set()

    def test_empty_dict(self):
        """Test empty dict input."""
        assert extract_tag_set({}) == set()

    def test_custom_exclude_fields(self):
        """Test custom exclude_fields parameter."""

        @dataclass
        class Tags:
            card_name: str
            removal: bool = True
            draw: bool = True
            metadata: str = "test"

        tags = Tags("Bolt", removal=True, draw=True)
        # Exclude both card_name and removal
        result = extract_tag_set(tags, exclude_fields={"card_name", "removal"})
        assert result == {"draw"}

    def test_empty_exclude_fields(self):
        """Test with empty exclude_fields set."""

        @dataclass
        class Tags:
            card_name: str
            removal: bool = True

        tags = Tags("Bolt", removal=True)
        result = extract_tag_set(tags, exclude_fields=set())
        # card_name is not bool, so not included
        assert result == {"removal"}

    def test_non_bool_true_values_filtered(self):
        """Test that non-bool True values are filtered out."""
        d = {
            "card_name": "Bolt",
            "removal": True,  # Bool True, included
            "count": 1,  # Non-bool, excluded
            "name": "Lightning Bolt",  # Non-bool, excluded
            "active": True,  # Bool True, included
        }
        result = extract_tag_set(d)
        assert result == {"removal", "active"}
        assert "count" not in result
        assert "name" not in result

    def test_regular_class_input(self):
        """Test extracting tags from regular class."""

        class RegularTags:
            def __init__(self):
                self.card_name = "Bolt"
                self.removal = True
                self.draw = False

        tags = RegularTags()
        result = extract_tag_set(tags)
        assert result == {"removal"}


class TestTaggerUtilsIntegration:
    """Integration tests for tagger utilities with real tagger results."""

    def test_fusion_with_dataclass_tagger(self):
        """Test fusion system with dataclass tagger results."""
        from ..similarity.fusion import WeightedLateFusion

        @dataclass
        class MockTags:
            card_name: str
            removal: bool = False
            draw: bool = False

        class MockTagger:
            def tag_card(self, card: str):
                if card == "Lightning Bolt":
                    return MockTags("Lightning Bolt", removal=True)
                elif card == "Counterspell":
                    return MockTags("Counterspell", draw=True)
                return MockTags(card)

        tagger = MockTagger()
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=tagger,
            weights=None,
        )

        # Should compute functional tag similarity
        sim = fusion._get_functional_tag_similarity("Lightning Bolt", "Counterspell")
        assert sim == 0.0  # No overlap

        sim2 = fusion._get_functional_tag_similarity("Lightning Bolt", "Lightning Bolt")
        assert sim2 == 1.0  # Perfect overlap

    def test_fusion_with_regular_class_tagger(self):
        """Test fusion system with regular class tagger results."""
        from ..similarity.fusion import WeightedLateFusion

        class MockTags:
            def __init__(self, card_name: str, removal: bool = False, draw: bool = False):
                self.card_name = card_name
                self.removal = removal
                self.draw = draw

        class MockTagger:
            def tag_card(self, card: str):
                if card == "Lightning Bolt":
                    return MockTags("Lightning Bolt", removal=True)
                elif card == "Counterspell":
                    return MockTags("Counterspell", draw=True)
                return MockTags(card)

        tagger = MockTagger()
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=tagger,
            weights=None,
        )

        sim = fusion._get_functional_tag_similarity("Lightning Bolt", "Counterspell")
        assert sim == 0.0

    def test_fusion_with_dict_tagger(self):
        """Test fusion system with dict tagger results."""
        from ..similarity.fusion import WeightedLateFusion

        class MockTagger:
            def tag_card(self, card: str):
                if card == "Lightning Bolt":
                    return {"card_name": "Lightning Bolt", "removal": True, "draw": False}
                elif card == "Counterspell":
                    return {"card_name": "Counterspell", "removal": False, "draw": True}
                return {"card_name": card}

        tagger = MockTagger()
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=tagger,
            weights=None,
        )

        sim = fusion._get_functional_tag_similarity("Lightning Bolt", "Counterspell")
        assert sim == 0.0

    def test_tagger_returns_none(self):
        """Test handling when tagger returns None."""
        from ..similarity.fusion import WeightedLateFusion

        class MockTagger:
            def tag_card(self, card: str):
                return None

        tagger = MockTagger()
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=tagger,
            weights=None,
        )

        sim = fusion._get_functional_tag_similarity("Lightning Bolt", "Counterspell")
        assert sim == 0.0

    def test_tagger_raises_exception(self):
        """Test handling when tagger raises exception."""
        from ..similarity.fusion import WeightedLateFusion

        class MockTagger:
            def tag_card(self, card: str):
                raise ValueError("Tagger error")

        tagger = MockTagger()
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=tagger,
            weights=None,
        )

        # Should return 0.0 on exception
        sim = fusion._get_functional_tag_similarity("Lightning Bolt", "Counterspell")
        assert sim == 0.0


class TestMixedTaggerTypes:
    """Tests for mixed tagger result types in same session."""

    def test_fusion_switches_between_dataclass_and_regular_class(self):
        """Test fusion handles switching between dataclass and regular class taggers."""
        from dataclasses import dataclass
        from ..similarity.fusion import WeightedLateFusion

        @dataclass
        class DataclassTags:
            card_name: str
            removal: bool = False

        class RegularClassTags:
            def __init__(self, card_name: str, removal: bool = False):
                self.card_name = card_name
                self.removal = removal

        class SwitchingTagger:
            def __init__(self):
                self.call_count = 0

            def tag_card(self, card: str):
                self.call_count += 1
                # Return different types based on call count
                if self.call_count % 2 == 1:
                    return DataclassTags(card, removal=(card == "Lightning Bolt"))
                else:
                    return RegularClassTags(card, removal=(card == "Lightning Bolt"))

        tagger = SwitchingTagger()
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=tagger,
            weights=None,
        )

        # First call: dataclass
        sim1 = fusion._get_functional_tag_similarity("Lightning Bolt", "Lightning Bolt")
        assert sim1 == 1.0

        # Second call: regular class
        sim2 = fusion._get_functional_tag_similarity("Lightning Bolt", "Lightning Bolt")
        assert sim2 == 1.0

        # Third call: dataclass again
        sim3 = fusion._get_functional_tag_similarity("Lightning Bolt", "Counterspell")
        assert sim3 == 0.0

    def test_fusion_switches_between_dict_and_dataclass(self):
        """Test fusion handles switching between dict and dataclass taggers."""
        from dataclasses import dataclass
        from ..similarity.fusion import WeightedLateFusion

        @dataclass
        class DataclassTags:
            card_name: str
            removal: bool = False

        class SwitchingTagger:
            def __init__(self):
                self.call_count = 0

            def tag_card(self, card: str):
                self.call_count += 1
                # Alternate between dict and dataclass
                if self.call_count % 2 == 1:
                    return {"card_name": card, "removal": (card == "Lightning Bolt")}
                else:
                    return DataclassTags(card, removal=(card == "Lightning Bolt"))

        tagger = SwitchingTagger()
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=tagger,
            weights=None,
        )

        # First call: dict
        sim1 = fusion._get_functional_tag_similarity("Lightning Bolt", "Lightning Bolt")
        assert sim1 == 1.0

        # Second call: dataclass
        sim2 = fusion._get_functional_tag_similarity("Lightning Bolt", "Lightning Bolt")
        assert sim2 == 1.0


class TestMalformedTaggerResults:
    """Tests for handling malformed tagger results."""

    def test_missing_card_name_field(self):
        """Test handling when tagger result missing card_name field."""
        d = {"removal": True, "draw": False}  # Missing card_name
        result = extract_tag_set(d)
        # Should work fine, card_name is excluded anyway
        assert result == {"removal"}

    def test_wrong_type_for_bool_field(self):
        """Test handling when bool field has wrong type."""
        d = {"card_name": "Bolt", "removal": "yes", "draw": 1, "ramp": True}
        result = extract_tag_set(d)
        # Only actual bool True values should be included
        assert result == {"ramp"}

    def test_nested_structure(self):
        """Test handling of nested structures in tagger results."""
        d = {
            "card_name": "Bolt",
            "removal": True,
            "tags": {"removal": True, "draw": False},  # Nested dict
        }
        result = extract_tag_set(d)
        # Should extract top-level bools, ignore nested structures
        assert result == {"removal"}

    def test_unexpected_attributes(self):
        """Test handling of unexpected attributes in class."""
        class WeirdTags:
            def __init__(self):
                self.card_name = "Bolt"
                self.removal = True
                self._private = True  # Private attribute (bool True, will be included)
                self.__dunder__ = True  # Dunder attribute (bool True, will be included)

        tags = WeirdTags()
        result = extract_tag_set(tags)
        # extract_tag_set includes all bool True values, regardless of naming
        # card_name is excluded by default, but _private and __dunder__ are included
        # if they are bool True (current behavior - may want to filter these in future)
        assert "removal" in result
        assert "_private" in result  # Included because it's bool True
        assert "__dunder__" in result  # Included because it's bool True

    def test_empty_string_fields(self):
        """Test handling of empty string fields."""
        d = {"card_name": "", "removal": True, "draw": False}
        result = extract_tag_set(d)
        assert result == {"removal"}

    def test_none_values(self):
        """Test handling of None values."""
        d = {"card_name": "Bolt", "removal": True, "draw": None, "ramp": False}
        result = extract_tag_set(d)
        # None is not bool, should be filtered
        assert result == {"removal"}

    def test_fusion_with_malformed_result(self):
        """Test fusion handles malformed tagger results gracefully."""
        from ..similarity.fusion import WeightedLateFusion

        class MalformedTagger:
            def tag_card(self, card: str):
                # Return malformed result
                return {"removal": "yes", "draw": 1}  # Wrong types

        tagger = MalformedTagger()
        fusion = WeightedLateFusion(
            embeddings=None,
            adj=None,
            tagger=tagger,
            weights=None,
        )

        # Should return 0.0 (no valid bool tags)
        sim = fusion._get_functional_tag_similarity("Lightning Bolt", "Counterspell")
        assert sim == 0.0

    def test_extract_tag_dict_with_malformed_class(self):
        """Test extract_tag_dict with class that has problematic attributes."""
        class ProblematicTags:
            def __init__(self):
                self.card_name = "Bolt"
                self.removal = True

            def __getattr__(self, name):
                # Simulate attribute that raises
                if name == "problematic":
                    raise AttributeError("Problematic attribute")
                raise AttributeError(f"No attribute {name}")

        tags = ProblematicTags()
        result = extract_tag_dict(tags)
        # Should extract what's available in __dict__
        assert "card_name" in result
        assert result["card_name"] == "Bolt"

