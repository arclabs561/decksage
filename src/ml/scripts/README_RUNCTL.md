# Using runctl for Training

All training scripts now use `runctl` for unified AWS management.

## Quick Start

```bash
# Build runctl first
just runctl-build

# See all available commands
just list-runctl

# Train locally
just train-local

# Train on AWS (creates instance automatically)
just train-unified src/ml/scripts/improve_training_with_validation_enhanced.py

# Use existing instance
just train-aws <instance-id>
```

## Key Benefits

1. **Unified Interface**: Same commands for local, AWS, RunPod
2. **Automatic SSM/SSH**: No need to manage connection methods
3. **S3 Integration**: Built-in `--data-s3` and `--output-s3`
4. **Instance Management**: Create, monitor, terminate all handled

## Migration

Old scripts using direct boto3/SSM are deprecated. Use:
- `train_with_runctl.py` - Python wrapper for any script
- `train_on_aws_instance_runctl.py` - Drop-in replacement
- `justfile` commands - Pre-configured for common tasks

See `RUNCTL_MIGRATION.md` for details.
