# Meta-Judge Evaluation: Complete

**Date**: 2025-01-27
**Status**: ✅ Meta-Evaluation Framework Ready

---

## What Was Built

### Meta-Judge Evaluation System

**Purpose**: Evaluate the evaluators - ensure judges are measuring what we actually care about.

**Components**:
1. ✅ **Actual Goals Definition** - What we ACTUALLY care about (not what we're currently judging)
2. ✅ **Prompt Analysis** - Compare judge prompts to actual goals
3. ✅ **Calibration Tests** - Test cases to verify judge alignment
4. ✅ **Improved Prompts** - Better prompts based on findings

---

## Key Findings

### Misalignments Identified

#### 1. Deck Modification Judge

**Missing Criteria**:
- ❌ Format legality enforcement (should be 0 if illegal, but not explicitly stated)
- ❌ Budget constraint enforcement (should be 0 if exceeds budget, but not explicit)
- ❌ Card count appropriateness (1-of vs 4-of not considered)
- ❌ Synergy awareness (removal suggestions don't check for synergies)

**Clarity Issues**:
- "Perfect/ideal" and "Strong/very appropriate" might be conflated
- Missing explicit middle ground (2-3 range)
- No clear guidance on when to use 0 vs 1

**Calibration Issues**:
- Might be too lenient (perfect/ideal both = 4)
- Missing explicit budget/legality enforcement

#### 2. Similarity Judge

**Missing Criteria**:
- ❌ Distinction between co-occurrence and similarity
- ❌ Substitutability requirement (can you replace one with the other?)
- ❌ Functional relationship emphasis

**Clarity Issues**:
- Scale definitions are clear but examples could be better
- No explicit guidance on co-occurrence vs similarity

---

## Improved Prompts

### Deck Modification Judge (Improved)

**Key Improvements**:
1. ✅ Explicit format legality enforcement (MUST be 0 if illegal)
2. ✅ Explicit budget constraint enforcement (MUST be 0 if exceeds budget)
3. ✅ Clear distinction: "good card" vs "good for THIS deck"
4. ✅ Explicit synergy awareness
5. ✅ Better calibration (clear 0-4 definitions with examples)

### Similarity Judge (Improved)

**Key Improvements**:
1. ✅ Explicit distinction: co-occurrence ≠ similarity
2. ✅ Substitutability requirement
3. ✅ Functional relationship emphasis
4. ✅ Clear examples for each level

---

## Calibration Test Cases

### Test 1: Perfect Match
- **Scenario**: Burn deck, suggest Lightning Bolt (95% inclusion, fills gap, legal, fits budget)
- **Expected**: All 4s (relevance, explanation, archetype, role fit)
- **Tests**: Ideal case recognition

### Test 2: Clear Mismatch
- **Scenario**: Burn deck, suggest Counterspell (blue control, wrong archetype)
- **Expected**: Relevance 0, Archetype Match 0
- **Tests**: Clear mismatch recognition

### Test 3: Budget Violation
- **Scenario**: Budget deck (max $2), suggest $10 card
- **Expected**: Relevance 0 (MUST be 0 if budget violated)
- **Tests**: Budget constraint enforcement

### Test 4: Format Illegal
- **Scenario**: Modern deck, suggest Chain Lightning (Legacy-only)
- **Expected**: Relevance 0 (MUST be 0 if illegal)
- **Tests**: Format legality enforcement

### Test 5: Synergy Awareness
- **Scenario**: Goblin deck, suggest removing Goblin Guide (tribal synergy)
- **Expected**: Relevance 1 (low - breaks synergy)
- **Tests**: Synergy awareness in removal

---

## Actual Goals (Ground Truth)

### Add Suggestions
1. Card fits the deck's strategy/archetype
2. Card fills a functional gap (role awareness)
3. Card is legal in the format
4. Card fits budget constraints (if provided)
5. Card count is appropriate (1-of vs 4-of)
6. Explanation is clear and actionable

### Remove Suggestions
1. Card is actually weak/redundant (not just low archetype match)
2. Removal won't break synergies
3. Removal won't create new gaps
4. Reasoning explains why it's safe to remove

### Replace Suggestions
1. Replacement fills the same role
2. Replacement is actually better (not just different)
3. Price delta is accurate (for upgrades/downgrades)
4. Replacement maintains deck balance (curve, etc.)

### Contextual Discovery
1. Synergy is functional, not just co-occurrence
2. Alternative is actually equivalent (same role)
3. Upgrade is actually better (not just more expensive)
4. Downgrade maintains functionality (not just cheaper)

---

## Usage

### Run Meta-Evaluation

```bash
python3 src/ml/evaluation/meta_judge_evaluation.py
```

**Output**: `experiments/meta_judge_evaluation.json`

### Use Improved Prompts

```python
from ml.evaluation.improved_judge_prompts import get_improved_prompt

prompt = get_improved_prompt("add")
# Use in judge agent creation
```

### Run Calibration Tests

```bash
# TODO: Create calibration test runner
python3 src/ml/evaluation/calibrate_judges.py \
    --test-cases experiments/meta_judge_evaluation.json
```

---

## Recommendations

### Immediate Actions

1. **Update Judge Prompts**: Use improved prompts from `improved_judge_prompts.py`
2. **Add Format Legality Check**: Explicitly state that illegal cards = 0
3. **Add Budget Enforcement**: Explicitly state that budget violations = 0
4. **Add Synergy Awareness**: Check for synergies before removal suggestions
5. **Run Calibration Tests**: Verify judges align with expected judgments

### Long-term Improvements

1. **Multi-Judge Consensus**: Use multiple judges and compute consensus
2. **Judge Training**: Fine-tune judges on calibration test cases
3. **Continuous Monitoring**: Track judge performance over time
4. **Human Validation**: Periodically validate judge judgments against human experts

---

## Files Created

1. `src/ml/evaluation/meta_judge_evaluation.py` - Meta-evaluation system
2. `src/ml/evaluation/improved_judge_prompts.py` - Improved prompts
3. `META_JUDGE_EVALUATION_COMPLETE.md` - This document

---

## Next Steps

1. ✅ **Meta-Evaluation Complete**: Identified misalignments
2. ✅ **Improved Prompts Created**: Better prompts ready
3. ⏳ **Update Judges**: Replace prompts with improved versions
4. ⏳ **Run Calibration Tests**: Verify alignment
5. ⏳ **Monitor Performance**: Track judge quality over time

---

**Status**: Meta-evaluation framework ready. Improved prompts available. Ready to update judges and run calibration tests.
