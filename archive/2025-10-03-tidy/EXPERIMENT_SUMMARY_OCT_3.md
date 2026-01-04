# Experiment Summary - October 3, 2025

## What We Tested

### Test 1: Fix "Failing" Test Suite
**Hypothesis**: Major integration failure
**Reality**: One linter error (redundant `\n`)
**Result**: ✅ All tests passing
**Lesson**: Check before assuming catastrophe

### Test 2: Format-Specific Similarity
**Hypothesis**: Filtering to format improves P@10
**Test**: Modern-only, Legacy-only vs all formats
**Results**:
- Baseline (all): P@10 = 0.0829
- Modern only: P@10 = 0.0045 (-94.6%)
- Legacy only: P@10 = 0.0342 (-58.7%)
**Result**: ❌ FAILED - dramatically worse
**Why**: Test set has generic queries, format filtering reduces data 5x

### Test 3: Archetype Staples Analysis
**Approach**: Frequency analysis instead of similarity
**Test**: Find cards appearing in 70%+ of archetype decks
**Results**:
- Red Deck Wins: 99.6% Mountain, 71% Burst Lightning ✓
- Reanimator: 89% Archon of Cruelty, 81% Reanimate ✓
- Boros Aggro: 70% Ocelot Pride, Guide of Souls ✓
**Result**: ✅ SUCCESS - useful, accurate data
**Why**: Uses co-occurrence's strength (frequency), not weakness (similarity)

## Key Discoveries

1. **P@10 = 0.08 is a real ceiling** for co-occurrence similarity
2. **Format-specific doesn't help** generic queries (needs format-aware queries)
3. **Archetype staples works great** - frequency analysis is co-occurrence's strength
4. **Co-occurrence has specific uses**: composition analysis, NOT functional similarity

## What to Build

**Works with current data**:
- Archetype staples (implemented ✓)
- Meta trend tracking
- Sideboard analysis
- Deck composition statistics

**Needs different signals**:
- Generic card similarity (needs card text embeddings)
- Cross-format suggestions (needs format-aware queries)
- Functional replacements (needs card mechanics understanding)

## Principles Applied

**"Experience reality as it unfolds"**:
- Tested assumptions quickly
- Accepted failures
- Pivoted based on data
- Built what works, not what we hoped would work

**"Debug slow vs fast"**:
- Could have spent days on scraper tests (works fine)
- Should have tested format-specific first (failed fast)
- Built working tool in 30 minutes after pivoting

## Repository Status

- **Tidied**: 100+ docs → 10 essential files
- **Tests**: All passing (Go + Python)
- **Working code**: Archetype staples analysis
- **Honest assessment**: P@10 = 0.08, won't improve with current signals
- **Clear direction**: Build frequency-based tools, not similarity engines

Time to stop chasing generic similarity and build what actually works.
