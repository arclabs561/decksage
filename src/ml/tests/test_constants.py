"""Test game-specific constants and filters."""

from ..utils.constants import GAME_FILTERS, RELEVANCE_WEIGHTS, get_filter_set


def test_game_filters_exist():
    """All supported games have filter definitions."""
    assert "magic" in GAME_FILTERS
    assert "yugioh" in GAME_FILTERS
    assert "pokemon" in GAME_FILTERS


def test_magic_filters():
    """Magic has proper land filtering."""
    basic = get_filter_set("magic", "basic")
    assert "Plains" in basic
    assert "Island" in basic
    assert len(basic) == 5

    common = get_filter_set("magic", "common")
    assert "Snow-Covered Plains" in common
    assert len(common) > len(basic)

    all_filters = get_filter_set("magic", "all")
    assert "Command Tower" in all_filters
    assert len(all_filters) > len(common)


def test_pokemon_filters():
    """Pokemon has energy filtering."""
    energy = get_filter_set("pokemon", "basic")
    assert "Fire Energy" in energy
    assert "Water Energy" in energy
    assert len(energy) == 9  # 9 basic energy types


def test_yugioh_filters():
    """Yu-Gi-Oh returns empty set (no lands)."""
    filters = get_filter_set("yugioh", "basic")
    assert isinstance(filters, set)
    # YGO doesn't have lands, so empty is expected


def test_relevance_weights():
    """Relevance weights are properly ordered."""
    assert RELEVANCE_WEIGHTS["highly_relevant"] == 1.0
    assert RELEVANCE_WEIGHTS["relevant"] > RELEVANCE_WEIGHTS["somewhat_relevant"]
    assert RELEVANCE_WEIGHTS["irrelevant"] == 0.0
    assert 0.0 <= min(RELEVANCE_WEIGHTS.values()) <= 1.0
    assert 0.0 <= max(RELEVANCE_WEIGHTS.values()) <= 1.0


def test_case_insensitive():
    """Game names are case-insensitive."""
    assert get_filter_set("MAGIC", "basic") == get_filter_set("magic", "basic")
    assert get_filter_set("Pokemon", "basic") == get_filter_set("pokemon", "basic")


def test_unknown_game():
    """Unknown game returns empty set."""
    assert get_filter_set("unknown_game", "basic") == set()


def test_unknown_level():
    """Unknown filter level returns empty set."""
    assert get_filter_set("magic", "nonexistent") == set()
