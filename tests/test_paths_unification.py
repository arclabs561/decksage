#!/usr/bin/env python3
"""
Tests for path unification - ensure all code uses PATHS.
"""

import ast
from pathlib import Path

import pytest


def find_hardcoded_paths(file_path: Path) -> list[tuple[int, str]]:
    """Find hardcoded paths in Python file."""
    with open(file_path) as f:
        content = f.read()

    tree = ast.parse(content, filename=str(file_path))
    hardcoded = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(pattern in node.value for pattern in ["data/", "experiments/", "src/ml/"]):
                hardcoded.append((node.lineno, node.value))

    return hardcoded


def test_no_hardcoded_paths_in_critical_files():
    """Test that critical files don't use hardcoded paths."""
    critical_files = [
        Path("src/ml/scripts/evaluate_all_embeddings.py"),
    ]

    for file_path in critical_files:
        if not file_path.exists():
            continue

        hardcoded = find_hardcoded_paths(file_path)
        # Allow some hardcoded paths in help text, but not in code
        # Filter out help text strings
        code_hardcoded = [
            (line, path)
            for line, path in hardcoded
            if not any(keyword in path.lower() for keyword in ["default", "help", "example"])
        ]

        assert len(code_hardcoded) == 0, f"{file_path} has hardcoded paths: {code_hardcoded}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
