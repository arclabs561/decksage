# AWS Setup Notes for Downstream Evaluation

## Current Status
- Script is ready: `scripts/evaluation/runctl_downstream_eval.sh`
- Defaults to AWS mode with spot instances
- Uses `--data-s3` and `--output-s3` per project rules

## AWS Connectivity Issues
runctl requires either:
1. SSH access (key pair + security group allowing SSH from your IP)
2. SSM access (IAM instance profile with SSM permissions)

## Recommended Setup

### Option 1: Use SSM (Preferred)
```bash
# Create instance with SSM
../runctl/target/release/runctl aws create --spot --iam-instance-profile EC2-SSM-InstanceProfile g4dn.xlarge

# Wait for SSM agent to register (check with):
aws ssm describe-instance-information --filters "Key=InstanceIds,Values=i-XXX"

# Run evaluation
./scripts/evaluation/runctl_downstream_eval.sh aws <instance-id>
```

### Option 2: Use SSH
```bash
# Create instance with key pair
../runctl/target/release/runctl aws create --spot --key-name tarek g4dn.xlarge

# Ensure security group allows SSH from your IP
# Then run:
export SSH_KEY_PATH=~/.ssh/tarek.pem
./scripts/evaluation/runctl_downstream_eval.sh aws <instance-id>
```

## Troubleshooting
- If SSH times out: Check security groups, ensure port 22 is open from your IP
- If SSM doesn't work: Verify IAM profile is attached, wait for agent registration
- Spot requests failing: Try on-demand or different instance type
