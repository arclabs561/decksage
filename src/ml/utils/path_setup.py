"""Shared utilities for setting up Python paths in scripts.

This module provides a consistent way to set up sys.path for scripts that need
to import from ml or src.ml modules. It handles both local execution and runctl
execution contexts.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def setup_project_paths() -> Path:
    """
    Set up sys.path to allow imports from ml or src.ml modules.

    Handles multiple execution contexts:
    - Local execution from project root
    - Local execution from scripts/ directory
    - runctl execution (runs from project root)
    - Installed package context (via DECKSAGE_ROOT env var)

    Returns:
        Path to project root
    """
    # Check for explicit project root override (for installed packages)
    env_root = os.getenv("DECKSAGE_ROOT")
    if env_root:
        project_root = Path(env_root)
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        src_dir = project_root / "src"
        if src_dir.exists() and str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        return project_root

    # Try to find project root by looking for markers
    script_path = Path(__file__).resolve()
    script_dir = script_path.parent

    # Start from script directory and walk up
    project_root = script_dir
    markers = [
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "Cargo.toml",
        ".git",
        "runctl.toml",
        ".runctl.toml",
    ]

    # Walk up to find project root (max 8 levels)
    for _ in range(8):
        if any((project_root / marker).exists() for marker in markers):
            break
        parent = project_root.parent
        if parent == project_root:  # Reached filesystem root
            break
        project_root = parent

    # If we didn't find markers, try using current working directory
    # (runctl runs from project root)
    if not any((project_root / m).exists() for m in markers):
        try:
            cwd = Path.cwd()
            if any((cwd / m).exists() for m in markers):
                project_root = cwd
        except Exception:
            pass

    # Verify project root by checking for src/ml structure
    if not (project_root / "src" / "ml").exists():
        # Try parent directory
        parent = project_root.parent
        if (parent / "src" / "ml").exists() and any((parent / m).exists() for m in markers):
            project_root = parent

    # Add project root to Python path
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Also add src directory if it exists (for ml imports)
    src_dir = project_root / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    # Debug logging if requested
    if os.getenv("DEBUG_PATHS"):
        print(f"DEBUG: script_path={script_path}", file=sys.stderr)
        print(f"DEBUG: project_root={project_root}", file=sys.stderr)
        print(f"DEBUG: sys.path={sys.path[:3]}", file=sys.stderr)

    return project_root


# Convenience function for scripts that just need path setup
def ensure_project_paths() -> None:
    """Ensure project paths are set up. Call this at the top of scripts."""
    setup_project_paths()
