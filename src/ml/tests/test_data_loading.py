"""Tests for data loading utilities."""

from pathlib import Path

from ..utils.paths import PATHS


class TestPaths:
    """Test canonical path configuration."""

    def test_paths_exist(self):
        """All path constants should be defined"""
        assert hasattr(PATHS, "pairs_large")
        assert hasattr(PATHS, "test_magic")
        assert hasattr(PATHS, "experiment_log")
        assert hasattr(PATHS, "decks_with_metadata")

    def test_paths_are_paths(self):
        """All paths should be Path objects"""
        assert isinstance(PATHS.pairs_large, Path)
        assert isinstance(PATHS.test_magic, Path)
        assert isinstance(PATHS.decks_with_metadata, Path)

    def test_experiment_log_points_to_canonical(self):
        """Experiment log should point to canonical version"""
        assert "CANONICAL" in str(PATHS.experiment_log)

    def test_embedding_helper(self):
        """Embedding path helper should work"""
        path = PATHS.embedding("test_model")
        assert "embeddings" in str(path)
        assert path.suffix == ".wv"


class TestDataLoading:
    """Test data loading functions."""

    def test_load_test_set(self):
        """Load test set should return dict"""
        from ..utils.data_loading import load_test_set

        # Use small test set
        if PATHS.test_magic.exists():
            test_set = load_test_set("magic")
            assert isinstance(test_set, dict)
            assert len(test_set) > 0

            # Check structure - test set values can be various types
            for query, relevant in test_set.items():
                assert isinstance(query, str)
                # Relevant can be list, dict, or even string (for legacy formats)
                assert relevant is not None

    def test_adjacency_graph_building(self):
        """Build adjacency graph from pairs"""
        import pandas as pd

        from ..utils.data_loading import build_adjacency_dict

        # Create small test graph
        test_data = pd.DataFrame(
            {"NAME_1": ["A", "B", "C"], "NAME_2": ["B", "C", "A"], "COUNT_MULTISET": [1, 2, 1]}
        )

        graph = build_adjacency_dict(test_data)

        assert "A" in graph
        assert "B" in graph["A"]
        assert "C" in graph["B"]

        # Should be bidirectional
        assert "A" in graph["C"]
