# Deck Modification: Annotation Generation Complete

**Date**: 2025-01-27  
**Status**: ✅ Annotation Framework Ready

---

## Summary

Created comprehensive annotation generation framework for **all deck modification tasks**:
1. ✅ Add suggestions (with role awareness, archetype matching)
2. ✅ Remove suggestions (weak cards, redundancy)
3. ✅ Replace suggestions (alternatives, upgrades, downgrades)
4. ✅ Contextual discovery (synergies, alternatives, upgrades, downgrades)

---

## What Was Built

### 1. Critique System (`deck_modification_evaluation.py`)

**Identified 15 issues**:
- 0 Critical
- 6 High severity
- 7 Medium severity
- 2 Low severity

**Generated 5 test cases**:
- `empty_burn_deck`: Empty deck should suggest core staples
- `no_removal_deck`: Deck missing removal should prioritize removal
- `excess_removal_deck`: Deck with excess removal should suggest removing weakest
- `budget_burn_deck`: Budget deck should prioritize cheap cards
- `lightning_bolt_contextual`: Format staple with clear synergies/alternatives

### 2. LLM-as-Judge System (`deck_modification_judge.py`)

**Features**:
- Structured judgment output (Pydantic models)
- Multi-dimensional evaluation:
  - Relevance (0-4)
  - Explanation Quality (0-4)
  - Archetype Match (0-4, if archetype provided)
  - Role Fit (0-4, if role gap identified)
  - Price Accuracy (0-4, for upgrades/downgrades)
- Handles all task types: add, remove, replace, contextual

### 3. Annotation Generation Pipeline

**For Each Test Case**:
1. Calls actual API (if URL provided) or generates templates
2. Judges each suggestion using LLM
3. Stores judgments as ground truth
4. Includes expected cards for validation

**Output Format**:
```json
{
  "test_case": "empty_burn_deck",
  "game": "magic",
  "deck": { /* deck */ },
  "archetype": "Burn",
  "format": "Modern",
  "expected_additions": ["Lightning Bolt", "Lava Spike"],
  "judgments": {
    "add": [
      {
        "suggested_card": "Lightning Bolt",
        "relevance": 4,
        "reasoning": "Perfect staple for Burn",
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

### 4. Regression Testing Framework (`regression_test_deck_modification.py`)

**Features**:
- Compares current API responses to ground truth annotations
- Tracks pass/fail rates
- Identifies regressions (cards that should be suggested but aren't)
- Generates detailed reports

---

## Usage

### Step 1: Generate Critique and Test Cases

```bash
uv run python src/ml/evaluation/deck_modification_evaluation.py \
    --generate-annotations
```

**Output**: `experiments/deck_modification_critique.json`

### Step 2: Generate Annotations (with API)

```bash
# Start API first
uvicorn src.ml.api.api:app --reload

# Generate annotations
uv run python src/ml/evaluation/deck_modification_judge.py \
    --api-url http://localhost:8000 \
    --critique-path experiments/deck_modification_critique.json \
    --output-path experiments/deck_modification_annotations.json
```

**Output**: `experiments/deck_modification_annotations.json`

### Step 3: Run Regression Tests

```bash
uv run python src/ml/evaluation/regression_test_deck_modification.py \
    --annotations experiments/deck_modification_annotations.json \
    --api-url http://localhost:8000 \
    --output regression_results.json
```

**Output**: Pass/fail report with detailed results

---

## Annotation Structure

### Deck Modification Annotations

```json
{
  "test_case": "test_name",
  "game": "magic",
  "deck": { /* deck object */ },
  "archetype": "Burn",
  "format": "Modern",
  "expected_additions": ["Lightning Bolt"],
  "expected_removals": ["Opt"],
  "expected_replacements": {
    "Opt": ["Expressive Iteration", "Consider"]
  },
  "judgments": {
    "add": [ /* DeckModificationJudgment objects */ ],
    "remove": [ /* DeckModificationJudgment objects */ ],
    "replace": [ /* DeckModificationJudgment objects */ ]
  }
}
```

### Contextual Discovery Annotations

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
    "synergies": [ /* ContextualJudgment objects */ ],
    "alternatives": [ /* ContextualJudgment objects */ ],
    "upgrades": [ /* ContextualJudgment objects */ ],
    "downgrades": [ /* ContextualJudgment objects */ ]
  }
}
```

---

## Evaluation Metrics

### For Each Suggestion

1. **Relevance** (0-4): How appropriate is this suggestion?
2. **Explanation Quality** (0-4): Is the reasoning clear and accurate?
3. **Archetype Match** (0-4): Does it fit the archetype? (if provided)
4. **Role Fit** (0-4): Does it fill a needed role? (if role gap identified)
5. **Price Accuracy** (0-4): For upgrades/downgrades, is price delta accurate?

### Aggregated Metrics

- **Pass Rate**: % of suggestions that meet quality threshold (relevance ≥ 3)
- **Coverage**: % of expected cards that appear in suggestions
- **Precision**: % of suggestions that are relevant (relevance ≥ 3)
- **Explanation Quality**: Average explanation quality score

---

## Integration with Existing Systems

### LLM-as-Judge Integration

Uses existing `pydantic_ai_helpers`:
- `get_default_model("judge")` for model selection
- Structured output via Pydantic models
- Error handling and retry logic

### Test Set Format

Compatible with existing test set format:
- Can convert annotations to test set format
- Uses same relevance levels (0-4)
- Can be used with existing evaluation scripts

---

## Next Steps

1. ✅ **Critique Complete**: 15 issues identified
2. ✅ **Test Cases Generated**: 5 test cases created
3. ✅ **Annotation Framework Ready**: LLM-as-Judge integrated
4. ⏳ **Generate Annotations**: Run with actual API to create ground truth
5. ⏳ **Regression Testing**: Set up CI/CD to run regression tests
6. ⏳ **Expand Test Cases**: Add more edge cases based on critiques

---

## Files Created

1. `src/ml/evaluation/deck_modification_evaluation.py` - Critique system
2. `src/ml/evaluation/deck_modification_judge.py` - LLM-as-Judge for annotations
3. `src/ml/evaluation/regression_test_deck_modification.py` - Regression testing
4. `DECK_MODIFICATION_CRITIQUE_AND_EVALUATION.md` - Detailed critique report

---

**Status**: Annotation framework complete. Ready to generate ground truth annotations and set up regression testing.

