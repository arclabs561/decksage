# Temporal Evaluation Dimensions: First-Class Concern

**Date**: 2025-01-27
**Status**: ✅ Temporal Dimensions Identified and Integrated

---

## Executive Summary

**Critical Finding**: We've been evaluating recommendations without considering **when** they were made or the **state of the game at that time**. This is a first-class concern that affects evaluation validity.

**8 New Temporal Dimensions Identified**:
- **1 Critical**: Temporal context appropriateness
- **4 High**: Meta shift awareness, price volatility awareness, ban timeline awareness, recommendation timestamp validity
- **2 Medium**: Format rotation awareness, seasonal meta awareness
- **1 High**: Context-dependent quality

---

## The Temporal Problem

### What We Were Missing

**Example**: Recommending Oko, Thief of Crowns
- **2019 (September)**: Perfect recommendation - legal, meta-defining, reasonable price
- **2020 (January)**: Banned in multiple formats - recommendation is now invalid
- **2024**: Still banned - recommendation would be completely wrong

**Without temporal context**, we can't distinguish between:
- A good recommendation made at the right time
- A bad recommendation made at the wrong time
- A good recommendation that became bad due to context changes

---

## Temporal Dimensions

### 1. Temporal Context Appropriateness (Critical)

**What It Measures**: Was this recommendation appropriate for the time/context it was made?

**Why Critical**: A recommendation that was good in 2019 might be terrible in 2024 due to bans, meta shifts, or price changes.

**How to Measure**:
- Was card legal at recommendation time?
- Was price reasonable then?
- Was it meta-relevant then?
- Did format/ban list change since?

**Example**: Recommending Oko in 2019 (good) vs 2020 (banned) - temporal context matters

**Current Coverage**: Not judged

---

### 2. Meta Shift Awareness (High)

**What It Measures**: Does the recommendation account for current meta state vs historical?

**Why Important**: What was good 6 months ago might not be good now. Meta shifts constantly.

**How to Measure**:
- Compare recommendation to recent meta (last 1-3 months) vs older data
- Check if it accounts for meta shifts
- Does it use recent data or only historical?

**Example**: Recommending card that was good 6 months ago but meta has shifted (outdated recommendation)

**Current Coverage**: Partially judged (we have temporal signals but don't evaluate if they're used correctly)

---

### 3. Price Volatility Awareness (High)

**What It Measures**: Was the price reasonable at recommendation time? (cards spike, crash, reprints change availability)

**Why Important**: A card that spiked 10x the day before recommendation is not available at reasonable price.

**How to Measure**:
- Check price history: Was card spiking when recommended?
- Was it recently reprinted? (reprints = cheaper)
- Price stability matters

**Example**: Recommending card that spiked 10x the day before (should flag as volatile/unavailable)

**Current Coverage**: Not judged

---

### 4. Ban Timeline Awareness (High)

**What It Measures**: Was the card legal at recommendation time? (ban list changes over time)

**Why Important**: A card that was legal when recommended but got banned 2 weeks later is problematic.

**How to Measure**:
- Check ban list history: Was card legal at recommendation timestamp?
- Did it get banned after?
- Does recommendation account for recent ban list changes?

**Example**: Recommending card that was legal when suggested but got banned 2 weeks later (temporal legality issue)

**Current Coverage**: Not judged

---

### 5. Recommendation Timestamp Validity (High)

**What It Measures**: Is the recommendation timestamped? Can we evaluate it in temporal context?

**Why Important**: Without timestamps, we can't evaluate temporal appropriateness.

**How to Measure**:
- Check if recommendation includes timestamp
- Can we reconstruct game state at that time?
- Do we have format state, meta state, price state at that time?

**Example**: Recommendation without timestamp - can't evaluate if it was appropriate for its time

**Current Coverage**: Not judged

---

### 6. Format Rotation Awareness (Medium)

**What It Measures**: Does recommendation account for format rotation? (Standard rotates, new sets change formats)

**Why Important**: Recommending a Standard card 1 week before rotation is not helpful.

**How to Measure**:
- Check if recommendation considers format rotation dates
- New set releases
- Format changes

**Example**: Recommending Standard card 1 week before rotation (should flag as rotating soon)

**Current Coverage**: Not judged

---

### 7. Seasonal/Meta Cycle Awareness (Medium)

**What It Measures**: Does recommendation account for seasonal meta patterns? (GP season, PTQ season, different metas)

**Why Important**: Meta has seasonal patterns (GP season vs off-season) but we don't evaluate this.

**How to Measure**:
- Check if recommendation aligns with seasonal meta patterns
- Tournament schedule
- Meta cycles

**Example**: Recommending GP-season card during off-season (meta mismatch)

**Current Coverage**: Not judged

---

### 8. Context-Dependent Quality (High)

**What It Measures**: Is the recommendation quality evaluated in its specific context? (same card, different times/contexts = different quality)

**Why Important**: We evaluate recommendations generically, not accounting for specific temporal/contextual factors.

**How to Measure**:
- Evaluate recommendation quality relative to: timestamp, format state, meta state, price state at that time
- Compare quality in context vs quality if recommended now

**Example**: Same card recommended in 2019 (good) vs 2020 (banned) - should have different quality scores

**Current Coverage**: Not judged

---

## Implementation

### Temporal Evaluation System

Created `src/ml/evaluation/temporal_evaluation_dimensions.py` with:
- `TemporalContext`: Captures game state at recommendation time
- `TemporalEvaluation`: Comprehensive temporal evaluation
- `evaluate_temporal_appropriateness`: Main evaluation function

### Expanded Judge Prompts

Updated `src/ml/evaluation/expanded_judge_criteria.py` to include:
- Temporal Context Appropriateness (0-4)
- Meta Shift Awareness (0-4)
- Price Volatility Awareness (0-4)
- Ban Timeline Awareness (0-4)
- Format Rotation Awareness (0-4)

---

## Recommendations

### Immediate Actions

1. **Add Timestamps to All Recommendations**: Every recommendation must include timestamp
2. **Track Game State Over Time**: Format state, meta state, price state at each timestamp
3. **Evaluate in Temporal Context**: Judge recommendations relative to their time, not just generically
4. **Flag Temporal Issues**: Identify recommendations that became invalid due to context changes

### Short-term Actions

1. **Implement Temporal Evaluation**: Use `temporal_evaluation_dimensions.py` for all recommendations
2. **Add Temporal Dimensions to Judges**: Update judge prompts to include temporal criteria
3. **Track Context Changes**: Monitor what changed since recommendation (bans, price spikes, meta shifts)
4. **Warn About Temporal Issues**: Flag recommendations with temporal problems

### Long-term Actions

1. **Temporal-Aware Recommendations**: Make recommendations that account for temporal factors
2. **Context-Dependent Quality Scores**: Quality scores that vary by temporal context
3. **Temporal Regression Testing**: Test that recommendations remain valid over time
4. **Meta Shift Prediction**: Predict meta shifts and adjust recommendations accordingly

---

## Files Created

1. `src/ml/evaluation/temporal_evaluation_dimensions.py` - Temporal evaluation system
2. `TEMPORAL_EVALUATION_DIMENSIONS.md` - This document

---

## Updated Missing Dimensions

**Total Missing Dimensions**: 23 (was 15, added 8 temporal dimensions)

**Breakdown**:
- **2 Critical**: Deck balance, Temporal context appropriateness
- **11 High**: Power level, availability, synergy strength, meta positioning, cost-effectiveness, sideboard optimization, role overlap, meta shift awareness, price volatility awareness, ban timeline awareness, context-dependent quality
- **7 Medium**: Upgrade path, consistency, theme, actionability, combo pieces, format rotation, seasonal meta
- **3 Low**: Learning value, format transition, recommendation timestamp validity

---

**Status**: Temporal dimensions identified and integrated. Ready to implement temporal evaluation system.
