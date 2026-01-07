# Continuous Improvement and Testing Guide

## Overview

This document outlines the continuous improvement and testing workflow for the annotation system.

## E2E Test Suite

**Script**: `scripts/annotation/test_e2e_annotation_system.py`

**Tests**:
1. ✅ IAA Configuration - Verifies different models/params
2. Single Annotator - Baseline annotation generation
3. Multi-Annotator IAA - Synthetic IAA with consensus
4. Uncertainty Selection - Hard mining
5. Human Queue - Task queuing system
6. All Games - Magic, Pokemon, Yu-Gi-Oh support

**Run**:
```bash
uv run python3 scripts/annotation/test_e2e_annotation_system.py
```

## Continuous Improvement Loop

**Script**: `scripts/annotation/run_continuous_improvement.py`

**Process**:
1. Generate annotations with current system
2. Analyze quality (score distribution, IAA, issues)
3. Run meta-judge for feedback
4. Inject improvements into next iteration
5. Repeat

**Run**:
```bash
# Basic (3 iterations, 10 pairs each)
uv run python3 scripts/annotation/run_continuous_improvement.py --game magic

# Custom
uv run python3 scripts/annotation/run_continuous_improvement.py \
    --game magic \
    --num-pairs 20 \
    --iterations 5 \
    --no-meta-judge  # Skip meta-judge if needed
```

## Quality Metrics Tracked

1. **Score Distribution**:
   - Very low (0.0-0.2)
   - Low (0.2-0.4)
   - Medium (0.4-0.6)
   - High (0.6-0.8)
   - Very high (0.8-1.0)

2. **Diversity Metrics**:
   - Score standard deviation
   - Range utilization (how many ranges used)
   - Clustering detection (>50% in one range)

3. **IAA Metrics** (when multi-annotator enabled):
   - Krippendorff's Alpha
   - Agreement level (high/medium/low)
   - Model disagreement patterns

4. **Meta-Judge Feedback**:
   - Score clustering issues
   - Reasoning quality
   - Card attribute coverage
   - Prompt improvement suggestions

## Issues Detected Automatically

- **Score Clustering**: >50% in very_low or very_high range
- **Low Diversity**: Standard deviation < 0.15
- **Limited Range**: <3/5 ranges used
- **Low IAA**: Krippendorff's Alpha < 0.6
- **Poor Reasoning**: Meta-judge flags incomplete reasoning

## Improvement Strategies

1. **Prompt Refinement**: Based on meta-judge feedback
2. **Pair Selection**: Use uncertainty-based selection
3. **Model Parameters**: Adjust temperature for diversity
4. **IAA Integration**: Use multi-annotator for consensus
5. **Human Queue**: Queue low-IAA pairs for human review

## Testing Workflow

### Daily Testing
```bash
# Quick E2E test (no LLM calls if API key missing)
uv run python3 scripts/annotation/test_e2e_annotation_system.py
```

### Weekly Validation
```bash
# Generate and compare methods
uv run python3 scripts/annotation/run_large_scale_validation.py \
    --game magic \
    --num-pairs 50
```

### Continuous Improvement
```bash
# Iterative improvement loop
uv run python3 scripts/annotation/run_continuous_improvement.py \
    --game magic \
    --num-pairs 20 \
    --iterations 5
```

## MTurk Prepayments Update

**Issue**: Direct URL `https://requester.mturk.com/prepayments/new` no longer works (redirects to sign-in)

**Correct Process**:
1. Sign in: https://requester.mturk.com
2. Go to: Account Settings → "Prepay for MTurk HITs"
3. Enter amount and complete payment

**Alternative**: If account uses AWS billing (per your account details), charges go to AWS account automatically - no prepaid balance needed.

## Next Steps

1. ✅ E2E test suite created
2. ✅ Continuous improvement loop created
3. ✅ MTurk prepayments process updated
4. ⏳ Run E2E tests with API key
5. ⏳ Run improvement loop for all games
6. ⏳ Analyze results and refine

