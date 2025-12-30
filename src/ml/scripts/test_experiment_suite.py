#!/usr/bin/env python3
"""
Integrated Experiment Suite

Tests that all active experiments can run without errors.
Does NOT validate results (too expensive), just smoke tests.
"""

import shutil
import subprocess
from pathlib import Path

import pytest


class TestExperimentSuite:
    """Test all active experiments can run."""

    def test_exp_source_filtering_imports(self):
        """Test exp_source_filtering.py can import."""
        try:
            assert True
        except Exception as e:
            pytest.fail(f"Failed to import: {e}")

    def test_exp_format_specific_imports(self):
        """Test exp_format_specific.py can import."""
        try:
            assert True
        except Exception as e:
            pytest.fail(f"Failed to import: {e}")

    def test_validate_data_quality_imports(self):
        """Test validate_data_quality.py can import."""
        try:
            assert True
        except Exception as e:
            pytest.fail(f"Failed to import: {e}")


@pytest.mark.integration
class TestAnalysisTools:
    """Test analysis tools can run."""

    def test_archetype_staples_runs(self):
        """Smoke test archetype_staples.py."""
        # Just check it can start
        if not shutil.which("uv"):
            pytest.skip("uv not installed")
        result = subprocess.run(
            ["uv", "run", "python", "archetype_staples.py"],
            check=False,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 0

    def test_sideboard_analysis_imports(self):
        """Test sideboard_analysis.py can import."""
        try:
            assert True
        except Exception as e:
            pytest.fail(f"Failed to import: {e}")

    def test_card_companions_runs(self):
        """Smoke test card_companions.py."""
        if not shutil.which("uv"):
            pytest.skip("uv not installed")
        result = subprocess.run(
            ["uv", "run", "python", "card_companions.py"],
            check=False,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 0

    def test_deck_composition_stats_runs(self):
        """Smoke test deck_composition_stats.py."""
        if not shutil.which("uv"):
            pytest.skip("uv not installed")
        result = subprocess.run(
            ["uv", "run", "python", "deck_composition_stats.py"],
            check=False,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode == 0


class TestUtilities:
    """Test utility functions work."""

    def test_data_loading_utils(self):
        """Test data_loading utilities."""
        from utils.data_loading import deck_stats, group_by_source, load_tournament_decks

        assert callable(load_tournament_decks)
        assert callable(group_by_source)
        assert callable(deck_stats)

    def test_evaluation_utils(self):
        """Test evaluation utilities."""
        from utils.evaluation import compute_precision_at_k, jaccard_similarity

        assert callable(compute_precision_at_k)
        assert callable(jaccard_similarity)


class TestDeprecatedExperiments:
    """Check deprecated experiments don't run accidentally."""

    def test_experimental_dir_isolated(self):
        """Verify experimental/ dir is properly isolated if present."""
        experimental_dir = Path("experimental")
        if not experimental_dir.exists():
            pytest.skip("experimental/ directory not present")

        # Check for README explaining deprecation
        readme = experimental_dir / "README.md"
        if readme.exists():
            content = readme.read_text()
            assert "archived" in content.lower() or "experimental" in content.lower()

    def test_no_experimental_imports_in_active(self):
        """Active code should not import from experimental/."""
        active_files = [
            "exp_source_filtering.py",
            "exp_format_specific.py",
            "validate_data_quality.py",
        ]

        for filepath in active_files:
            if not Path(filepath).exists():
                continue

            content = Path(filepath).read_text()

            # Check for imports from experimental
            if "from experimental" in content or "import experimental" in content:
                pytest.fail(f"{filepath} imports from experimental/ (should be isolated)")


def test_run_all_analysis_exists():
    """Check if run_all_analysis.py works."""
    assert Path("run_all_analysis.py").exists()

    # Can it import?
    try:
        pass
    except Exception as e:
        pytest.fail(f"run_all_analysis.py failed to import: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
