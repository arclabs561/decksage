# Experiment Logs

## Canonical Source

**`EXPERIMENT_LOG_CANONICAL.jsonl`** - The single source of truth (35 experiments, exp_001-exp_053)

Use this file for:
- Reading experiment history
- Cross-experiment comparisons
- Meta-analysis

## Archive

**`EXPERIMENT_LOG_OLD_PARTIAL.jsonl`** - Partial subset (16 experiments starting at exp_022)
- Kept for historical reference
- DO NOT USE for new experiments

**`EXPERIMENT_LOG_BACKUP.jsonl`** - Original backup before consolidation
- Historical reference only

## Python Usage

```python
from utils.paths import PATHS

# Load experiments
with open(PATHS.experiment_log) as f:
    experiments = [json.loads(line) for line in f]
```

## Consolidated: October 2, 2025

Previously had 3+ different log files. Consolidated to single canonical source.



