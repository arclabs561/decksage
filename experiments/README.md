# Experiments Directory

## Current State (After 47 Experiments)

### Verified Results
- `EXPERIMENT_LOG.jsonl`: 10 verified experiments (cleaned from 47)
- Best: Jaccard P@10 = 0.12 on 20-query canonical test
- Plateau: All co-occurrence methods at 0.10-0.12

### Test Sets
- `test_set_canonical_magic.json`: 30 queries (expanded from 20)
- `test_set_canonical_yugioh.json`: 5 queries
- `test_set_canonical_pokemon.json`: 5 queries

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

## How to Resume

```bash
cd src/ml
python self_sustaining_loop.py
```

System will:
1. Load 10 verified experiments
2. Analyze patterns
3. Make autonomous decision
4. Suggest next experiment
5. Continue evolution

## Key Insights Embedded

1. **Ceiling Reached:** 0.12 P@10 with co-occurrence only
2. **Root Causes:** Wrong objective, wrong structure, metadata inaccessible
3. **Solution:** Heterogeneous graphs + LTR + meta statistics
4. **Papers:** A-Mem and Memory Mgmt in code, others designed

## Critical Files

- `EXPERIMENT_LOG.jsonl`: Source of truth (10 verified)
- `test_set_canonical_magic.json`: Evaluation standard
- `MOTIVATIONS.md`: Why system is designed this way

## Next Experiments (System-Suggested)

Based on 47 experiments, system suggests:
1. Integrate external meta statistics (highest impact)
2. Cross-game validation (verify patterns hold)
3. Fix metadata parsing (engineering work)

Human choice determines path.


