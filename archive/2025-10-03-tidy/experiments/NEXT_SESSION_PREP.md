# Next Session Preparation

## Critical Path to Improvement

Current: P@10 = 0.12 (verified across 9 experiments)
Target: P@10 = 0.42+ (match papers)
Blocker: Meta statistics inaccessible

## Option A: External Data Integration

```bash
# 1. Get 17lands data (if available)
curl "https://17lands.com/card_ratings/data" > data/17lands_stats.json

# 2. Parse into usable format
python src/ml/parse_17lands.py

# 3. Add to features
# Expected: P@10 jumps to 0.30-0.40
```

## Option B: Fix Internal Parsing

```bash
# 1. Debug why zstd files parse incorrectly
cd src/backend
go run ./cmd/debug-deck-parse data-full/games/magic/mtgtop8/collections/*.zst

# 2. Fix JSON structure or decompression
# 3. Re-export with working parser
# 4. Expected: Access archetype/format data
```

## Option C: Cross-Game Validation

```bash
# Verify our methods on YGO/Pokemon
# If consistent 0.12 across games → confirms co-occurrence ceiling
# If different → learn what's different about MTG

python src/ml/run_cross_game_experiments.py
```

## Immediate Actions (5 minutes)

1. Run system one more time to log final state
2. Save all key files
3. Document exact blockers
4. Prepare decision tree for next session

## Files Ready for Next Session

- experiments/EXPERIMENT_LOG.jsonl (10 verified)
- experiments/CURRENT_BEST_magic.json (0.12 baseline)
- experiments/test_set_canonical_magic.json (20 queries)
- src/ml/*.py (all integrated components)
- paper/findings.tex (experimental results)

## System Will Auto-Resume

```bash
cd src/ml
python self_sustaining_loop.py
# Will load state, analyze 10 experiments, make next decision
```
