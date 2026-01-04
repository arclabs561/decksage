#!/usr/bin/env python3
"""
Tests for data integrity validation and fixes.
"""

import json
import pytest
from pathlib import Path
from scripts.deep_analysis.check_data_integrity import check_test_set_integrity
from scripts.deep_analysis.fix_data_integrity_issues import fix_test_set_integrity


def test_test_set_integrity_check():
    """Test that integrity checker works."""
    test_set = Path("experiments/test_set_canonical_magic_improved_fixed.json")
    if not test_set.exists():
        pytest.skip("Test set not found")
    
    result = check_test_set_integrity(test_set)
    assert result["valid"], "Fixed test set should have no integrity issues"


def test_fix_data_integrity():
    """Test that integrity fixer works."""
    # Create a test case with integrity issues
    test_data = {
        "queries": {
            "Lightning Bolt": {
                "highly_relevant": ["Shock", "Bolt"],
                "relevant": ["Bolt"],  # Duplicate
                "somewhat_relevant": ["Shock"],  # Duplicate
            }
        }
    }
    
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_data, f)
        temp_path = Path(f.name)
    
    try:
        result = fix_test_set_integrity(temp_path)
        assert result["success"], "Fix should succeed"
        assert result["stats"]["cards_fixed"] > 0, "Should fix duplicate cards"
    finally:
        temp_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

