#!/usr/bin/env python3
"""
Run improved training with validation on AWS EC2.

⚠️  DEPRECATED: Use train_with_runctl.py instead!
This script uses direct SSM calls. The runctl version provides:
- Unified instance management
- Automatic SSM/SSH handling
- Better S3 integration

Uses the improved training script with validation and early stopping.
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "boto3>=1.34.0",
# ]
# ///

import json
import sys
import time
from pathlib import Path

try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    print("❌ boto3 not available", file=sys.stderr)


def upload_file_to_s3(local_path: Path, s3_key: str, bucket: str = "games-collections") -> bool:
    """Upload file to S3."""
    s3 = boto3.client("s3")
    try:
        s3.upload_file(str(local_path), bucket, s3_key)
        print(f"✅ Uploaded {local_path.name} to s3://{bucket}/{s3_key}")
        return True
    except Exception as e:
        print(f"❌ Failed to upload {local_path.name}: {e}", file=sys.stderr)
        return False


def create_ec2_instance(
    instance_type: str = "t3.medium",
    use_spot: bool = True,
    spot_max_price: str | None = "0.10",
    fallback_to_ondemand: bool = True,
) -> str | None:
    """Create EC2 instance for computation."""
    ec2 = boto3.client("ec2")
    ami_id = "ami-08fa3ed5577079e64"
    
    user_data = """#!/bin/bash
yum update -y
yum install -y python3 python3-pip git
python3 -m pip install --upgrade pip || pip3 install --upgrade pip || true
python3 -m pip install pandas numpy gensim boto3 pecanpy || pip3 install pandas numpy gensim boto3 pecanpy || true
"""
    
    launch_spec = {
        "ImageId": ami_id,
        "InstanceType": instance_type,
        "MinCount": 1,
        "MaxCount": 1,
        "UserData": user_data,
        "IamInstanceProfile": {"Name": "EC2-SSM-InstanceProfile"},
    }
    
    if use_spot and spot_max_price:
        launch_spec["InstanceMarketOptions"] = {
            "MarketType": "spot",
            "SpotOptions": {
                "MaxPrice": spot_max_price,
                "SpotInstanceType": "one-time",
                "InstanceInterruptionBehavior": "terminate",
            },
        }
    
    try:
        if use_spot:
            print(f"Creating spot instance ({instance_type}, max ${spot_max_price or 'on-demand'}/hr)...")
            response = ec2.run_instances(**launch_spec)
        else:
            print(f"Creating on-demand instance ({instance_type})...")
            response = ec2.run_instances(**launch_spec)
        
        instance_id = response["Instances"][0]["InstanceId"]
        print(f"✅ Created instance: {instance_id}")
        return instance_id
        
    except Exception as e:
        if use_spot and fallback_to_ondemand:
            print(f"⚠️  Spot instance failed: {e}")
            print("Falling back to on-demand...")
            launch_spec.pop("InstanceMarketOptions", None)
            try:
                response = ec2.run_instances(**launch_spec)
                instance_id = response["Instances"][0]["InstanceId"]
                print(f"✅ Created on-demand instance: {instance_id}")
                return instance_id
            except Exception as e2:
                print(f"❌ On-demand instance also failed: {e2}", file=sys.stderr)
                return None
        else:
            print(f"❌ Failed to create instance: {e}", file=sys.stderr)
            return None


def wait_for_ssm_ready(instance_id: str, timeout: int = 300) -> bool:
    """Wait for SSM to be ready on instance."""
    ssm = boto3.client("ssm")
    print(f"Waiting for SSM to be ready on {instance_id}...")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = ssm.describe_instance_information(
                Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
            )
            if response.get("InstanceInformationList"):
                print("✅ SSM is ready")
                return True
        except Exception:
            pass
        
        time.sleep(5)
        print(".", end="", flush=True)
    
    print(f"\n⚠️  SSM timeout")
    return False


def run_command_on_instance(instance_id: str, command: str, timeout: int = 7200) -> tuple[int, str, str]:
    """Run command on EC2 instance via SSM."""
    ssm = boto3.client("ssm")
    
    print(f"Running command on {instance_id}...")
    
    try:
        commands = [cmd.strip() for cmd in command.strip().split("\n") if cmd.strip()]
        
        response = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": commands},
            TimeoutSeconds=timeout,
        )
        
        command_id = response["Command"]["CommandId"]
        print(f"  Command ID: {command_id}")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                result = ssm.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id,
                )
                
                status = result["Status"]
                if status in ["Success", "Failed", "Cancelled", "TimedOut"]:
                    stdout = result.get("StandardOutputContent", "")
                    stderr = result.get("StandardErrorContent", "")
                    return (
                        0 if status == "Success" else 1,
                        stdout,
                        stderr,
                    )
            except ssm.exceptions.InvocationDoesNotExist:
                time.sleep(2)
                continue
            
            time.sleep(10)
            print(".", end="", flush=True)
        
        return 1, "", f"Command timed out after {timeout}s"
            
    except Exception as e:
        return 1, "", str(e)


def download_from_s3(s3_key: str, local_path: Path, bucket: str = "games-collections") -> bool:
    """Download file from S3."""
    s3 = boto3.client("s3")
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, s3_key, str(local_path))
        print(f"✅ Downloaded {s3_key} to {local_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to download: {e}", file=sys.stderr)
        return False


def terminate_instance(instance_id: str) -> None:
    """Terminate EC2 instance."""
    ec2 = boto3.client("ec2")
    try:
        ec2.terminate_instances(InstanceIds=[instance_id])
        print(f"✅ Terminated instance {instance_id}")
    except Exception as e:
        print(f"⚠️  Could not terminate instance: {e}")


def main() -> int:
    """Run improved training on AWS EC2."""
    if not HAS_BOTO3:
        print("❌ boto3 not available", file=sys.stderr)
        return 1
    
    import argparse
    
    parser = argparse.ArgumentParser(description="Run improved training on AWS EC2")
    parser.add_argument("--edgelist", type=str, help="Edgelist file (default: use enriched)")
    parser.add_argument("--test-set", type=str, default="experiments/test_set_expanded_magic.json", help="Test set")
    parser.add_argument("--name-mapping", type=str, help="Name mapping JSON")
    parser.add_argument("--output", type=str, default="data/embeddings/magic_improved.wv", help="Output embeddings")
    parser.add_argument("--p", type=float, default=1.0, help="Return parameter")
    parser.add_argument("--q", type=float, default=1.0, help="In-out parameter")
    parser.add_argument("--dim", type=int, default=128, help="Embedding dimension")
    parser.add_argument("--walk-length", type=int, default=80, help="Walk length")
    parser.add_argument("--num-walks", type=int, default=10, help="Number of walks")
    parser.add_argument("--epochs", type=int, default=10, help="Max epochs")
    parser.add_argument("--patience", type=int, default=3, help="Early stopping patience")
    
    args = parser.parse_args()
    
    bucket = "games-collections"
    
    # Determine edgelist
    if args.edgelist:
        edgelist_path = Path(args.edgelist)
    else:
        edgelist_path = Path("data/graphs/pairs_enriched.edg")
        if not edgelist_path.exists():
            edgelist_path = Path("data/graphs/pairs_enriched_with_attrs.edg")
    
    # Upload training script
    script_path = Path("src/ml/scripts/improve_training_with_validation.py")
    s3_script_key = "scripts/improve_training_with_validation.py"
    
    print("=" * 70)
    print("Step 1: Upload training script to S3")
    print("=" * 70)
    if not upload_file_to_s3(script_path, s3_script_key, bucket):
        return 1
    
    # Upload test set and name mapping
    if Path(args.test_set).exists():
        upload_file_to_s3(Path(args.test_set), f"processed/{Path(args.test_set).name}", bucket)
    
    if args.name_mapping and Path(args.name_mapping).exists():
        upload_file_to_s3(Path(args.name_mapping), f"processed/{Path(args.name_mapping).name}", bucket)
    
    # Create EC2 instance
    print("\n" + "=" * 70)
    print("Step 2: Create EC2 instance")
    print("=" * 70)
    
    instance_id = create_ec2_instance(
        instance_type="t3.medium",
        use_spot=True,
        spot_max_price="0.10",
        fallback_to_ondemand=True,
    )
    
    if not instance_id:
        return 1
    
    # Wait for SSM
    if not wait_for_ssm_ready(instance_id):
        print("⚠️  Continuing anyway...")
    
    # Wait for Python
    print("\n" + "=" * 70)
    print("Step 3: Wait for Python installation")
    print("=" * 70)
    wait_cmd = "while ! command -v python3 &> /dev/null; do sleep 5; done && echo 'Python ready'"
    exit_code, stdout, stderr = run_command_on_instance(instance_id, wait_cmd, timeout=300)
    if exit_code == 0:
        print("✅ Python is ready")
    
    # Install dependencies
    print("\n" + "=" * 70)
    print("Step 4: Install dependencies")
    print("=" * 70)
    install_cmd = "python3 -m pip install pandas numpy gensim boto3 pecanpy 2>&1"
    exit_code, stdout, stderr = run_command_on_instance(instance_id, install_cmd, timeout=600)
    print(stdout[-500:] if len(stdout) > 500 else stdout)
    
    # Download script and data
    print("\n" + "=" * 70)
    print("Step 5: Download script and data")
    print("=" * 70)
    
    download_script = f"""python3 -c "import boto3, os; s3=boto3.client('s3'); os.makedirs('/tmp/training', exist_ok=True); [s3.download_file('{bucket}', k, p) or print(f'✅ {{k}}') if True else None for k,p in [('{s3_script_key}', '/tmp/training/train.py'), ('processed/{Path(args.test_set).name}', '/tmp/training/test_set.json'), ('processed/{Path(args.name_mapping).name if args.name_mapping else 'name_mapping.json'}', '/tmp/training/name_mapping.json')] if Path(k).exists() or k.startswith('processed/')]; print('Download complete')"
"""
    
    # Use edgelist from S3 or upload it
    if not str(edgelist_path).startswith("s3://"):
        # Upload edgelist
        s3_edgelist_key = f"graphs/{edgelist_path.name}"
        upload_file_to_s3(edgelist_path, s3_edgelist_key, bucket)
        edgelist_s3 = s3_edgelist_key
    else:
        edgelist_s3 = edgelist_path.replace("s3://games-collections/", "")
    
    # Run training
    print("\n" + "=" * 70)
    print("Step 6: Run improved training")
    print("=" * 70)
    print("⏳ Training with validation and early stopping...")
    
    run_cmd = f"""
cd /tmp/training
python3 train.py \
  --input /tmp/training/edgelist.edg \
  --output /tmp/training/embeddings.wv \
  --test-set test_set.json \
  --name-mapping name_mapping.json \
  --p {args.p} \
  --q {args.q} \
  --dim {args.dim} \
  --walk-length {args.walk_length} \
  --num-walks {args.num_walks} \
  --epochs {args.epochs} \
  --patience {args.patience}
"""
    
    exit_code, stdout, stderr = run_command_on_instance(instance_id, run_cmd, timeout=14400)
    
    print("\n" + "=" * 70)
    print("Training Results")
    print("=" * 70)
    print(stdout[-2000:] if len(stdout) > 2000 else stdout)
    
    if exit_code != 0:
        print(f"\n⚠️  Training had errors: {stderr[-500:]}")
    
    # Download results
    print("\n" + "=" * 70)
    print("Step 7: Download results")
    print("=" * 70)
    
    download_results_script = f"""python3 << 'PYUPLOAD'
import boto3
import json

s3 = boto3.client('s3')
bucket = '{bucket}'

# Upload embeddings
try:
    s3.upload_file('/tmp/training/embeddings.wv', bucket, 'embeddings/{Path(args.output).name}')
    print('✅ Uploaded embeddings to S3')
except Exception as e:
    print(f'⚠️  Could not upload embeddings: {{e}}')

# Upload training history
try:
    with open('/tmp/training/embeddings_history.json') as f:
        history = json.load(f)
    s3.put_object(
        Bucket=bucket,
        Key='experiments/training_history.json',
        Body=json.dumps(history, indent=2),
        ContentType='application/json'
    )
    print('✅ Uploaded training history to S3')
except Exception as e:
    print(f'⚠️  Could not upload history: {{e}}')
PYUPLOAD
"""
    
    exit_code, stdout, stderr = run_command_on_instance(instance_id, download_results_script, timeout=300)
    print(stdout)
    
    # Download locally
    local_embeddings = Path(args.output)
    if download_from_s3(f"embeddings/{local_embeddings.name}", local_embeddings, bucket):
        print(f"✅ Embeddings saved to {local_embeddings}")
    
    # Terminate instance
    print("\n" + "=" * 70)
    print("Step 8: Terminate instance")
    print("=" * 70)
    terminate_instance(instance_id)
    
    print("\n" + "=" * 70)
    print("✅ Improved training complete!")
    print("=" * 70)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

