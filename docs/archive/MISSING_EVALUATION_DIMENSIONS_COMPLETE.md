# Missing Evaluation Dimensions: Complete Analysis

**Date**: 2025-01-27
**Status**: ✅ Comprehensive Gap Analysis Complete

---

## Executive Summary

**15 Missing Dimensions Identified**:
- **1 Critical**: Deck balance (we don't judge this at all)
- **7 High**: Power level, card availability, synergy strength, meta positioning, cost-effectiveness, sideboard optimization, replacement role overlap
- **5 Medium**: Upgrade path coherence, consistency improvement, theme consistency, explanation actionability, combo piece identification
- **2 Low**: Learning value, format transition readiness

**Coverage Analysis**:
- **9 Not Judged**: Completely missing from evaluation
- **5 Partially Judged**: Implicitly covered but not explicit
- **1 Implicitly Judged**: Covered through other dimensions

---

## Critical Missing Dimensions

### 1. Deck Balance (Critical)

**What We're Missing**: We judge individual cards but not their impact on overall deck structure.

**Why It Matters**: Adding cards without considering curve, land count, or color distribution can break a deck.

**How to Measure**:
- Calculate deck stats before/after: avg CMC, land count, color distribution
- Compare to archetype norms
- Check if suggestion maintains/improves balance

**Example Test Case**: Adding 4 Lightning Bolt to a deck with 18 lands (should suggest land count adjustment)

**Current Coverage**: Not judged at all

---

## High Priority Missing Dimensions

### 2. Power Level Match (High)

**What We're Missing**: We judge archetype fit but not power level appropriateness.

**Why It Matters**: Casual and competitive decks have different power levels. Suggesting a competitive card to a casual deck (or vice versa) is a mismatch.

**How to Measure**: Compare card's typical format usage (casual/competitive) to deck's intended power level.

**Example**: Suggesting Sol Ring to a casual kitchen table deck (power level mismatch)

**Current Coverage**: Implicitly judged through archetype match, but not explicit

### 3. Card Availability (High)

**What We're Missing**: We assume cards are available, but some are out of print or spiked.

**Why It Matters**: Suggesting a card that spiked 10x in price last week is not helpful.

**How to Measure**: Check card printings, recent price history, stock status.

**Example**: Suggesting a card that spiked 10x in price last week (unavailable at reasonable price)

**Current Coverage**: Not judged

### 4. Synergy Strength (High)

**What We're Missing**: We identify synergies but don't judge their strength.

**Why It Matters**: Weak synergies (nice to have) vs strong synergies (combo pieces) are very different.

**How to Measure**: Categorize: weak (nice to have), moderate (good together), strong (synergistic), combo (essential).

**Example**: Suggesting 'Goblin' card for Goblin deck (weak synergy) vs 'Goblin Chieftain' (strong synergy)

**Current Coverage**: Partially judged (we identify synergies but don't rate strength)

### 5. Meta Positioning (High)

**What We're Missing**: Competitive users care about meta, but we don't evaluate this.

**Why It Matters**: Does this improve the deck's position in the meta? Better matchups, meta share.

**How to Measure**: Check if card improves win rate vs top decks, if it's meta-relevant.

**Example**: Suggesting sideboard card that improves Tron matchup (meta positioning)

**Current Coverage**: Not judged

### 6. Cost-Effectiveness (High)

**What We're Missing**: We check budget constraints but don't evaluate cost-effectiveness.

**Why It Matters**: Budget users care about power per dollar, not just staying under budget.

**How to Measure**: Compare card's power level to its price, compare to alternatives.

**Example**: Suggesting $10 card when $2 alternative is 90% as good (poor cost-effectiveness)

**Current Coverage**: Not judged

### 7. Sideboard Optimization (High)

**What We're Missing**: We suggest maindeck cards but don't evaluate sideboard appropriateness.

**Why It Matters**: Competitive players need sideboard cards that answer meta threats.

**How to Measure**: Check if card answers common meta threats, if it's flexible (not narrow).

**Example**: Suggesting Grafdigger's Cage for sideboard (answers graveyard decks)

**Current Coverage**: Not judged

### 8. Replacement Role Overlap Quantified (High)

**What We're Missing**: We check if roles match but don't quantify overlap percentage.

**Why It Matters**: 95% role overlap (near substitute) vs 60% overlap (related but different) are very different.

**How to Measure**: Calculate role overlap: % of functions that overlap between old and new card.

**Example**: Replacing Lightning Bolt with Chain Lightning (95% overlap) vs Lava Spike (60% overlap)

**Current Coverage**: Partially judged (we check role_match but don't quantify)

---

## Medium Priority Missing Dimensions

### 9. Upgrade Path Coherence (Medium)

**What We're Missing**: We suggest upgrades but don't evaluate if the path is coherent.

**Why It Matters**: Can you afford it? Does it lead somewhere? Is the path logical?

**How to Measure**: Check if upgrade is affordable given budget, if it leads to a coherent deck.

**Example**: Suggesting $50 upgrade when budget is $20 (incoherent path)

**Current Coverage**: Partially judged (we check budget but not path coherence)

### 10. Consistency Improvement (Medium)

**What We're Missing**: Competitive players value consistency, but we don't evaluate this.

**Why It Matters**: Does this reduce deck variance? More consistent draws, less mulligans.

**How to Measure**: Analyze deck's mana curve, card draw, filtering - does suggestion improve consistency?

**Example**: Adding card draw to a deck with high variance (consistency improvement)

**Current Coverage**: Not judged

### 11. Theme Consistency (Medium)

**What We're Missing**: Casual players value theme, but we only check archetype (competitive theme).

**Why It Matters**: Does this maintain the deck's theme? Tribal, flavor, mechanical theme.

**How to Measure**: Check if card fits theme: tribal (same creature type), flavor (same plane/set), mechanical (same mechanic).

**Example**: Suggesting non-Goblin card to Goblin tribal deck (theme violation)

**Current Coverage**: Partially judged (through archetype, but not explicit theme)

### 12. Explanation Actionability (Medium)

**What We're Missing**: We judge explanation quality but not whether it's actionable.

**Why It Matters**: Can the user act on this explanation? Specific vs vague.

**How to Measure**: Check if explanation provides specific next steps vs vague advice.

**Example**: 'Add 2 more lands' (actionable) vs 'Improve your mana base' (not actionable)

**Current Coverage**: Partially judged (through explanation_quality, but not explicit)

### 13. Combo Piece Identification (Medium)

**What We're Missing**: Combo players need combo pieces, but we don't identify them.

**Why It Matters**: Is this a combo piece? Enables combos, protects combos, tutors for combos.

**How to Measure**: Check if card is part of known combos, if it enables/protects combos.

**Example**: Suggesting Kiki-Jiki for Twin combo (combo piece identification)

**Current Coverage**: Not judged

---

## Low Priority Missing Dimensions

### 14. Explanation Learning Value (Low)

**What We're Missing**: We judge explanation quality but not learning value.

**Why It Matters**: Does the explanation help the user learn? Teaches deck building, not just 'this is good'.

**How to Measure**: Check if explanation teaches concepts (role, synergy, meta) vs just stating facts.

**Example**: Explanation: 'This fills your removal gap' (learning) vs 'This is good' (not learning)

**Current Coverage**: Partially judged (through explanation_quality, but not explicit)

### 15. Format Transition Readiness (Low)

**What We're Missing**: Advanced users want format transitions, but we don't evaluate this.

**Why It Matters**: Does this help transition to a different format? Modern → Legacy.

**How to Measure**: Check if card is legal in target format, if it fits target format's meta.

**Example**: Suggesting Modern-legal card that's also Legacy-playable (transition ready)

**Current Coverage**: Not judged

---

## Recommendations

### Immediate Actions (Critical + High)

1. **Add Deck Balance Evaluation**: Calculate deck stats before/after, compare to norms
2. **Add Power Level Match**: Explicitly judge if card matches deck's power level
3. **Add Card Availability Check**: Verify card is actually available (printings, price, stock)
4. **Add Synergy Strength Rating**: Categorize synergies (weak/moderate/strong/combo)
5. **Add Meta Positioning**: For competitive decks, check if card improves meta position
6. **Add Cost-Effectiveness**: For budget users, evaluate power per dollar
7. **Add Sideboard Appropriateness**: Evaluate if card is good sideboard material
8. **Quantify Role Overlap**: Calculate % overlap for replacements, not just binary match

### Short-term Actions (Medium)

1. **Add Upgrade Path Coherence**: Check if upgrade path is affordable and logical
2. **Add Consistency Improvement**: Evaluate if suggestion reduces deck variance
3. **Add Theme Consistency**: For theme decks, check if card maintains theme
4. **Add Explanation Actionability**: Judge if explanation provides actionable steps
5. **Add Combo Piece Identification**: Identify if card enables/protects combos

### Long-term Actions (Low)

1. **Add Learning Value**: Judge if explanation teaches deck building concepts
2. **Add Format Transition Readiness**: Evaluate if card helps format transitions

---

## Expanded Judge Prompts

Created expanded judge prompts in `src/ml/evaluation/expanded_judge_criteria.py` that include:
- All missing dimensions
- Explicit scoring rubrics for each dimension
- Clear examples and test cases
- Critical considerations for edge cases

**Usage**: Replace current judge prompts with expanded versions to evaluate all dimensions.

---

## Files Created

1. `src/ml/evaluation/missing_evaluation_dimensions.py` - Gap analysis system
2. `src/ml/evaluation/expanded_judge_criteria.py` - Expanded judge prompts
3. `experiments/missing_evaluation_dimensions.json` - Analysis results
4. `MISSING_EVALUATION_DIMENSIONS_COMPLETE.md` - This document

---

## Next Steps

1. ✅ **Gap Analysis Complete**: Identified 15 missing dimensions
2. ✅ **Expanded Prompts Created**: Comprehensive judge prompts ready
3. ⏳ **Integrate Expanded Prompts**: Update judges to use expanded criteria
4. ⏳ **Implement Measurement Logic**: Add code to calculate missing dimensions
5. ⏳ **Create Test Cases**: Generate test cases for each missing dimension
6. ⏳ **Run Calibration Tests**: Verify judges align with expanded criteria

---

**Status**: Comprehensive gap analysis complete. Expanded judge prompts ready. Ready to integrate and implement measurement logic.
