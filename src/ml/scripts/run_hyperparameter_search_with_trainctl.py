#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Run hyperparameter search using runctl.

This script orchestrates hyperparameter search on AWS using runctl
instead of custom AWS scripts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Run hyperparameter search with runctl."""
    runctl_path = Path("../runctl/target/release/runctl")
    
    if not runctl_path.exists():
        print("❌ runctl not found. Build it first:")
        print("   cd ../runctl && cargo build --release")
        return 1
    
    print("🚀 Running hyperparameter search with runctl")
    print("=" * 70)
    
    # Create AWS instance
    print("\n1. Creating AWS EC2 instance (spot, g4dn.xlarge)...")
        create_cmd = [
            str(runctl_path),
            "aws", "create",
            "--spot",
            "--instance-type", "g4dn.xlarge",
        ]
    
    try:
        result = subprocess.run(
            create_cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        instance_output = result.stdout
        print(f"   Output: {instance_output}")
        
        # Extract instance ID
        import re
        instance_match = re.search(r'i-[a-z0-9]+', instance_output)
        if not instance_match:
            print("❌ Could not extract instance ID from output")
            return 1
        
        instance_id = instance_match.group(0)
        print(f"✅ Instance created: {instance_id}")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create instance: {e}")
        print(f"   stderr: {e.stderr}")
        return 1
    
    # Train with hyperparameter search
    print(f"\n2. Running hyperparameter search on {instance_id}...")
    train_cmd = [
        str(runctl_path),
        "aws", "train", instance_id,
        "src/ml/scripts/improve_embeddings_hyperparameter_search.py",
        "--input", "s3://games-collections/processed/pairs_large.csv",
        "--test-set", "s3://games-collections/processed/test_set_canonical_magic.json",
        "--output", "s3://games-collections/experiments/hyperparameter_results.json",
    ]
    
    try:
        subprocess.run(train_cmd, check=True)
        print("✅ Training started")
    except subprocess.CalledProcessError as e:
        print(f"❌ Training failed: {e}")
        return 1
    
    # Monitor
    print(f"\n3. Monitoring training on {instance_id}...")
    print("   (Press Ctrl+C to stop monitoring, instance will continue)")
    monitor_cmd = [
        str(runctl_path),
        "aws", "monitor", instance_id,
        "--follow",
    ]
    
    try:
        subprocess.run(monitor_cmd)
    except KeyboardInterrupt:
        print("\n⏸️  Monitoring stopped (training continues)")
    
    print(f"\n✅ Hyperparameter search complete!")
    print(f"   Results: s3://games-collections/experiments/hyperparameter_results.json")
    print(f"   Instance: {instance_id} (terminate manually if needed)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
