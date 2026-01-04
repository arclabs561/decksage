# Automated Deck Modification Evaluation: Complete

**Date**: 2025-01-27
**Status**: ✅ Fully Automated Pipeline Ready

---

## What Was Built

### Automated Evaluation Pipeline

**Single Command Execution**:
```bash
python3 src/ml/scripts/automated_deck_modification_evaluation.py
```

**Or with Shell Script**:
```bash
./src/ml/scripts/run_full_evaluation.sh
```

**Pipeline Steps**:
1. ✅ Generate critique and test cases
2. ✅ Generate annotations (with API if available, templates otherwise)
3. ✅ Run regression tests (if API available)
4. ✅ Generate summary report

---

## Automation Features

### 1. API Detection

- Automatically detects if API is running
- Waits for API to become available (configurable timeout)
- Falls back to template generation if API unavailable

### 2. Error Handling

- Graceful degradation if API unavailable
- Template generation as fallback
- Continues pipeline even if one step fails

### 3. Comprehensive Output

**Generated Files**:
- `experiments/deck_modification_critique.json` - Critique and test cases
- `experiments/deck_modification_annotations.json` - Annotations (or templates)
- `experiments/deck_modification_regression_results.json` - Regression test results
- `experiments/deck_modification_evaluation_report.md` - Summary report

---

## Usage

### Basic (Templates Only)

```bash
python3 src/ml/scripts/automated_deck_modification_evaluation.py
```

**Output**: Critique, test cases, and annotation templates

### With API (Full Evaluation)

```bash
# Start API in another terminal
uvicorn src.ml.api.api:app --reload

# Run evaluation
python3 src/ml/scripts/automated_deck_modification_evaluation.py \
    --api-url http://localhost:8000 \
    --wait-for-api
```

**Output**: Full evaluation with actual API calls and judgments

### Shell Script (Easiest)

```bash
# Set API URL if needed
export API_URL=http://localhost:8000

# Run
./src/ml/scripts/run_full_evaluation.sh
```

---

## Pipeline Details

### Step 1: Critique Generation

- Runs `DeckModificationEvaluator`
- Identifies 16 issues (5 high, 8 medium, 3 low)
- Generates 5 test cases
- Saves to `deck_modification_critique.json`

### Step 2: Annotation Generation

**If API Available**:
- Calls API for each test case
- Judges each suggestion using LLM
- Stores judgments as ground truth

**If API Unavailable**:
- Generates template structure
- Includes expected cards
- Ready for later annotation

### Step 3: Regression Testing

**If API Available**:
- Compares current API to ground truth
- Tracks pass/fail rates
- Identifies regressions

**If API Unavailable**:
- Skipped (can run later)

### Step 4: Summary Report

- Combines all results
- Highlights high-priority issues
- Lists test cases
- Shows annotation status
- Includes regression results (if available)

---

## Output Files

### `deck_modification_critique.json`

```json
{
  "critiques": [ /* 16 issues */ ],
  "test_cases": [ /* 4 deck modification cases */ ],
  "contextual_test_cases": [ /* 1 contextual case */ ],
  "summary": {
    "total_critiques": 16,
    "high": 5,
    "medium": 8,
    "low": 3,
    "total_test_cases": 5
  }
}
```

### `deck_modification_annotations.json`

```json
[
  {
    "test_case": "empty_burn_deck",
    "game": "magic",
    "deck": { /* deck */ },
    "expected_additions": ["Lightning Bolt", "Lava Spike"],
    "judgments": {
      "add": [ /* LLM judgments */ ],
      "remove": [],
      "replace": []
    }
  }
]
```

### `deck_modification_evaluation_report.md`

Markdown report with:
- Critique summary
- High-priority issues
- Test cases
- Annotation status
- Regression results

---

## Integration with CI/CD

### GitHub Actions Example

```yaml
name: Deck Modification Evaluation

on:
  schedule:
    - cron: '0 0 * * 0'  # Weekly
  workflow_dispatch:

jobs:
  evaluate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: |
          pip install uv
          uv sync
      - run: |
          uvicorn src.ml.api.api:app &
          sleep 10
          python3 src/ml/scripts/automated_deck_modification_evaluation.py \
            --api-url http://localhost:8000
      - uses: actions/upload-artifact@v3
        with:
          name: evaluation-results
          path: experiments/deck_modification_*
```

---

## Next Steps

1. ✅ **Automation Complete**: Single command runs everything
2. ⏳ **Run with API**: Generate actual annotations
3. ⏳ **Set up CI/CD**: Automated weekly evaluation
4. ⏳ **Track Metrics**: Monitor pass rates over time
5. ⏳ **Fix Issues**: Implement high-priority fixes

---

## Files Created

1. `src/ml/scripts/automated_deck_modification_evaluation.py` - Main automation script
2. `src/ml/scripts/run_full_evaluation.sh` - Shell script wrapper
3. `AUTOMATED_EVALUATION_COMPLETE.md` - This document

---

**Status**: Fully automated pipeline ready. Run with single command to generate critique, annotations, and regression tests.
