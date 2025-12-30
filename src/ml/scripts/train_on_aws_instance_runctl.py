#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Train embeddings on AWS using runctl (replaces train_on_aws_instance.py).

This is a drop-in replacement that uses runctl instead of direct SSM calls.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def find_runctl() -> Path | None:
    """Find runctl binary."""
    project_root = Path(__file__).parent.parent.parent.parent
    runctl_path = project_root.parent / "runctl" / "target" / "release" / "runctl"
    
    if runctl_path.exists():
        return runctl_path
    
    return None


def main() -> int:
    """Train embeddings on AWS using runctl."""
    parser = argparse.ArgumentParser(
        description="Train embeddings on AWS EC2 using runctl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--pairs-s3",
        type=str,
        default="s3://games-collections/processed/pairs_large.csv",
        help="S3 path to pairs CSV",
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="magic_128d",
        help="Output name for embeddings",
    )
    
    parser.add_argument(
        "--dim",
        type=int,
        default=128,
        help="Embedding dimension",
    )
    
    parser.add_argument(
        "--instance-id",
        type=str,
        default=None,
        help="Existing instance ID (or create new if not provided)",
    )
    
    parser.add_argument(
        "--instance-type",
        type=str,
        default="g4dn.xlarge",
        help="Instance type for new instances",
    )
    
    parser.add_argument(
        "--no-spot",
        action="store_true",
        help="Don't use spot instances",
    )
    
    parser.add_argument(
        "--terminate",
        action="store_true",
        help="Terminate instance after training",
    )
    
    args = parser.parse_args()
    
    runctl_path = find_runctl()
    if not runctl_path:
        print("❌ runctl not found. Build it first:")
        print("   cd ../runctl && cargo build --release")
        return 1
    
    # Create instance if needed
    instance_id = args.instance_id
    if not instance_id:
        print(f"Creating AWS instance ({args.instance_type}, spot={not args.no_spot})...")
        create_cmd = [
            str(runctl_path),
            "aws", "create",
            "--spot" if not args.no_spot else "",
            args.instance_type,
        ]
        create_cmd = [c for c in create_cmd if c]
        
        try:
            result = subprocess.run(
                create_cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            import re
            instance_match = re.search(r'i-[a-z0-9]+', result.stdout)
            if instance_match:
                instance_id = instance_match.group(0)
                print(f"✅ Instance created: {instance_id}")
            else:
                print(f"❌ Could not extract instance ID")
                return 1
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create instance: {e.stderr}")
            return 1
    
    # Use the unified training script with runctl
    # We'll use improve_training_with_validation_enhanced.py which handles S3 paths
    print(f"🚀 Training embeddings on {instance_id}...")
    
    train_cmd = [
        str(runctl_path),
        "aws", "train",
        instance_id,
        "src/ml/scripts/improve_training_with_validation_enhanced.py",
        "--output-s3", "s3://games-collections/embeddings/",
        "--",
        "--input", args.pairs_s3,
        "--output", f"s3://games-collections/embeddings/{args.output}.wv",
        "--dim", str(args.dim),
    ]
    
    try:
        subprocess.run(train_cmd, check=True)
        print("✅ Training complete!")
        
        # Download results
        print(f"\nDownloading embeddings from S3...")
        local_path = Path(f"data/embeddings/{args.output}.wv")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        download_cmd = [
            "aws", "s3", "cp",
            f"s3://games-collections/embeddings/{args.output}.wv",
            str(local_path),
        ]
        
        result = subprocess.run(download_cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Downloaded to {local_path}")
        else:
            print(f"⚠️  Download failed: {result.stderr}")
        
        # Terminate if requested
        if args.terminate:
            print("\nTerminating instance...")
            # runctl doesn't have terminate yet, use AWS CLI
            subprocess.run(
                ["aws", "ec2", "terminate-instances", "--instance-ids", instance_id],
                check=False,
            )
            print("✅ Instance termination requested")
        
        return 0
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Training failed: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n⏸️  Interrupted (training may continue on instance)")
        return 130


if __name__ == "__main__":
    sys.exit(main())

