# Experiments Directory

## Current State (January 2025)

### Test Sets (Canonical - Production Standard)
- `test_set_canonical_magic.json`: 38 queries ✅
- `test_set_canonical_pokemon.json`: 10 queries ✅
- `test_set_canonical_yugioh.json`: 13 queries ✅
- `ground_truth_v1.json`: 38 queries (Magic, merged from canonical)

### Test Sets (Expanded - Comprehensive Analysis)
- `test_set_expanded_magic.json`: Various sizes
- `test_set_expanded_pokemon.json`
- `test_set_expanded_yugioh.json`

### Experiment Logs
- `EXPERIMENT_LOG_CANONICAL.jsonl`: Consolidated experiment log
- Use canonical test sets for production evaluation
- Use expanded test sets for comprehensive analysis

### System State
- `SYSTEM_STATE_FINAL.json`: Complete context for resumption
- `CURRENT_BEST_magic.json`: Best method tracker
- `self_sustaining_state.json`: Autonomous loop state

### Documentation
- `MOTIVATIONS.md`: Why each principle exists (pain → solution)
- `PRINCIPLES.md`: What each paper contributes
- `NEXT_SESSION_PREP.md`: Action plan with options
- `ADVANCED_METHODS_ROADMAP.md`: Long-term plan
- `DATA_SOURCES.md`: Where data comes from

### Archived
- `archived/`: Old experiment logs (before cleaning)
- `plans/`: Experiment plan files

## Evaluation

### Running Evaluation
```bash
# All games with canonical test sets
just evaluate-all-games

# Comprehensive evaluation
just evaluate-final

# Specific embedding
uv run src/ml/scripts/evaluate_all_embeddings.py \
  --embedding data/embeddings/production.wv \
  --test-set experiments/test_set_canonical_magic.json
```

### Best Practices
- Use canonical test sets for production evaluation
- Use expanded test sets for comprehensive analysis
- Track Inter-Annotator Agreement (IAA) for labels
- Use confidence intervals for metrics

## Critical Files

- `test_set_canonical_*.json`: Production evaluation standard
- `EXPERIMENT_LOG_CANONICAL.jsonl`: Experiment history
- `fusion_grid_search_latest.json`: Latest fusion weights (auto-loaded by API)


