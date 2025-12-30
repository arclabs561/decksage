# Deck Modification: Complete Annotation Framework

**Date**: 2025-01-27  
**Status**: ✅ All Tasks Have Annotation Support

---

## Summary

Created comprehensive annotation generation framework that covers **all deck modification tasks**:

1. ✅ **Add Suggestions** - Role-aware, archetype-aware suggestions
2. ✅ **Remove Suggestions** - Weak/redundant card identification
3. ✅ **Replace Suggestions** - Alternatives, upgrades, downgrades
4. ✅ **Contextual Discovery** - Synergies, alternatives, upgrades, downgrades

**Key Insight**: Every task now has:
- Test cases with expected results
- LLM-as-Judge evaluation framework
- Ground truth annotation generation
- Regression testing capability

---

## Annotation Coverage by Task

### 1. Add Suggestions ✅

**Test Cases**:
- `empty_burn_deck`: Empty deck → core staples
- `no_removal_deck`: Missing removal → removal suggestions
- `budget_burn_deck`: Budget constraints → cheap alternatives

**Annotations Include**:
- Expected additions (ground truth)
- LLM judgments for each suggestion:
  - Relevance (0-4)
  - Explanation Quality (0-4)
  - Archetype Match (0-4)
  - Role Fit (0-4)

**Evaluation Metrics**:
- Coverage: % of expected cards that appear
- Precision: % of suggestions that are relevant (≥3)
- Explanation Quality: Average explanation score

### 2. Remove Suggestions ✅

**Test Cases**:
- `excess_removal_deck`: Too much removal → remove weakest

**Annotations Include**:
- Expected removals (ground truth)
- LLM judgments:
  - Relevance (0-4): Should this card be removed?
  - Reasoning: Why remove it?
  - Redundancy Score: How redundant is it?

**Evaluation Metrics**:
- Precision: % of removal suggestions that are correct
- False Positive Rate: % of good cards incorrectly suggested for removal

### 3. Replace Suggestions ✅

**Test Cases**:
- Replace `Opt` → `Expressive Iteration` (upgrade)
- Replace `Lightning Bolt` → `Shock` (downgrade)

**Annotations Include**:
- Expected replacements (card → alternatives)
- LLM judgments:
  - Relevance (0-4): Is this a good replacement?
  - Role Match (0-4): Does it fill the same role?
  - Price Accuracy (0-4): Is price delta correct?

**Evaluation Metrics**:
- Replacement Quality: % of replacements that are good (≥3)
- Role Preservation: % that maintain role

### 4. Contextual Discovery ✅

**Test Cases**:
- `lightning_bolt_contextual`: Synergies, alternatives, upgrades, downgrades

**Annotations Include**:
- Expected synergies, alternatives, upgrades, downgrades
- LLM judgments for each category:
  - Relevance (0-4)
  - Price Accuracy (0-4, for upgrades/downgrades)

**Evaluation Metrics**:
- Category Coverage: % of expected cards in each category
- Quality Score: Average relevance across categories

---

## Complete Workflow

### Step 1: Critique System

```bash
uv run python src/ml/evaluation/deck_modification_evaluation.py \
    --generate-annotations
```

**Outputs**:
- `experiments/deck_modification_critique.json`:
  - 15 identified issues (6 high, 7 medium, 2 low)
  - 5 test cases (4 deck modification, 1 contextual)

### Step 2: Generate Annotations

```bash
# Start API
uvicorn src.ml.api.api:app --reload

# Generate annotations
uv run python src/ml/evaluation/deck_modification_judge.py \
    --api-url http://localhost:8000 \
    --critique-path experiments/deck_modification_critique.json \
    --output-path experiments/deck_modification_annotations.json
```

**Outputs**:
- `experiments/deck_modification_annotations.json`: Ground truth annotations
- `experiments/contextual_discovery_annotations.json`: Contextual annotations

**For Each Test Case**:
1. Calls actual API to get suggestions
2. Judges each suggestion using LLM (multi-dimensional)
3. Stores judgments as ground truth
4. Includes expected cards for validation

### Step 3: Regression Testing

```bash
uv run python src/ml/evaluation/regression_test_deck_modification.py \
    --annotations experiments/deck_modification_annotations.json \
    --api-url http://localhost:8000 \
    --output regression_results.json
```

**Outputs**:
- Pass/fail report
- Detailed results per test case
- Coverage metrics
- Quality metrics

---

## Annotation Structure

### Deck Modification Annotation

```json
{
  "test_case": "empty_burn_deck",
  "game": "magic",
  "deck": {
    "partitions": [{"name": "Main", "cards": []}]
  },
  "archetype": "Burn",
  "format": "Modern",
  "expected_additions": ["Lightning Bolt", "Lava Spike", "Rift Bolt"],
  "expected_removals": [],
  "expected_replacements": {},
  "judgments": {
    "add": [
      {
        "suggested_card": "Lightning Bolt",
        "relevance": 4,
        "reasoning": "Perfect staple for Burn archetype, 95%+ inclusion rate",
        "explanation_quality": 4,
        "archetype_match": 4,
        "role_fit": 4
      }
    ],
    "remove": [],
    "replace": []
  }
}
```

### Contextual Discovery Annotation

```json
{
  "test_case": "lightning_bolt_contextual",
  "game": "magic",
  "card": "Lightning Bolt",
  "format": "Modern",
  "archetype": "Burn",
  "expected_synergies": ["Lava Spike", "Rift Bolt"],
  "expected_alternatives": ["Chain Lightning", "Shock"],
  "expected_upgrades": ["Skewer the Critics"],
  "expected_downgrades": ["Shock"],
  "judgments": {
    "synergies": [
      {
        "suggested_card": "Lava Spike",
        "relevance": 4,
        "reasoning": "High co-occurrence in Burn decks, similar function",
        "price_accuracy": null
      }
    ],
    "alternatives": [...],
    "upgrades": [...],
    "downgrades": [...]
  }
}
```

---

## Evaluation Dimensions

### For Each Suggestion

1. **Relevance** (0-4): How appropriate is this suggestion?
   - 4: Perfect/ideal
   - 3: Strong/very appropriate
   - 2: Moderate/generally appropriate
   - 1: Weak/partially appropriate
   - 0: Completely wrong/inappropriate

2. **Explanation Quality** (0-4): Is the reasoning clear and accurate?
   - 4: Excellent, clear and accurate
   - 3: Good, mostly clear
   - 2: Adequate, some clarity issues
   - 1: Poor, unclear or inaccurate
   - 0: No explanation or completely wrong

3. **Archetype Match** (0-4, if archetype provided): Does it fit the archetype?
   - 4: Perfect fit, archetype staple
   - 3: Strong fit, commonly used
   - 2: Moderate fit, sometimes used
   - 1: Weak fit, rarely used
   - 0: Doesn't fit archetype

4. **Role Fit** (0-4, if role gap identified): Does it fill a needed role?
   - 4: Perfectly fills the role gap
   - 3: Strongly fills the role gap
   - 2: Moderately fills the role gap
   - 1: Weakly fills the role gap
   - 0: Doesn't fill the role gap

5. **Price Accuracy** (0-4, for upgrades/downgrades): Is price delta accurate?
   - 4: Price delta is accurate
   - 3: Price delta is mostly accurate
   - 2: Price delta is somewhat accurate
   - 1: Price delta is inaccurate
   - 0: Price delta is completely wrong

---

## Integration Points

### With Existing Systems

1. **LLM-as-Judge**: Uses `pydantic_ai_helpers` for model selection
2. **Test Set Format**: Compatible with existing test set structure
3. **Evaluation Metrics**: Uses same relevance levels (0-4)
4. **IAA Framework**: Can use `inter_annotator_agreement.py` for multi-judge

### CI/CD Integration

```yaml
# Example GitHub Actions workflow
- name: Regression Test
  run: |
    uvicorn src.ml.api.api:app &
    sleep 5
    uv run python src/ml/evaluation/regression_test_deck_modification.py \
      --annotations experiments/deck_modification_annotations.json \
      --api-url http://localhost:8000
```

---

## Critical Issues Identified

### High Priority (6 issues)

1. **Limited Role Taxonomy**: Only 6 roles, misses many (graveyard, board wipes, etc.)
2. **No Synergy Awareness**: Removal suggestions don't check for synergies
3. **Role Overlap Threshold Too Low**: 30% might allow wrong replacements
4. **No Functional Synergy**: Contextual discovery only uses co-occurrence
5. **No Budget Prioritization**: Doesn't prioritize cheaper alternatives
6. **No Format Legality Filtering**: Might suggest illegal cards

### Medium Priority (7 issues)

1. Archetype staple threshold too high (70%)
2. No card count suggestions (always 1-of)
3. Redundancy thresholds too strict (format-agnostic)
4. Low archetype match removal too aggressive
5. No lateral upgrade mode (same price, better card)
6. No curve consideration for replacements
7. Explanations too technical for beginners

---

## Next Steps

1. ✅ **Critique Complete**: 15 issues identified
2. ✅ **Test Cases Generated**: 5 test cases created
3. ✅ **Annotation Framework Ready**: LLM-as-Judge integrated
4. ⏳ **Generate Annotations**: Run with actual API
5. ⏳ **Fix High-Priority Issues**: Implement top 6 fixes
6. ⏳ **Expand Test Cases**: Add more edge cases
7. ⏳ **CI/CD Integration**: Set up automated regression testing

---

## Files Created

1. `src/ml/evaluation/deck_modification_evaluation.py` - Critique system
2. `src/ml/evaluation/deck_modification_judge.py` - LLM-as-Judge for all tasks
3. `src/ml/evaluation/regression_test_deck_modification.py` - Regression testing
4. `DECK_MODIFICATION_CRITIQUE_AND_EVALUATION.md` - Detailed critique
5. `ANNOTATION_GENERATION_COMPLETE.md` - Annotation framework docs

---

**Status**: Complete annotation framework for all tasks. Ready to generate ground truth and set up regression testing.

