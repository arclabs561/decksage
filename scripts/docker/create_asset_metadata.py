#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic>=2.0.0",
# ]
# ///
"""
Create metadata file for ML assets to track versions and training/eval info.

Usage:
    python scripts/docker/create_asset_metadata.py \
        --embeddings data/embeddings/model.wv \
        --pairs data/graphs/pairs.csv \
        --attributes data/attributes/card_attrs.csv \
        --output data/ASSET_METADATA.json
"""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = None
    Field = None


class AssetMetadata(BaseModel):
    """Metadata for ML assets."""

    embeddings: dict[str, Any] = Field(..., description="Embeddings metadata")
    graph: dict[str, Any] | None = Field(None, description="Graph data metadata")
    attributes: dict[str, Any] | None = Field(None, description="Card attributes metadata")
    signals: dict[str, Any] | None = Field(None, description="Additional signals metadata")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    version: str = Field(..., description="Asset version (e.g., v2026-W01)")


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_file_metadata(file_path: Path | str) -> dict[str, Any]:
    """Get metadata for a file."""
    path = Path(file_path)
    if not path.exists():
        return {"path": str(path), "exists": False}

    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "sha256": compute_file_hash(path),
    }


def extract_version_from_path(path: Path | str) -> str | None:
    """Extract version from path if present (e.g., model_v2026-W01.wv)."""
    path_str = str(path)
    # Look for version patterns: _v2026-W01, _v2026-01-01, etc.
    import re

    match = re.search(r"_v(\d{4}-[W]?\d{2,3})", path_str)
    if match:
        return f"v{match.group(1)}"
    return None


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Create ML asset metadata")
    parser.add_argument("--embeddings", required=True, help="Path to embeddings file")
    parser.add_argument("--pairs", help="Path to pairs/graph CSV")
    parser.add_argument("--attributes", help="Path to attributes CSV")
    parser.add_argument("--signals-dir", help="Directory containing signal files")
    parser.add_argument("--version", help="Version tag (auto-detected if not provided)")
    parser.add_argument("--output", default="data/ASSET_METADATA.json", help="Output metadata file")
    parser.add_argument(
        "--training-run",
        help="Training run ID or path to training metadata",
    )
    parser.add_argument(
        "--eval-results",
        help="Path to evaluation results JSON",
    )

    args = parser.parse_args()

    # Determine version
    version = args.version
    if not version:
        # Try to extract from embeddings path
        version = extract_version_from_path(args.embeddings)
        if not version:
            # Auto-generate from current date
            version = datetime.now().strftime("v%Y-W%V")

    # Get embeddings metadata
    embeddings_meta = get_file_metadata(args.embeddings)
    embeddings_meta["version"] = version

    # Get graph metadata
    graph_meta = None
    if args.pairs:
        graph_meta = get_file_metadata(args.pairs)

    # Get attributes metadata
    attributes_meta = None
    if args.attributes:
        attributes_meta = get_file_metadata(args.attributes)

    # Get signals metadata
    signals_meta = None
    if args.signals_dir:
        signals_dir = Path(args.signals_dir)
        if signals_dir.exists():
            signals_meta = {}
            for signal_file in ["sideboard.json", "temporal.json", "gnn_graphsage.json"]:
                signal_path = signals_dir / signal_file
                if signal_path.exists():
                    signals_meta[signal_file] = get_file_metadata(signal_path)

    # Load training run metadata if provided
    training_metadata = None
    if args.training_run:
        training_path = Path(args.training_run)
        if training_path.exists():
            try:
                with open(training_path) as f:
                    training_metadata = json.load(f)
            except Exception as e:
                print(f"Warning: Could not load training metadata: {e}")

    # Load eval results if provided
    eval_metadata = None
    if args.eval_results:
        eval_path = Path(args.eval_results)
        if eval_path.exists():
            try:
                with open(eval_path) as f:
                    eval_data = json.load(f)
                    # Extract key metrics
                    eval_metadata = {
                        "path": str(eval_path),
                        "p_at_10": eval_data.get("metrics", {}).get("p_at_10"),
                        "mrr": eval_data.get("metrics", {}).get("mrr"),
                        "timestamp": eval_data.get("timestamp"),
                    }
            except Exception as e:
                print(f"Warning: Could not load eval results: {e}")

    # Build metadata
    metadata = {
        "version": version,
        "created_at": datetime.now().isoformat(),
        "embeddings": embeddings_meta,
        "graph": graph_meta,
        "attributes": attributes_meta,
        "signals": signals_meta,
        "training": training_metadata,
        "evaluation": eval_metadata,
    }

    # Validate with Pydantic if available
    if BaseModel is not None:
        try:
            validated = AssetMetadata(**metadata)
            metadata = validated.model_dump()
        except Exception as e:
            print(f"Warning: Pydantic validation failed: {e}")

    # Write metadata
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"✓ Created asset metadata: {output_path}")
    print(f"  Version: {version}")
    print(f"  Embeddings: {embeddings_meta.get('size_mb', 0)} MB")
    if graph_meta:
        print(f"  Graph: {graph_meta.get('size_mb', 0)} MB")
    if attributes_meta:
        print(f"  Attributes: {attributes_meta.get('size_mb', 0)} MB")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())

