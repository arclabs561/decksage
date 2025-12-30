#!/usr/bin/env python3
"""
Organize S3 assets with proper structure and README files.

Creates:
- README.md files for each top-level directory
- Index of all assets
- Proper organization structure
"""

# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "boto3>=1.34.0",
# ]
# ///

import json
from datetime import datetime, timezone
from typing import Any

import boto3

S3_BUCKET = "games-collections"


def create_directory_readme(
    path: str,
    description: str,
    contents: list[dict[str, Any]],
    usage: dict[str, str] | None = None,
) -> str:
    """Create a README.md for an S3 directory."""
    lines = [
        f"# {path}",
        "",
        description,
        "",
        "## Contents",
        "",
    ]

    if contents:
        lines.append("| Name | Size | Last Modified | Description |")
        lines.append("|------|------|----------------|-------------|")
        for item in contents:
            name = item.get("name", "")
            size = item.get("size", "")
            modified = item.get("modified", "")
            desc = item.get("description", "")
            lines.append(f"| {name} | {size} | {modified} | {desc} |")
    else:
        lines.append("(No contents listed)")

    if usage:
        lines.extend(["", "## Usage", ""])
        for key, value in usage.items():
            lines.append(f"### {key}")
            lines.append(f"```bash")
            lines.append(value)
            lines.append("```")
            lines.append("")

    lines.extend([
        "",
        "---",
        f"*Last updated: {datetime.now(timezone.utc).isoformat()}*",
    ])

    return "\n".join(lines)


def list_s3_objects(s3_client: Any, prefix: str) -> list[dict[str, Any]]:
    """List objects in S3 with metadata."""
    objects = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        if "Contents" in page:
            for obj in page["Contents"]:
                objects.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "modified": obj["LastModified"].isoformat(),
                })
    return objects


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def main() -> None:
    """Organize S3 assets and create README files."""
    s3_client = boto3.client("s3")

    # Embeddings directory
    emb_objects = list_s3_objects(s3_client, "embeddings/")
    emb_contents = [
        {
            "name": obj["key"].split("/")[-1],
            "size": format_size(obj["size"]),
            "modified": obj["modified"][:10],
            "description": "Graph embedding model (KeyedVectors format)",
        }
        for obj in emb_objects
        if not obj["key"].endswith("/")
    ]

    emb_readme = create_directory_readme(
        "embeddings/",
        "Graph embedding models for card similarity. Trained using Node2Vec, DeepWalk, and variants.",
        emb_contents,
        {
            "Download": "aws s3 cp s3://games-collections/embeddings/{name}.wv .",
            "List all": "aws s3 ls s3://games-collections/embeddings/",
            "Load in Python": "from gensim.models import KeyedVectors; model = KeyedVectors.load('{name}.wv')",
        },
    )

    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key="embeddings/README.md",
        Body=emb_readme.encode("utf-8"),
        ContentType="text/markdown",
    )
    print("✓ Created embeddings/README.md")

    # Processed directory
    proc_objects = list_s3_objects(s3_client, "processed/")
    proc_contents = [
        {
            "name": obj["key"].split("/")[-1],
            "size": format_size(obj["size"]),
            "modified": obj["modified"][:10],
            "description": "Processed deck data for training",
        }
        for obj in proc_objects
        if not obj["key"].endswith("/")
    ]

    proc_readme = create_directory_readme(
        "processed/",
        "Processed deck data used for training embeddings and computing signals.",
        proc_contents,
        {
            "Download": "aws s3 cp s3://games-collections/processed/{name} .",
            "List all": "aws s3 ls s3://games-collections/processed/",
        },
    )

    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key="processed/README.md",
        Body=proc_readme.encode("utf-8"),
        ContentType="text/markdown",
    )
    print("✓ Created processed/README.md")

    # Scripts directory
    script_objects = list_s3_objects(s3_client, "scripts/")
    script_contents = [
        {
            "name": obj["key"].split("/")[-1],
            "size": format_size(obj["size"]),
            "modified": obj["modified"][:10],
            "description": "Training or utility script",
        }
        for obj in script_objects
        if not obj["key"].endswith("/")
    ]

    script_readme = create_directory_readme(
        "scripts/",
        "Utility scripts for training and data processing, designed to run on EC2 instances.",
        script_contents,
        {
            "Download": "aws s3 cp s3://games-collections/scripts/{name} .",
            "List all": "aws s3 ls s3://games-collections/scripts/",
        },
    )

    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key="scripts/README.md",
        Body=script_readme.encode("utf-8"),
        ContentType="text/markdown",
    )
    print("✓ Created scripts/README.md")

    # Root README
    root_readme = f"""# DeckSage S3 Assets

This bucket contains all ML artifacts, training data, and scripts for the DeckSage project.

## Directory Structure

- **embeddings/**: Graph embedding models (Node2Vec, DeepWalk variants)
- **processed/**: Processed deck data for training
- **scripts/**: Training and utility scripts
- **games/**: Raw game data (scraped collections)
- **scraper/**: Scraped API responses
- **model-cards/**: Model cards documenting all ML artifacts

## Quick Start

### Download Embeddings
```bash
aws s3 cp s3://games-collections/embeddings/magic_128d_test_pecanpy.wv .
```

### Download Processed Data
```bash
aws s3 cp s3://games-collections/processed/pairs_large.csv .
```

### List All Assets
```bash
aws s3 ls s3://games-collections/ --recursive
```

## Model Cards

All ML artifacts have corresponding model cards in `model-cards/`:
- `model-cards/embeddings/`: Embedding model documentation
- `model-cards/signals/`: Similarity signal documentation

See `model-cards/README.json` for the full index.

## Organization Principles

1. **Versioning**: Major versions in filenames (e.g., `magic_128d_test_pecanpy.wv`)
2. **Documentation**: Every directory has a README.md
3. **Model Cards**: All ML artifacts have JSON model cards
4. **Consistency**: Consistent naming and structure across all assets

---
*Last updated: {datetime.utcnow().isoformat()}Z*
"""

    s3_client.put_object(
        Bucket=S3_BUCKET,
        Key="README.md",
        Body=root_readme.encode("utf-8"),
        ContentType="text/markdown",
    )
    print("✓ Created root README.md")

    print("\n✓ S3 assets organized")


if __name__ == "__main__":
    main()

