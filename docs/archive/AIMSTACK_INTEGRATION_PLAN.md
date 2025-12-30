# AimStack Integration Plan

## Overview

AimStack is an open-source experiment tracking platform that provides:
- Real-time experiment tracking
- Metric visualization
- Hyperparameter comparison
- Artifact management
- Reproducibility tracking

## Current State

**No experiment tracking system integrated**
- Experiments logged to JSON files (`EXPERIMENT_LOG.jsonl`, various JSON files)
- No centralized tracking dashboard
- No automatic metric logging during training
- Manual result comparison required

## Integration Benefits

1. **Real-time Monitoring**: Track training progress live
2. **Visual Comparison**: Compare hyperparameters and results side-by-side
3. **Reproducibility**: Automatic logging of all hyperparameters and code state
4. **Artifact Management**: Track embeddings, checkpoints, and results
5. **Query Interface**: Use AimQL to filter and analyze experiments

## Integration Points

### 1. Training Scripts

**File**: `src/ml/scripts/improve_training_with_validation_enhanced.py`

```python
import aim

# Initialize run
aim_run = aim.Run(
    experiment='embedding_training',
    repo='.aim',
    hparams={
        'dim': args.dim,
        'walk_length': args.walk_length,
        'num_walks': args.num_walks,
        'window_size': args.window_size,
        'p': args.p,
        'q': args.q,
        'epochs': args.epochs,
        'lr': args.lr,
        'lr_decay': args.lr_decay,
        'val_ratio': args.val_ratio,
        'patience': args.patience,
    }
)

# Track metrics during training
for epoch in range(epochs):
    train_loss = ...
    val_loss = ...
    val_p10 = ...
    
    aim_run.track(train_loss, name='loss', context={'subset': 'train'})
    aim_run.track(val_loss, name='loss', context={'subset': 'val'})
    aim_run.track(val_p10, name='p10', context={'subset': 'val'})
    
    # Track learning rate
    aim_run.track(current_lr, name='learning_rate')
    
    # Track embeddings as artifact
    if epoch % checkpoint_interval == 0:
        aim_run.track(embedding_path, name='checkpoint', context={'epoch': epoch})
```

### 2. Hyperparameter Search

**File**: `src/ml/scripts/improve_embeddings_hyperparameter_search.py`

```python
import aim

# Create experiment for hyperparameter search
aim_run = aim.Run(
    experiment='hyperparameter_search',
    repo='.aim',
    hparams=params  # All hyperparameters
)

# Track each configuration's results
for params in grid_search:
    result = evaluate_config(params)
    
    aim_run.track(result['p10'], name='p10', context={'config': params})
    aim_run.track(result['ndcg'], name='ndcg', context={'config': params})
    aim_run.track(result['mrr'], name='mrr', context={'config': params})
```

### 3. Evaluation Scripts

**File**: `src/ml/scripts/evaluate_all_embeddings.py`

```python
import aim

aim_run = aim.Run(
    experiment='embedding_evaluation',
    repo='.aim',
    hparams={
        'embedding_method': method_name,
        'test_set': test_set_path,
    }
)

# Track evaluation metrics
aim_run.track(p10, name='p10')
aim_run.track(ndcg, name='ndcg')
aim_run.track(mrr, name='mrr')

# Track confusion matrix or other artifacts
aim_run.track(confusion_matrix_path, name='confusion_matrix')
```

### 4. API Metrics

**File**: `src/ml/api/api.py`

```python
import aim

# Track API usage metrics
aim_run = aim.Run(
    experiment='api_usage',
    repo='.aim',
)

# Track request metrics
@router.middleware("http")
async def track_api_metrics(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    aim_run.track(duration, name='request_duration', context={
        'endpoint': request.url.path,
        'method': request.method,
    })
    
    return response
```

## Implementation Steps

### Step 1: Install AimStack

```bash
uv add aim
```

### Step 2: Initialize Aim Repository

```bash
aim init
```

### Step 3: Integrate Training Scripts

1. Add Aim tracking to `improve_training_with_validation_enhanced.py`
2. Add Aim tracking to `improve_embeddings_hyperparameter_search.py`
3. Add Aim tracking to evaluation scripts

### Step 4: Create Aim Helper Module

**File**: `src/ml/utils/aim_helpers.py`

```python
"""AimStack integration helpers for consistent tracking"""

import aim
from pathlib import Path
from typing import Dict, Any, Optional

AIM_REPO = Path('.aim')

def create_training_run(
    experiment_name: str,
    hparams: Dict[str, Any],
    tags: Optional[list] = None,
) -> aim.Run:
    """Create an Aim run for training experiments"""
    run = aim.Run(
        experiment=experiment_name,
        repo=str(AIM_REPO),
        hparams=hparams,
        tags=tags or [],
    )
    return run

def track_training_metrics(
    run: aim.Run,
    epoch: int,
    train_loss: float,
    val_loss: float,
    val_p10: float,
    learning_rate: float,
):
    """Track standard training metrics"""
    run.track(train_loss, name='loss', context={'subset': 'train'}, step=epoch)
    run.track(val_loss, name='loss', context={'subset': 'val'}, step=epoch)
    run.track(val_p10, name='p10', context={'subset': 'val'}, step=epoch)
    run.track(learning_rate, name='learning_rate', step=epoch)

def track_evaluation_metrics(
    run: aim.Run,
    p10: float,
    ndcg: float,
    mrr: float,
    method: str,
):
    """Track evaluation metrics"""
    run.track(p10, name='p10', context={'method': method})
    run.track(ndcg, name='ndcg', context={'method': method})
    run.track(mrr, name='mrr', context={'method': method})
```

### Step 5: Update pyproject.toml

```toml
dependencies = [
    # ... existing dependencies ...
    "aim>=3.0.0",
]
```

### Step 6: Launch Aim UI

```bash
aim up
```

Access at `http://localhost:43800`

## Usage Examples

### Training with Aim

```bash
uv run src/ml/scripts/improve_training_with_validation_enhanced.py \
    --input data/processed/pairs_large.csv \
    --output data/embeddings/trained.wv \
    --dim 128 \
    --walk-length 80 \
    --num-walks 10 \
    --window-size 10 \
    --p 1.0 \
    --q 1.0 \
    --epochs 10 \
    --val-ratio 0.1 \
    --patience 3 \
    --lr 0.025 \
    --lr-decay 0.95
```

Then view results:
```bash
aim up
```

### Hyperparameter Search with Aim

```bash
uv run src/ml/scripts/improve_embeddings_hyperparameter_search.py \
    data/processed/pairs_large.csv \
    experiments/hyperparameter_results.json \
    --test-set experiments/test_set_labeled_magic.json
```

Compare results in Aim UI using AimQL:
```
p10 > 0.1 and dim == 128
```

## Migration from JSON Logs

Create a migration script to import existing JSON experiment logs:

**File**: `src/ml/scripts/migrate_experiments_to_aim.py`

```python
import aim
import json
from pathlib import Path

def migrate_experiment_log():
    """Migrate EXPERIMENT_LOG.jsonl to Aim"""
    log_file = Path('experiments/EXPERIMENT_LOG.jsonl')
    
    with open(log_file) as f:
        for line in f:
            exp = json.loads(line)
            
            run = aim.Run(
                experiment=exp.get('experiment_id', 'migrated'),
                repo='.aim',
                hparams=exp.get('config', {}),
            )
            
            # Track results
            if 'results' in exp:
                for metric, value in exp['results'].items():
                    run.track(value, name=metric)
            
            run.finalize()
```

## Best Practices

1. **Consistent Naming**: Use consistent experiment names and metric names
2. **Context Organization**: Use context to group related metrics (train/val, different methods)
3. **Artifact Tracking**: Track embeddings, checkpoints, and results as artifacts
4. **Hyperparameter Logging**: Log all hyperparameters, even defaults
5. **Tags**: Use tags to mark important runs (best, baseline, etc.)

## Next Steps

1. ✅ Install AimStack
2. ✅ Initialize Aim repository
3. ⏳ Integrate into training scripts
4. ⏳ Integrate into hyperparameter search
5. ⏳ Integrate into evaluation scripts
6. ⏳ Migrate existing experiment logs
7. ⏳ Set up Aim UI for team access

