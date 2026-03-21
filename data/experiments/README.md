# Experiment Log

Each experiment gets a YAML file: `NNNN_short_name.yaml`.

## Workflow

### Automatic (preferred)

Training scripts write a JSON run summary to `data/logs/`. To create an experiment:

```bash
# 1. Train (writes run summary + loss CSV automatically)
uv run scripts/training/train_metapath2vec.py --game magic --epochs 160

# 2. Generate experiment YAML from the run summary
uv run scripts/evaluation/log_experiment.py data/logs/magic_metapath2vec_run.json \
    --hypothesis "160 epochs should improve over 80ep baseline"

# 3. Review the YAML, fill in conclusion, commit with the code
```

### Manual

Create the YAML by hand following the schema below. Use for non-training experiments
(annotation work, data curation, architecture analysis).

## File format

```yaml
id: "0001"
date: "2026-03-17"
title: "Short descriptive title"
game: magic | pokemon | yugioh | all

# WHY: write BEFORE running
hypothesis: >
  One sentence: what do you expect to happen and why?

# HOW: exact reproduction
method:
  type: embedding | fine-tune | fusion | completion | annotation | sweep
  script: scripts/training/foo.py
  args: "--game magic --epochs 50"
  commit: abc1234  # git SHA at time of run

# WITH WHAT: data provenance
data:
  edge_types:          # {type: count} from graph
    deck: 500000
    enriched: 120000
  num_cards: 21151     # total unique cards in graph
  training:
    source: data/test_sets/annotated_magic_v2.json
    count: 3290
    split: "90/10 train/val"

# WHAT HAPPENED: measured metrics only
results:
  sub_ndcg: 0.228
  syn_ndcg: 0.228
  meta_ndcg: 0.222
  final_loss: 0.705
  duration_s: 4800
  quality_pairs:
    "Lightning Bolt <-> Lava Spike": 0.28
    "Sol Ring <-> Arcane Signet": 0.80

# SO WHAT: write AFTER reviewing results
conclusion: >
  One sentence: did the hypothesis hold? What did we learn? What next?

# PRODUCED
artifacts:
  - data/embeddings/magic_metapath2vec.wv
  - data/logs/magic_metapath2vec_loss.csv
```

## Artifacts produced by training scripts

| File | Content | Format |
|------|---------|--------|
| `data/logs/{game}_{model}_loss.csv` | Per-epoch loss curve | CSV: epoch, loss, wall_s |
| `data/logs/{game}_{model}_run.json` | Full run summary | JSON (params, data, results, artifacts) |
| `data/checkpoints/{model}_{nodes}n_{dim}d.pt` | Training checkpoint | PyTorch state dict |
| `data/embeddings/{game}_{model}.wv` | Trained embeddings | gensim KeyedVectors |

## Rules

- Write hypothesis BEFORE running. If you can't state what you expect, you don't understand the experiment.
- Never backfill metrics you didn't measure. "not recorded" is honest; guessing is not.
- Record negative results. "This didn't work because X" is as valuable as "this improved Y by Z%."
- Commit experiment files WITH the code changes, not separately.
- Per-game metrics always. A single "overall" number hides domain-specific results.

## Index

See `SUMMARY.md` for a chronological table of all experiments.
