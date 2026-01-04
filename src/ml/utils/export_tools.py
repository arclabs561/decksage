"""
Utilities for building and locating export tools.

Provides consistent paths and build logic for Go export tools.
"""

import subprocess
import tempfile
from pathlib import Path


# Consistent temp directory for export binaries
TEMP_DIR = Path(tempfile.gettempdir()) / "decksage"
TEMP_DIR.mkdir(exist_ok=True)


def build_export_tool(
    tool_name: str,
    go_source: Path,
    backend_dir: Path | None = None,
) -> Path:
    """
    Build Go export tool and return path to binary.

    Args:
        tool_name: Name of tool (e.g., "export-hetero", "export-multi-game-graph")
        go_source: Path to main.go file
        backend_dir: Backend directory (default: src/backend)

    Returns:
        Path to built binary

    Raises:
        RuntimeError: If build fails
    """
    if backend_dir is None:
        backend_dir = Path("src/backend")

    if not go_source.exists():
        raise FileNotFoundError(f"Go source not found: {go_source}")

    # Determine package path from source path
    # e.g., src/backend/cmd/export-hetero/main.go -> ./cmd/export-hetero
    rel_path = go_source.relative_to(backend_dir)
    package_path = "./" + str(rel_path.parent)

    # Output binary path
    binary_path = TEMP_DIR / tool_name

    # Build
    result = subprocess.run(
        ["go", "build", "-o", str(binary_path), package_path],
        cwd=backend_dir.absolute(),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to build {tool_name}: {result.stderr}\n"
            f"Command: go build -o {binary_path} {package_path}\n"
            f"Working directory: {backend_dir}"
        )

    return binary_path


def get_export_binary(tool_name: str) -> Path | None:
    """
    Get path to export binary if it exists.

    Args:
        tool_name: Name of tool

    Returns:
        Path to binary if exists, None otherwise
    """
    binary_path = TEMP_DIR / tool_name
    if binary_path.exists():
        return binary_path
    return None
