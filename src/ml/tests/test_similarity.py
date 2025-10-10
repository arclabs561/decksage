"""Tests for similarity functions."""

from ..utils.evaluation import jaccard_similarity


class TestJaccardSimilarity:
    """Test Jaccard similarity calculation."""

    def test_identical_sets(self):
        """Identical sets should have similarity 1.0"""
        s1 = {1, 2, 3}
        s2 = {1, 2, 3}
        assert jaccard_similarity(s1, s2) == 1.0

    def test_disjoint_sets(self):
        """Disjoint sets should have similarity 0.0"""
        s1 = {1, 2, 3}
        s2 = {4, 5, 6}
        assert jaccard_similarity(s1, s2) == 0.0

    def test_partial_overlap(self):
        """Partial overlap should give correct ratio"""
        s1 = {1, 2, 3, 4}
        s2 = {3, 4, 5, 6}
        # Intersection: {3, 4} = 2
        # Union: {1,2,3,4,5,6} = 6
        # Jaccard: 2/6 = 0.333...
        assert abs(jaccard_similarity(s1, s2) - (2 / 6)) < 0.001

    def test_empty_sets(self):
        """Empty sets should return 0.0 (avoid division by zero)"""
        s1 = set()
        s2 = set()
        assert jaccard_similarity(s1, s2) == 0.0

    def test_one_empty(self):
        """One empty set should give 0.0"""
        s1 = {1, 2, 3}
        s2 = set()
        assert jaccard_similarity(s1, s2) == 0.0

    def test_subset(self):
        """Subset case"""
        s1 = {1, 2}
        s2 = {1, 2, 3, 4}
        # Intersection: {1, 2} = 2
        # Union: {1, 2, 3, 4} = 4
        # Jaccard: 2/4 = 0.5
        assert jaccard_similarity(s1, s2) == 0.5


class TestCardSimilarity:
    """Test card-specific similarity logic."""

    def test_land_filtering(self):
        """Basic lands should be filtered from similarity"""
        from ..utils.constants import get_filter_set

        lands = get_filter_set("magic", "basic")
        assert "Plains" in lands
        assert "Island" in lands
        assert "Lightning Bolt" not in lands

    def test_multiGame_filters(self):
        """All games should have filter sets"""
        from ..utils.constants import get_filter_set

        # All should return sets without error
        magic_filters = get_filter_set("magic", "basic")
        pokemon_filters = get_filter_set("pokemon", "basic")
        yugioh_filters = get_filter_set("yugioh", "basic")

        assert isinstance(magic_filters, set)
        assert isinstance(pokemon_filters, set)
        assert isinstance(yugioh_filters, set)
