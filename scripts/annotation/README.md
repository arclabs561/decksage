# Annotation Tools

This directory contains wrapper scripts and documentation for the annotation tools.

## Python Annotation Tools (`ml.annotation.*`)

Status: Active and complete

- **LLM similarity annotations** (JSONL): Scale annotation using LLMs
- **Hand annotation batch generation**: Create YAML batches for manual annotation
- **Direct integration with training**: Convert annotations → substitution pairs → training (5x weight)
- **Conversion utilities**: Transform between annotation formats
- **Commands**: Use `just annotate-*` (see justfile)

### Features

- Loads embeddings directly from Gensim/Word2Vec
- Integrates with existing Python ML pipeline
- Supports both LLM and hand annotations
- Converts annotations to substitution pairs for training
- Merges annotations into test sets for evaluation

## When to Use

| Task | Tool | Notes |
|------|------|-------|
| LLM annotations | `annotate-llm` | Uses pydantic-ai for scale |
| Hand annotation batches | `annotate-generate` | Creates YAML for manual annotation |
| Grade annotations | `annotate-grade` | Validates completion and quality |
| Merge to test set | `annotate-merge` | Adds to evaluation ground truth |
| Convert to training data | `annotate-convert` | Creates substitution pairs (5x weight in training) |

## Quick Start

### Complete Workflow

```bash
# 1. Generate LLM annotations (scale annotation)
just annotate-llm 100 diverse

# 2. OR generate hand annotation batch (manual expert annotation)
just annotate-generate magic 50 38

# 3. Grade annotations (validate completion)
just annotate-grade annotations/hand_batch_magic.yaml

# 4. Merge to test set (evaluation ground truth)
just annotate-merge annotations/hand_batch_magic.yaml experiments/test_set_canonical_magic.json

# 5. Convert to substitution pairs for training (5x weight)
just annotate-convert annotations/similarity_annotations.jsonl experiments/substitution_pairs.json

# 6. Use in training
python -m ml.scripts.train_multitask_refined_enhanced \
    --substitution-pairs experiments/substitution_pairs.json \
    --pairs data/processed/pairs_large.csv \
    --output data/embeddings/multitask.wv
```

## Integration with Training

Annotations flow into training in two ways:

1. **Substitution Pairs** (5x weight): High-confidence pairs (`relevance=4`, `is_substitute=True`)
   - Converted with `annotate-convert`
   - Used with `--substitution-pairs` flag
   - Gets `substitution_weight=5.0` vs `cooccurrence_weight=1.0`

2. **Test Sets** (evaluation): All annotations merged for evaluation
   - Merged with `annotate-merge`
   - Used by evaluation scripts to measure P@10, MRR, etc.

See `annotations/README.md` for detailed annotation workflow and guidelines.

