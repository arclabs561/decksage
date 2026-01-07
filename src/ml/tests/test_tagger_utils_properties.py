#!/usr/bin/env python3
"""
Property-based tests for tagger utilities using Hypothesis.

Tests invariants that should always hold true for extract_tag_dict and extract_tag_set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hypothesis import given, strategies as st

from ..utils.tagger_utils import extract_tag_dict, extract_tag_set


class TestTaggerUtilsProperties:
    """Property-based tests for tagger utilities."""

    @given(
        tag_dict=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(
                st.booleans(),
                st.text(max_size=50),
                st.integers(),
                st.floats(),
                st.none(),
            ),
            min_size=0,
            max_size=20,
        )
    )
    def test_extract_tag_dict_preserves_dict(self, tag_dict: dict[str, Any]):
        """extract_tag_dict should return dict unchanged when input is dict."""
        result = extract_tag_dict(tag_dict)
        assert result == tag_dict
        assert result is tag_dict  # Should be same object

    @given(tags_obj=st.none())
    def test_extract_tag_dict_none_returns_empty(self, tags_obj: None):
        """extract_tag_dict should return empty dict for None."""
        result = extract_tag_dict(tags_obj)
        assert result == {}
        assert isinstance(result, dict)

    @given(
        tag_set=st.sets(
            st.text(min_size=1, max_size=20).filter(lambda x: x != "card_name"),
            min_size=0,
            max_size=10,
        ),
        exclude_fields=st.sets(st.text(min_size=1, max_size=20), min_size=0, max_size=5),
    )
    def test_extract_tag_set_excludes_specified_fields(self, tag_set: set[str], exclude_fields: set[str]):
        """extract_tag_set should exclude specified fields."""
        # Create dict with all tags as True
        tag_dict = {tag: True for tag in tag_set}
        tag_dict["card_name"] = "Test Card"  # Add card_name (excluded by default)

        result = extract_tag_set(tag_dict, exclude_fields=exclude_fields)

        # Should not include excluded fields
        assert "card_name" not in result
        for excluded in exclude_fields:
            assert excluded not in result

        # Should include non-excluded True bool tags
        for tag in tag_set:
            if tag not in exclude_fields:
                assert tag in result

    @given(
        tag_dict=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.booleans(),
            min_size=0,
            max_size=15,
        )
    )
    def test_extract_tag_set_only_includes_true_bools(self, tag_dict: dict[str, bool]):
        """extract_tag_set should only include fields that are bool and True."""
        # Add non-bool fields
        tag_dict["card_name"] = "Test Card"
        tag_dict["count"] = 4
        tag_dict["price"] = 0.5

        result = extract_tag_set(tag_dict)

        # Should only include bool True values (excluding card_name by default)
        assert "card_name" not in result
        assert "count" not in result
        assert "price" not in result

        for key, value in tag_dict.items():
            if key != "card_name" and isinstance(value, bool) and value:
                assert key in result
            elif key != "card_name":
                assert key not in result

    @given(
        tag_dict=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(lambda x: x != "card_name"),
            values=st.booleans(),
            min_size=0,
            max_size=10,
        )
    )
    def test_extract_tag_set_idempotent(self, tag_dict: dict[str, bool]):
        """extract_tag_set should be idempotent (applying twice gives same result)."""
        tag_dict["card_name"] = "Test Card"

        result1 = extract_tag_set(tag_dict)
        result2 = extract_tag_set(tag_dict)

        assert result1 == result2

    @given(
        tag_dict1=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(lambda x: x != "card_name"),
            values=st.booleans(),
            min_size=0,
            max_size=10,
        ),
        tag_dict2=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(lambda x: x != "card_name"),
            values=st.booleans(),
            min_size=0,
            max_size=10,
        ),
    )
    def test_extract_tag_set_union_property(self, tag_dict1: dict[str, bool], tag_dict2: dict[str, bool]):
        """extract_tag_set should handle union of tag sets correctly."""
        tag_dict1["card_name"] = "Card 1"
        tag_dict2["card_name"] = "Card 2"

        set1 = extract_tag_set(tag_dict1)
        set2 = extract_tag_set(tag_dict2)

        # Union of tag sets should be extractable from union of dicts
        # Note: When unioning dicts, if a key exists in both, the second value wins
        # So we need to ensure True values are preserved in the union
        union_dict = {**tag_dict1, **tag_dict2}
        union_dict["card_name"] = "Union Card"
        
        # For keys that exist in both, preserve True if either was True
        for key in set(tag_dict1.keys()) & set(tag_dict2.keys()):
            if key != "card_name":
                union_dict[key] = tag_dict1[key] or tag_dict2[key]
        
        union_set = extract_tag_set(union_dict)

        # Union set should contain all True tags from both sets
        # (if a tag is True in either dict, it should be in the union set)
        for tag in set1:
            assert tag in union_set
        for tag in set2:
            assert tag in union_set

    @given(
        tag_dict=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(st.booleans(), st.text(max_size=50), st.integers()),
            min_size=0,
            max_size=15,
        )
    )
    def test_extract_tag_set_never_contains_card_name(self, tag_dict: dict[str, Any]):
        """extract_tag_set should never include card_name (default exclusion)."""
        tag_dict["card_name"] = "Test Card"

        result = extract_tag_set(tag_dict)

        assert "card_name" not in result

    @given(
        tag_dict=st.dictionaries(
            keys=st.text(min_size=1, max_size=20).filter(lambda x: x != "card_name"),
            values=st.booleans(),
            min_size=1,
            max_size=10,
        )
    )
    def test_extract_tag_set_size_bounded(self, tag_dict: dict[str, bool]):
        """extract_tag_set size should be bounded by number of True bools."""
        tag_dict["card_name"] = "Test Card"

        result = extract_tag_set(tag_dict)

        # Size should be at most number of non-card_name keys
        max_possible = len([k for k in tag_dict.keys() if k != "card_name"])
        assert len(result) <= max_possible

        # Size should equal number of True bools (excluding card_name)
        true_count = sum(1 for k, v in tag_dict.items() if k != "card_name" and v is True)
        assert len(result) == true_count

