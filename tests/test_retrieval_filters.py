"""Filter translation and post-filtering for the two retrieval arms."""

from __future__ import annotations

from ml.search.hybrid_search import (
    metadata_matches_filter,
    parse_filter_clauses,
)


def test_equality_matches_a_scalar_and_a_list():
    assert metadata_matches_filter({"rarity": "rare"}, 'rarity = "rare"')
    assert metadata_matches_filter({"colors": ["G", "U"]}, 'colors = "U"')
    assert not metadata_matches_filter({"colors": ["G"]}, 'colors = "U"')


def test_equality_is_case_insensitive():
    assert metadata_matches_filter({"set": "CLU"}, 'set = "clu"')
    assert metadata_matches_filter({"rarity": "Rare"}, 'rarity = "rare"')


def test_numeric_equality_ignores_float_formatting():
    """Meilisearch treats 2 and 2.0 as equal; so must the post-filter."""
    assert metadata_matches_filter({"cmc": 2.0}, "cmc = 2")
    assert metadata_matches_filter({"cmc": "2.0"}, "cmc = 2")
    assert not metadata_matches_filter({"cmc": 2.5}, "cmc = 2")


def test_numeric_comparisons():
    metadata = {"cmc": 2.0, "power": "4"}
    assert metadata_matches_filter(metadata, "cmc <= 2")
    assert not metadata_matches_filter(metadata, "cmc > 2")
    assert metadata_matches_filter(metadata, "power >= 4")
    assert not metadata_matches_filter(metadata, "power < 3")


def test_and_clauses_all_have_to_hold():
    metadata = {"colors": "R", "cmc": 1.0}
    assert metadata_matches_filter(metadata, 'colors = "R" AND cmc <= 2')
    assert not metadata_matches_filter(metadata, 'colors = "R" AND cmc >= 3')


def test_or_group_inside_parentheses():
    metadata = {"colors": "U"}
    assert metadata_matches_filter(metadata, '(colors = "W" OR colors = "U")')
    assert not metadata_matches_filter(metadata, '(colors = "W" OR colors = "B")')


def test_color_list_reads_the_display_string():
    """color_list is filter-only; metadata keeps colours as "GU"."""
    assert metadata_matches_filter({"colors": "GU"}, 'color_list = "U"')
    assert metadata_matches_filter({"colors": "GU"}, 'color_list = "G"')
    assert not metadata_matches_filter({"colors": "GU"}, 'color_list = "R"')


def test_missing_field_is_dropped_not_passed():
    """A filter the card cannot satisfy is not silently treated as a match."""
    assert not metadata_matches_filter({"name": "Bolt"}, 'set = "clu"')
    assert not metadata_matches_filter(None, 'set = "clu"')


def test_unparseable_clause_passes():
    """A clause we do not understand must not empty the result set."""
    assert metadata_matches_filter({"name": "Bolt"}, "some_meili_operator(?)")
    assert parse_filter_clauses("some_meili_operator(?)") is None


def test_no_filter_matches_everything():
    assert metadata_matches_filter({"name": "Bolt"}, None)
    assert metadata_matches_filter(None, None)
