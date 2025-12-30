# Training Instance Management

## Quick Reference

### Create Instance
```bash
just train-aws-create  # Creates g4dn.xlarge (GPU-enabled)
```

### Check Status
```bash
uv run --script scripts/verify_training_status.py
```

### Monitor Instance
```bash
just train-aws-monitor <instance-id>
```

### Clean Up
```bash
uv run --script scripts/analyze_idle_instances.py
```

## Instance Types

**Default**: `g4dn.xlarge` (GPU-enabled)
- Best for training workloads
- Configured in `justfile` and `train_with_runctl.py`
- Fallback: `t3.large` if GPU unavailable

**Not Recommended**: `t3.medium`, `t4g.small` (too small for training)

## Personal Infrastructure

The following instances are personal infrastructure and excluded from training management:

- `gyarados` (i-0bbef6e651c9588b1)
- `alakazam` (i-0bb5da468ad8e730f)

These are automatically excluded from:
- `scripts/verify_training_status.py`
- `scripts/analyze_idle_instances.py`

## Best Practices

1. Always use GPU instances (`g4dn.xlarge`) for training
2. Use spot instances for cost savings (default)
3. Monitor regularly to catch idle instances
4. Terminate when done to avoid costs
5. Exclude personal infrastructure from automated management
