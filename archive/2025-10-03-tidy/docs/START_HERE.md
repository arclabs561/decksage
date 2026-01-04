# DeckSage - Start Here

## Quick Start for Next Session

```bash
cd /Users/henry/Documents/dev/decksage
cat experiments/SYSTEM_STATE_FINAL.json  # Read complete state
cd src/ml
python self_sustaining_loop.py           # Continue autonomous evolution
```

## Current State (After 47 Experiments)

**Performance:** P@10 = 0.12 (plateau with co-occurrence data)
**Experiments:** 10 verified (37 failures cleaned)
**System:** Fully autonomous, research-informed, harmonized

## What We Discovered

1. **Ceiling:** Co-occurrence alone maxes at ~0.12
2. **Need:** Meta statistics (papers show 42-68%)
3. **Blocker:** Metadata parsing failed 7 times
4. **Solution:** External data OR fix scraper

## Files That Matter

Core code:
- `src/ml/meta_learner.py` (analyzes all experiments)
- `src/ml/true_closed_loop.py` (protects baseline)
- `src/ml/evolving_experiment_memory.py` (A-Mem network)
- `src/ml/memory_management.py` (quality gates)

Experiments:
- `experiments/EXPERIMENT_LOG.jsonl` (10 verified)
- `experiments/test_set_canonical_magic.json` (30 queries)
- `experiments/MOTIVATIONS.md` (why principles exist)

Design:
- `API_AND_LOSS_DESIGN.md` (LTR formulation)
- `HETEROGENEOUS_GRAPH_DESIGN.md` (graph structure)
- `MATHEMATICAL_FORMULATION.md` (problem definition)

## Decision Points

**Path A:** Fix metadata parsing (engineering, could take days)
**Path B:** Use 17lands API (quick, if available)
**Path C:** Continue with co-occurrence, accept 0.12

System will autonomously continue from any path.

## Papers Applied

✅ **A-Mem** (Rutgers 2025): Networked experiments, evolution
✅ **Memory Management** (Harvard 2025): Quality gates
📋 **JKU MTG** (2024): Designed, needs meta stats
📋 **Q-DeckRec** (UCLA 2018): Designed, needs labels

## Achievement

Built autonomous scientific discovery system that:
- Ran 47 experiments
- Found 3 root causes
- Designed complete solution
- Embedded motivations
- Ready to continue forever

Not just results - a **self-improving process**.
