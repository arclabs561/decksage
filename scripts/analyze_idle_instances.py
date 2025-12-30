#!/usr/bin/env python3
"""
Analyze which instances are safe to terminate based on activity and age.
"""

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "boto3>=1.34.0",
# ]
# ///

import sys
from datetime import datetime, timezone

try:
    import boto3
except ImportError:
    print("❌ boto3 not available. Install with: uv pip install boto3")
    sys.exit(1)


def analyze_instances():
    """Analyze instances and recommend which can be terminated."""
    ec2 = boto3.client("ec2")
    ssm = boto3.client("ssm")
    
    # Get all running instances
    response = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )
    
    instances = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            name = None
            for tag in instance.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break
            
            launch_time = instance["LaunchTime"]
            age_hours = (datetime.now(timezone.utc) - launch_time).total_seconds() / 3600
            
            # Check SSM status
            ssm_online = False
            try:
                ssm_response = ssm.describe_instance_information(
                    Filters=[{"Key": "InstanceIds", "Values": [instance["InstanceId"]]}]
                )
                ssm_online = len(ssm_response["InstanceInformationList"]) > 0
            except Exception:
                pass
            
            # Check for IAM role
            has_iam_role = instance.get("IamInstanceProfile") is not None
            
            # Check if spot instance
            is_spot = instance.get("SpotInstanceRequestId") is not None
            
            instances.append({
                "id": instance["InstanceId"],
                "name": name,
                "type": instance["InstanceType"],
                "launch_time": launch_time,
                "age_hours": age_hours,
                "ssm_online": ssm_online,
                "has_iam_role": has_iam_role,
                "is_spot": is_spot,
                "public_ip": instance.get("PublicIpAddress"),
            })
    
    # Analyze each instance
    print("=" * 70)
    print("IDLE INSTANCE ANALYSIS")
    print("=" * 70)
    print()
    
    safe_to_terminate = []
    keep_instances = []
    unknown_instances = []
    
    for inst in instances:
        print(f"Instance: {inst['id']}")
        print(f"  Name: {inst['name'] or '(none)'}")
        print(f"  Type: {inst['type']}")
        print(f"  Age: {inst['age_hours']:.1f} hours ({inst['age_hours']/24:.1f} days)")
        print(f"  SSM: {'✅' if inst['ssm_online'] else '❌'}")
        print(f"  IAM Role: {'✅' if inst['has_iam_role'] else '❌'}")
        print(f"  Spot: {'Yes' if inst['is_spot'] else 'No'}")
        print()
        
        # Decision logic
        reasons_keep = []
        reasons_terminate = []
        
        # Reasons to keep
        if inst['ssm_online']:
            # Check if it has processes (we'd need to run a command, but for now assume if SSM works it might be active)
            reasons_keep.append("SSM accessible - may be active")
        
        if inst['age_hours'] < 2:
            reasons_keep.append("Very recently launched (< 2 hours)")
        
        # Reasons to terminate
        if not inst['ssm_online'] and not inst['has_iam_role']:
            reasons_terminate.append("No SSM access and no IAM role - cannot manage")
        
        if inst['age_hours'] > 24 and not inst['ssm_online']:
            reasons_terminate.append(f"Old ({inst['age_hours']/24:.1f} days) and no SSM - likely idle")
        
        if inst['is_spot'] and inst['age_hours'] > 12:
            reasons_terminate.append("Spot instance running > 12 hours - may be idle")
        
        # Decision
        if reasons_terminate and not reasons_keep:
            safe_to_terminate.append((inst, reasons_terminate))
            print(f"  ⚠️  RECOMMEND TERMINATE")
            for reason in reasons_terminate:
                print(f"     - {reason}")
        elif reasons_keep:
            keep_instances.append((inst, reasons_keep))
            print(f"  ✅ KEEP")
            for reason in reasons_keep:
                print(f"     - {reason}")
        else:
            unknown_instances.append((inst, []))
            print(f"  ❓ UNKNOWN - Manual review needed")
        
        print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    
    if safe_to_terminate:
        print(f"⚠️  SAFE TO TERMINATE ({len(safe_to_terminate)} instances):")
        print()
        for inst, reasons in safe_to_terminate:
            print(f"  {inst['id']} ({inst['name'] or 'unnamed'})")
            print(f"    Type: {inst['type']}, Age: {inst['age_hours']/24:.1f} days")
            print(f"    Command: aws ec2 terminate-instances --instance-ids {inst['id']}")
            print()
    else:
        print("✅ No instances clearly safe to terminate")
        print()
    
    if keep_instances:
        print(f"✅ KEEP ({len(keep_instances)} instances):")
        for inst, reasons in keep_instances:
            print(f"  {inst['id']} ({inst['name'] or 'unnamed'})")
        print()
    
    if unknown_instances:
        print(f"❓ MANUAL REVIEW ({len(unknown_instances)} instances):")
        for inst, _ in unknown_instances:
            print(f"  {inst['id']} ({inst['name'] or 'unnamed'})")
        print()
    
    print("=" * 70)
    
    return safe_to_terminate, keep_instances, unknown_instances


if __name__ == "__main__":
    analyze_instances()

