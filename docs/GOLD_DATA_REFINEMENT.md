# Gold Data Refinement Pipeline

## Overview

The iterative refinement pipeline continuously improves test set quality by:
1. **Expanding**: Adding new queries to increase coverage
2. **Deepening**: Adding more labels to existing queries (increasing label density)
3. **Re-labeling**: Improving queries with low Inter-Annotator Agreement (IAA)

This creates a continuous improvement loop for gold data, ensuring test sets have:
- High label density (15-25+ labels per query)
- High IAA (≥0.7)
- Broad coverage across card types, formats, and archetypes

## Quick Start

```bash
# Quick test (5 queries, 1 iteration)
just iterative-refine \
    input="experiments/test_set_expanded_magic.json" \
    output="experiments/test_set_refined.json" \
    iterations=1 \
    max-queries=5

# Production refinement (20 queries per iteration, 3 iterations)
just iterative-refine \
    input="experiments/test_set_expanded_magic.json" \
    output="experiments/test_set_refined.json" \
    iterations=3 \
    max-queries=20
```

## Components

### 1. Iterative Refinement (`iterative_refine_gold_data.py`)

Main script that orchestrates the refinement process.

**Features:**
- Expands queries: Adds new queries per iteration
- Deepens labels: Adds more labels to existing queries below target
- Re-labels: Improves queries with low IAA (<0.7)
- Checkpoints: Saves progress after each iteration
- Progress tracking: Shows [X/Y] progress for each query

**Usage:**
```bash
uv run --script src/ml/scripts/iterative_refine_gold_data.py \
    --input experiments/test_set_expanded_magic.json \
    --output experiments/test_set_refined.json \
    --iterations 3 \
    --new-queries-per-iter 20 \
    --num-judges 3 \
    --min-labels-target 15 \
    --min-iaa-target 0.7 \
    --max-queries-per-iter 20
```

**Arguments:**
- `--input`: Input test set JSON
- `--output`: Output refined test set JSON
- `--iterations`: Number of refinement iterations (default: 3)
- `--new-queries-per-iter`: New queries to add per iteration (default: 20)
- `--num-judges`: Number of LLM judges per query (default: 3)
- `--min-labels-target`: Target minimum labels per query (default: 15)
- `--min-iaa-target`: Target minimum IAA (default: 0.7)
- `--max-queries-per-iter`: Maximum queries to process per iteration (default: None = all)
- `--no-deepen`: Skip deepening existing queries
- `--no-expand`: Skip expanding with new queries

### 2. Batch Deepening (`batch_deepen_labels.py`)

Dedicated script to add more labels to existing queries.

**Usage:**
```bash
uv run --script src/ml/scripts/batch_deepen_labels.py \
    --input experiments/test_set_expanded_magic.json \
    --output experiments/test_set_deepened.json \
    --num-judges 3 \
    --target-labels 25 \
    --batch-size 10
```

### 3. Parallel Multi-Judge (`parallel_multi_judge.py`)

Parallel execution for faster labeling with multiple judges.

**Features:**
- Parallel execution: Multiple judges run concurrently
- Timeout handling: 2 minutes per judge (configurable)
- Error recovery: Continues even if some judges fail
- Majority voting: Combines judgments from multiple judges

## Quality Targets

### Label Density
- **Minimum**: 10 labels per query
- **Target**: 15-25 labels per query
- **Ideal**: 25+ labels per query

### IAA (Inter-Annotator Agreement)
- **Minimum**: 0.5
- **Target**: 0.7+
- **Ideal**: 0.8+

### Coverage
- **Card Types**: All major types (creatures, spells, lands, etc.)
- **Formats**: Multiple formats (Standard, Modern, Legacy, etc.)
- **Archetypes**: Aggro, Control, Combo, Midrange, Tempo
- **Use Cases**: Substitute, synergy, archetype, functional

## Best Practices

1. **Start Small**: Use `max-queries=5` for testing
2. **Production Settings**: Use `max-queries=20`, `iterations=3` for production
3. **Monitor Progress**: Check checkpoints after each iteration
4. **Resume from Checkpoint**: Use checkpoint files as input if interrupted

See `src/ml/README.md` for more details.
