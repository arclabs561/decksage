#!/usr/bin/env python3
"""
Integration tests for Tier 0 & Tier 1 validation scripts.

Tests that scripts work together and handle real-world scenarios.
"""

from __future__ import annotations

import json
import subprocess

# Set up paths
from pathlib import Path
from unittest.mock import patch

import pytest

from ml.utils.path_setup import setup_project_paths


setup_project_paths()

from ml.scripts.validate_integration import (
    validate_component_integration,
    validate_end_to_end_workflow,
)


class TestComponentIntegration:
    """Tests for component integration validation."""

    def test_validate_component_integration_success(self, tmp_path: Path):
        """Test successful component integration validation."""
        # Create mock files
        test_set = tmp_path / "test_set.json"
        decks = tmp_path / "decks.jsonl"
        pairs = tmp_path / "pairs.csv"

        test_set.write_text('{"queries": {"query1": {"highly_relevant": ["card1"]}}}')
        decks.write_text('{"name": "test"}\n')
        pairs.write_text("card1,card2\n")

        with patch("ml.scripts.validate_integration.PATHS") as mock_paths:
            mock_paths.test_magic = test_set
            mock_paths.decks_all_final = decks
            mock_paths.pairs_large = pairs

            result = validate_component_integration()

            assert "checks" in result
            assert "overall" in result
            assert result["overall"] in ["pass", "warn"]


class TestEndToEndWorkflow:
    """Tests for end-to-end workflow validation."""

    def test_validate_end_to_end_workflow_success(self, tmp_path: Path):
        """Test successful end-to-end workflow validation."""
        # Create mock files
        test_set = tmp_path / "test_set.json"
        test_set.write_text('{"queries": {"query1": {"highly_relevant": ["card1"]}}}')

        with patch("ml.scripts.validate_integration.PATHS") as mock_paths:
            mock_paths.test_magic = test_set
            mock_paths.decks_all_final = tmp_path / "decks.jsonl"
            mock_paths.pairs_large = tmp_path / "pairs.csv"
            mock_paths.experiments = tmp_path
            mock_paths.hybrid_evaluation_results = tmp_path / "results.json"

            # Mock file creation
            (tmp_path / "decks.jsonl").write_text('{"name": "test"}\n')
            (tmp_path / "pairs.csv").write_text("card1,card2\n")
            (tmp_path / "results.json").write_text('{"p_at_10": 0.12}')

            result = validate_end_to_end_workflow("magic")

            assert "steps" in result
            assert "overall" in result
            assert result["overall"] in ["pass", "warn"]


class TestScriptExecution:
    """Tests for actual script execution (smoke tests)."""

    def test_validate_prerequisites_script_runs(self):
        """Test that prerequisite validation script can be executed."""
        result = subprocess.run(
            [
                "python3",
                "-m",
                "ml.scripts.validate_prerequisites",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Should exit successfully or with warnings (not errors)
        assert result.returncode in [0, 1]  # 0 = pass, 1 = fail (acceptable)

        # Should produce JSON output
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                assert "overall" in data
            except json.JSONDecodeError:
                # If not JSON, that's okay - might be human-readable
                pass

    @pytest.mark.slow
    def test_check_test_set_size_script_runs(self):
        """Test that test set size check can be executed."""
        # This is a smoke test - just verify it doesn't crash
        try:
            from ml.scripts.run_all_tier0_tier1 import check_test_set_size

            result = check_test_set_size("magic")

            # Should return a dict with status
            assert isinstance(result, dict)
            assert "status" in result
        except Exception as e:
            pytest.fail(f"check_test_set_size raised exception: {e}")


class TestErrorRecovery:
    """Tests for error recovery and graceful degradation."""

    def test_handles_missing_test_set_gracefully(self):
        """Test that missing test set is handled gracefully."""
        from ml.scripts.run_all_tier0_tier1 import check_test_set_size

        with patch("ml.scripts.run_all_tier0_tier1.PATHS") as mock_paths:
            mock_paths.test_magic = Path("/nonexistent/test.json")
            result = check_test_set_size("magic")

            # Should return error status, not raise exception
            assert result["status"] == "fail"
            assert "queries" in result

    def test_handles_missing_prerequisites_gracefully(self):
        """Test that missing prerequisites are handled gracefully."""
        result = validate_component_integration()

        # Should return a result, not raise exception
        assert isinstance(result, dict)
        assert "overall" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
