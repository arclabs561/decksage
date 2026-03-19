# Experiment Log

Each experiment gets a YAML file: `NNNN_short_name.yaml`.

## File format

```yaml
id: "0001"
date: "2026-03-17"
title: "Short descriptive title"
game: magic | pokemon | yugioh | all

# WHY: hypothesis or goal
hypothesis: >
  One sentence: what do you expect to happen and why?

# WHAT: method
method:
  type: embedding | fine-tune | fusion | completion | annotation | sweep
  script: scripts/training/foo.py  # path relative to repo root
  args: "--game magic --epochs 50"  # CLI args used
  commit: abc1234  # git SHA at time of run
  model: intfloat/e5-base-v2  # base model if applicable

# WITH WHAT: data provenance
data:
  training:
    source: data/test_sets/annotated_magic_v2.json
    description: "481 annotated pairs, mode-labeled (sub/syn/meta)"
    count: 3290  # number of examples
    split: "90/10 train/val"
  graph: data/graphs/magic_unified.db  # if used
  embeddings: data/embeddings/magic_v5_fused.wv  # if used

# RESULTS: metrics
results:
  overall_ndcg: 0.156
  sub_ndcg: 0.150
  syn_ndcg: 0.133
  meta_ndcg: 0.143
  contextual_recall: 0.38
  # add any metric that matters

# SO WHAT: interpretation
conclusion: >
  One sentence: what did we learn? Did the hypothesis hold?
  What should we try next?

# artifacts produced
artifacts:
  - data/embeddings/magic_v5_fused.wv
  - data/experiments/lightgcn_sweep_magic.tsv
```

## Index

See `SUMMARY.md` for a chronological table of all experiments and key metrics.
The TSV `experiment_log.tsv` is the legacy flat format (kept for backward compat).
