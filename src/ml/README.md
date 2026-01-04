# ML Pipeline

Python code for training embeddings, evaluation, and experiments.

## Core Files

Training:
- `card_similarity_pecan.py` - Train Node2Vec embeddings using PecanPy
- `similarity_methods.py` - Various similarity methods (Jaccard, cosine, etc)

Evaluation:
- `evaluate.py` - Metrics (P@K, MRR, NDCG), experiment logging
- `compare_models.py` - Compare multiple embedding methods
- `improved_jaccard.py` - Jaccard with type filtering

LLM Tools:
- `llm_annotator.py` - Generate annotations using LLM
- `llm_data_validator.py` - Validate data quality with LLM
- `test_llm_annotation.py` - Test LLM annotation setup

API:
- `api.py` - FastAPI server for similarity queries

Utilities:
- `utils/` - Shared utilities (paths, constants, data loading)
- `tests/` - 31 passing tests

## Setup

```bash
# From repo root, create venv and install deps via uv
uv venv --python 3.11
uv sync --extra api --extra embeddings --extra dev
```

## Running Tests

```bash
# From repo root
uv run -q python -m pytest -q

# Or only ML tests
uv run -q python -m pytest -q src/ml/tests
```

## Training Example

```bash
# Export graph from backend
cd src/backend
go run cmd/export-graph/main.go pairs.csv

# Train embeddings
cd ../ml
uv run python card_similarity_pecan.py \
  --input ../backend/pairs.csv \
  --output magic_128d \
  --dim 128

# Evaluate
uv run python evaluate.py \
  --embeddings magic_128d.wv \
  --test-set ../../experiments/test_set_canonical_magic.json
```

## Experiment Tracking

All experiments logged to `../../experiments/EXPERIMENT_LOG_CANONICAL.jsonl`.

Use `evaluate.py::Evaluator` for consistent experiment tracking:

```python
from evaluate import Evaluator

eval = Evaluator(test_set_path="../../experiments/test_set_canonical_magic.json")
results = eval.evaluate_model(model, cards, k_values=[5, 10, 20])
# Results automatically include P@K, MRR, NDCG
```

## Experimental Code

Advanced techniques and old experiments are in `experimental/`:
- Research paper implementations (A-Mem, memory evolution)
- Old experiment files (run_exp_*.py)
- Duplicate experiment tracking systems
- One-off utilities

See `experimental/README.md` for details on why these are archived.

## Gold Data Refinement

Iteratively improve test set quality with more queries and more labels:

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

Key Scripts:
- `iterative_refine_gold_data.py` - Main refinement pipeline (expand + deepen + re-label)
- `batch_deepen_labels.py` - Add more labels to existing queries
- `parallel_multi_judge.py` - Parallel execution for faster labeling
- `analyze_eval_data_quality.py` - Analyze test set quality metrics

Quality Targets:
- Label density: 15-25+ labels per query
- IAA: ≥0.7 (Inter-Annotator Agreement)
- Coverage: All card types, formats, archetypes

See `docs/GOLD_DATA_REFINEMENT.md` for complete documentation.

## Current Focus

1. Fix format-specific use case (Modern, Legacy specific suggestions)
2. Get P@10 > 0.10 on specific use case
3. Add more tests for edge cases
4. Implement diagnostic tools
5. Continuously refine gold data (more queries, more labels, higher IAA)

Not building sophisticated meta-learning systems until basics work reliably.
