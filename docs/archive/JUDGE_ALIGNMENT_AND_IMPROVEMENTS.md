# Judge Alignment and Improvements

**Date**: 2025-01-27  
**Status**: ✅ Meta-Evaluation Complete, Improved Prompts Integrated

---

## Executive Summary

**Problem**: Judges might not be measuring what we actually care about.

**Solution**: Meta-evaluation system that:
1. Defines actual goals (ground truth)
2. Analyzes judge prompts for alignment
3. Identifies gaps and misalignments
4. Provides improved prompts
5. Creates calibration tests

**Result**: Improved prompts integrated into judge system.

---

## Key Misalignments Found

### 1. Format Legality Not Enforced

**Issue**: Prompt doesn't explicitly state that illegal cards MUST get relevance 0.

**Impact**: Judge might give relevance 2-3 to a banned card if it "fits archetype".

**Fix**: Improved prompt explicitly states: "If card is banned/not legal, relevance MUST be 0"

### 2. Budget Constraints Not Enforced

**Issue**: Prompt mentions budget but doesn't enforce it.

**Impact**: Judge might suggest $10 card when budget is $2.

**Fix**: Improved prompt explicitly states: "If budget_max provided and card exceeds it, relevance MUST be 0"

### 3. Missing Synergy Awareness

**Issue**: Removal judge doesn't check for synergies.

**Impact**: Might suggest removing Goblin Guide from Goblin deck (breaks tribal synergy).

**Fix**: Improved prompt includes: "Synergy awareness: Consider if card works WITH the deck"

### 4. Co-occurrence vs Similarity Confusion

**Issue**: Similarity judge doesn't distinguish co-occurrence from functional similarity.

**Impact**: Might judge Goblin Guide and Lightning Bolt as similar (they co-occur but aren't similar).

**Fix**: Improved prompt explicitly states: "Co-occurrence ≠ Similarity"

---

## Improved Prompts

### Deck Modification Judge

**Key Improvements**:
1. ✅ Explicit format legality enforcement
2. ✅ Explicit budget constraint enforcement
3. ✅ Clear distinction: "good card" vs "good for THIS deck"
4. ✅ Synergy awareness
5. ✅ Better calibration (clear 0-4 definitions)

**Critical Additions**:
- "If card is banned/not legal, relevance MUST be 0"
- "If budget_max provided and card exceeds it, relevance MUST be 0"
- "Distinguish between 'good card' and 'good for this deck'"
- "Consider if card works WITH the deck, not just individually"

### Similarity Judge

**Key Improvements**:
1. ✅ Explicit distinction: co-occurrence ≠ similarity
2. ✅ Substitutability requirement
3. ✅ Functional relationship emphasis
4. ✅ Clear examples for each level

**Critical Additions**:
- "Co-occurrence ≠ Similarity: Cards that appear together (synergy) are NOT similar"
- "Substitutability matters: Can you replace one with the other?"
- "Distinguish between 'similar' and 'synergistic'"

---

## Calibration Test Cases

### Test 1: Perfect Match ✅
- Burn deck, suggest Lightning Bolt
- **Expected**: All 4s
- **Tests**: Ideal case recognition

### Test 2: Clear Mismatch ✅
- Burn deck, suggest Counterspell
- **Expected**: Relevance 0
- **Tests**: Clear mismatch recognition

### Test 3: Budget Violation ✅
- Budget deck (max $2), suggest $10 card
- **Expected**: Relevance 0 (MUST be 0)
- **Tests**: Budget enforcement

### Test 4: Format Illegal ✅
- Modern deck, suggest Chain Lightning (Legacy-only)
- **Expected**: Relevance 0 (MUST be 0)
- **Tests**: Format legality enforcement

### Test 5: Synergy Awareness ✅
- Goblin deck, suggest removing Goblin Guide
- **Expected**: Relevance 1 (low - breaks synergy)
- **Tests**: Synergy awareness

---

## Actual Goals (What We Actually Care About)

### Add Suggestions
1. ✅ Card fits the deck's strategy/archetype
2. ✅ Card fills a functional gap (role awareness)
3. ✅ Card is legal in the format
4. ✅ Card fits budget constraints (if provided)
5. ⚠ Card count is appropriate (1-of vs 4-of) - **Not yet judged**
6. ✅ Explanation is clear and actionable

### Remove Suggestions
1. ✅ Card is actually weak/redundant
2. ⚠ Removal won't break synergies - **Now in improved prompt**
3. ✅ Removal won't create new gaps
4. ✅ Reasoning explains why it's safe to remove

### Replace Suggestions
1. ✅ Replacement fills the same role
2. ✅ Replacement is actually better
3. ✅ Price delta is accurate
4. ⚠ Replacement maintains deck balance - **Partially addressed**

### Contextual Discovery
1. ⚠ Synergy is functional, not just co-occurrence - **Now in improved prompt**
2. ✅ Alternative is actually equivalent
3. ✅ Upgrade is actually better
4. ✅ Downgrade maintains functionality

---

## Integration Status

### ✅ Updated Judges

1. **Deck Modification Judge**: Uses improved prompt from `improved_judge_prompts.py`
2. **Similarity Judge**: Uses improved prompt from `improved_judge_prompts.py`

### ⏳ Pending

1. **Calibration Test Runner**: Script to run calibration tests and verify alignment
2. **Judge Performance Monitoring**: Track judge quality over time
3. **Multi-Judge Consensus**: Use multiple judges and compute consensus

---

## Usage

### Run Meta-Evaluation

```bash
python3 src/ml/evaluation/meta_judge_evaluation.py
```

**Output**: `experiments/meta_judge_evaluation.json`

### View Improved Prompts

```python
from ml.evaluation.improved_judge_prompts import (
    DECK_MODIFICATION_JUDGE_PROMPT,
    SIMILARITY_JUDGE_PROMPT,
    CONTEXTUAL_DISCOVERY_JUDGE_PROMPT,
)
```

### Run Calibration Tests

```bash
# TODO: Create calibration test runner
python3 src/ml/evaluation/calibrate_judges.py
```

---

## Recommendations

### Immediate

1. ✅ **Prompts Updated**: Improved prompts integrated
2. ⏳ **Run Calibration Tests**: Verify judges align with expected judgments
3. ⏳ **Monitor Performance**: Track judge quality on calibration tests

### Long-term

1. **Multi-Judge Consensus**: Use 3+ judges and compute consensus
2. **Judge Training**: Fine-tune judges on calibration test cases
3. **Continuous Monitoring**: Track judge performance over time
4. **Human Validation**: Periodically validate against human experts

---

## Files Created

1. `src/ml/evaluation/meta_judge_evaluation.py` - Meta-evaluation system
2. `src/ml/evaluation/improved_judge_prompts.py` - Improved prompts
3. `JUDGE_ALIGNMENT_AND_IMPROVEMENTS.md` - This document

---

## Next Steps

1. ✅ **Meta-Evaluation Complete**: Identified misalignments
2. ✅ **Improved Prompts Created**: Better prompts ready
3. ✅ **Prompts Integrated**: Judges now use improved prompts
4. ⏳ **Run Calibration Tests**: Verify alignment
5. ⏳ **Monitor Performance**: Track judge quality

---

**Status**: Meta-evaluation complete. Improved prompts integrated. Ready for calibration testing.

