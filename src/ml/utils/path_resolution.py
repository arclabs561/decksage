"""Centralized path resolution with support for local, S3, and absolute paths."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from .paths import PATHS


def resolve_path(
    path: Path | str,
    base: Path | str | None = None,
    relative_to: Literal["project", "data", "embeddings", "experiments", "graphs"] | None = None,
) -> Path | str:
    """
    Resolve a path, handling local, S3, and absolute paths.

    Args:
        path: Path to resolve (can be relative, absolute, or S3)
        base: Base path for relative resolution
        relative_to: Resolve relative to a known location (project, data, embeddings, etc.)

    Returns:
        Resolved path (Path for local, str for S3)
    """
    path_str = str(path)

    # S3 paths: return as-is
    if path_str.startswith("s3://"):
        return path_str

    # Absolute paths: return as Path
    if Path(path_str).is_absolute():
        return Path(path_str)

    # Relative paths: resolve based on base or relative_to
    if relative_to:
        base_map = {
            "project": Path(__file__).parent.parent.parent.parent,  # Project root
            "data": PATHS.data,
            "embeddings": PATHS.embeddings,
            "experiments": PATHS.experiments,
            "graphs": PATHS.graphs,
        }
        if relative_to in base_map:
            base = base_map[relative_to]

    if base:
        base_path = Path(base)
        return base_path / path_str

    # Default: resolve relative to project root
    project_root = Path(__file__).parent.parent.parent.parent
    return project_root / path_str


def version_path(
    path: Path | str,
    version: str,
    keep_extension: bool = True,
) -> Path | str:
    """
    Version a path by inserting version tag before extension.

    Args:
        path: Original path
        version: Version tag (e.g., "2024-W52" or "v2024-12-31")
        keep_extension: If True, keeps original extension; if False, removes it

    Returns:
        Versioned path (same type as input: Path or str)
    """
    is_s3 = isinstance(path, str) and path.startswith("s3://")
    is_str = isinstance(path, str)

    if is_s3:
        # S3 path: handle as string
        path_str = path
        if "/" in path_str:
            # Extract bucket and key
            parts = path_str.replace("s3://", "").split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""

            # Version the key
            if "." in key and keep_extension:
                key_base, key_ext = key.rsplit(".", 1)
                versioned_key = f"{key_base}_v{version}.{key_ext}"
            else:
                versioned_key = f"{key}_v{version}"

            return f"s3://{bucket}/{versioned_key}"
        else:
            # Just bucket name, can't version
            return path_str
    else:
        # Local path: handle as Path
        path_obj = Path(path) if not isinstance(path, Path) else path

        if keep_extension and path_obj.suffix:
            # Insert version before extension
            versioned = path_obj.parent / f"{path_obj.stem}_v{version}{path_obj.suffix}"
        else:
            # Append version
            versioned = path_obj.parent / f"{path_obj.name}_v{version}"

        return versioned if not is_str else str(versioned)


def get_current_embedding(embedding_type: Literal["gnn", "cooccurrence", "instruction"]) -> Path:
    """
    Get the current (production) embedding path.

    Args:
        embedding_type: Type of embedding

    Returns:
        Path to current embedding
    """
    paths = {
        "gnn": PATHS.embeddings / "gnn_graphsage.json",
        "cooccurrence": PATHS.embeddings / "production.wv",
        "instruction": None,  # Instruction embeddings are loaded from model name
    }

    if embedding_type not in paths:
        raise ValueError(f"Unknown embedding type: {embedding_type}")

    if paths[embedding_type] is None:
        raise ValueError(f"Embedding type '{embedding_type}' doesn't have a file path")

    return paths[embedding_type]


def get_versioned_embedding(
    embedding_type: Literal["gnn", "cooccurrence"],
    version: str,
) -> Path:
    """
    Get a versioned embedding path.

    Args:
        embedding_type: Type of embedding
        version: Version tag

    Returns:
        Path to versioned embedding
    """
    current = get_current_embedding(embedding_type)
    return version_path(current, version)
