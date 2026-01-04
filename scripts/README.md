# Scripts Directory

This directory contains all executable scripts for the DeckSage project, organized by purpose.

## Directory Structure

### `automation/`
Automated workflows (cron jobs, scheduled tasks)
- `daily_update.sh` - Daily graph updates and quick evaluation
- `weekly_retrain.sh` - Weekly full retraining and evaluation
- `setup_cron.sh` - Set up cron jobs for automation

### `monitoring/`
**Consolidated monitoring scripts** (replaces 12+ individual monitoring scripts)
- `status.sh` - Quick status check (runctl, AWS instances, key files)
- `training.sh` - Training monitoring (structured logs + S3)
- `full_pipeline.sh` - Full pipeline monitoring (training + evaluation)
- `comprehensive.py` - Comprehensive system monitoring (embeddings, test sets, evaluation)

**Legacy scripts** (moved here, use consolidated versions above):
- `monitor_*.py`, `monitor_*.sh` - Old monitoring scripts (deprecated, use consolidated versions)

### `validation/`
Validation and verification scripts
- `validate_*.py` - Data and model validation
- `verify_*.py` - Verification checks
- `check_*.sh` - Quick validation checks

### `analysis/`
Analysis and reporting scripts
- `analyze_*.py` - Data analysis
- `review_*.py` - Review and audit scripts
- `compute_*.py` - Metric computation
- `data_status_report.py` - Data status reporting
- `dataset_health_check.py` - Dataset health checks

### `generation/`
Data generation and preparation scripts
- `generate_*.py` - Generate test data, annotations, audits
- `prepare_*.py` - Prepare training/evaluation data

### `pipeline/`
End-to-end pipeline scripts
- `run_*.sh` - Pipeline execution scripts
- `*_pipeline.sh` - Specific pipeline workflows
- `hybrid_embeddings_pipeline.sh` - Hybrid embeddings pipeline
- `quick_start_hybrid.sh` - Quick start script

### `evaluation/`
Evaluation-specific scripts
- `runctl_*.sh` - Runctl-based evaluation
- `run_*.sh` - Evaluation execution
- `check_eval_status.sh` - Evaluation status checks
- `validate_e2e_runctl.sh` - End-to-end validation

### `training/`
Training-specific scripts
- `train_*.sh` - Training execution scripts
- `runctl_training.sh` - Runctl training wrapper
- `monitor_training*.sh` - Training monitoring (legacy, use `monitoring/training.sh`)

### `data_processing/`
Data processing and transformation
- `export_*.sh` - Data export scripts
- `sync_*.sh` - S3 sync scripts
- `generate_*.py` - Data generation

### `test_sets/`
Test set management
- `expand_*.py` - Test set expansion
- `update_*.sh` - Test set updates
- `generate_*.py` - Test set generation

### `model_management/`
Model versioning and promotion
- `promote_to_production.sh` - Promote models to production

### `instance_management/`
AWS instance management
- `pause_all_machines.sh` - Pause all instances
- `resume_all_machines.sh` - Resume all instances
- `auto_stop_after_training.sh` - Auto-stop after training

### `infrastructure/`
Infrastructure setup and management
- `setup_*.sh` - Setup scripts (EBS, volumes, etc.)
- `create_*.sh` - Resource creation
- `find_*.sh` - Resource discovery
- `check_*.sh` - Infrastructure checks

### `annotation/`
Annotation-related scripts
- `README.md` - Annotation workflow documentation

### `annotations/`
Annotation generation
- `generate_llm_annotations.py` - LLM-based annotation generation

### `cleanup/`
Cleanup and maintenance
- `remove_emojis.py` - Remove emojis from files

## Top-Level Scripts

Scripts that don't fit into categories above remain at the top level:
- `start_api.sh` - Start the DeckSage API
- `runctl_*.sh` - Runctl wrappers
- `FINAL_VERIFICATION.sh` - Final verification checks
- `apply_all_fixes.sh` - Apply all fixes
- `clean-docs.sh` - Clean up documentation
- Utility scripts (e.g., `card_companions.py`, `archetype_staples.py`)

## Usage Patterns

### Monitoring
```bash
# Quick status check
./scripts/monitoring/status.sh

# Monitor training
./scripts/monitoring/training.sh <instance-id>

# Monitor full pipeline
./scripts/monitoring/full_pipeline.sh <instance-id>

# Comprehensive monitoring
./scripts/monitoring/comprehensive.py [--once] [--interval 60]
```

### Validation
```bash
# Validate datasets
./scripts/validation/validate_datasets.py

# Check runctl status
./scripts/validation/check_runctl_status.sh
```

### Training
```bash
# Train with runctl
./scripts/training/train_with_runctl.sh <instance-id>

# Monitor training
./scripts/monitoring/training.sh <instance-id>
```

### Evaluation
```bash
# Run evaluation
./scripts/evaluation/runctl_evaluation.sh <instance-id>

# Check evaluation status
./scripts/evaluation/check_eval_status.sh <instance-id>
```

## Path Management

All scripts should use `PATHS` from `src/ml/utils/paths.py` for canonical paths:
```python
from ml.utils.paths import PATHS

# Use PATHS instead of hardcoded paths
card_attrs = PATHS.card_attributes
test_set = PATHS.test_magic
```

For path setup in scripts, use `path_setup.py`:
```python
from ml.utils.path_setup import setup_project_paths
project_root = setup_project_paths()
```

## Error Handling

All bash scripts should use:
```bash
set -euo pipefail
```

This ensures:
- `-e`: Exit on error
- `-u`: Error on undefined variables
- `-o pipefail`: Fail on pipe errors

## Script Organization Principles

1. **Categorize by purpose**: Group related scripts together
2. **Consolidate duplicates**: Merge overlapping functionality
3. **Use shared utilities**: `PATHS`, `path_setup.py`, logging utilities
4. **Document usage**: Include usage examples in script headers
5. **Standardize error handling**: All bash scripts use `set -euo pipefail`

## Migration Notes

- **Monitoring scripts**: Consolidated from 12+ scripts to 4 in `monitoring/`
- **Test sets**: Migrated from `test_set_canonical_*.json` to `test_set_unified_*.json`
- **Paths**: Migrating from hardcoded paths to `PATHS` abstraction
- **Error handling**: Standardized across all 85+ bash scripts
