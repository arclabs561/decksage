#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas>=2.0.0",
#     "numpy<2.0.0",
#     "pecanpy>=2.0.0",
#     "gensim>=4.3.0",
# ]
# ///
"""
Train all embedding methods and upload to S3.

Uses PEP 723 inline dependencies.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> tuple[bool, str]:
    """Run a command."""
    print(f"\n{'='*70}")
    print(f"{description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*70}\n")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        
        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr or result.stdout
    except Exception as e:
        return False, str(e)


def upload_to_s3(local_path: Path, s3_path: str, description: str = "") -> bool:
    """Upload file to S3."""
    if not local_path.exists():
        print(f"  ❌ File not found: {local_path}")
        return False
    
    success, output = run_command(
        ["aws", "s3", "cp", str(local_path), s3_path],
        f"Uploading {description or local_path.name} to S3",
    )
    
    return success


def main() -> int:
    """Train all embeddings and upload to S3."""
    parser = argparse.ArgumentParser(description="Train all embeddings and upload to S3")
    parser.add_argument(
        "--input",
        type=str,
        default="data/processed/pairs_large.csv",
        help="Input pairs CSV",
    )
    parser.add_argument(
        "--bucket",
        type=str,
        default="games-collections",
        help="S3 bucket name",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload to S3 after training",
    )
    parser.add_argument(
        "--dim",
        type=int,
        default=128,
        help="Embedding dimension",
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Train All Embedding Methods")
    print("=" * 70)
    print()
    
    # Train all methods
    methods = ["deepwalk", "node2vec", "node2vec_bfs", "node2vec_dfs"]
    
    cmd = [
        "uv", "run", "--script", "src/ml/scripts/compare_embedding_methods.py",
        "--input", args.input,
        "--methods"] + methods + [
        "--dim", str(args.dim),
        "--output-dir", "data/embeddings",
    ]
    
    success, output = run_command(cmd, "Training all embedding methods")
    
    if not success:
        print(f"❌ Training failed: {output[:500]}")
        return 1
    
    print("✅ Training complete!")
    
    # Upload to S3
    if args.upload:
        print("\nUploading to S3...")
        embeddings_dir = Path("data/embeddings")
        
        for method in methods:
            if method == "node2vec":
                filename = "node2vec_default.wv"
            else:
                filename = f"{method}.wv"
            
            local_file = embeddings_dir / filename
            if local_file.exists():
                s3_path = f"s3://{args.bucket}/embeddings/{filename}"
                upload_to_s3(local_file, s3_path, method)
    
    print()
    print("=" * 70)
    print("✅ Complete!")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

