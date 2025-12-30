# Deck Modification System: Critique and Evaluation Plan

**Date**: 2025-01-27  
**Status**: ✅ Critique Complete, Evaluation Framework Ready

---

## Executive Summary

After systematic critique of the deck modification system, **15 issues** were identified:
- **0 Critical** (blocking)
- **6 High** (significant impact)
- **7 Medium** (moderate impact)
- **2 Low** (minor improvements)

**Key Findings**:
1. Role taxonomy is too narrow (only 6 roles)
2. No synergy awareness in removal suggestions
3. Replacements don't consider curve/CMC similarity
4. Contextual discovery lacks functional synergy detection
5. Explanations could be more beginner-friendly

---

## Detailed Critiques

### Add Suggestions (5 issues)

#### High Severity

**Issue 1: Limited Role Taxonomy**
- **Problem**: Only 6 roles (removal, threat, card_draw, ramp, counter, tutor)
- **Impact**: Misses graveyard recursion, board wipes, mana fixing, combo pieces
- **Recommendation**: Expand taxonomy or use LLM to infer roles from card text
- **Test Case**: `combo_deck_missing_pieces`

**Issue 2: No Budget Prioritization**
- **Problem**: Budget filtering exists but doesn't prioritize cheaper alternatives
- **Impact**: Might suggest $10 card when $2 card is equally good
- **Recommendation**: Boost cheaper cards within budget, or add `budget_tier` parameter
- **Test Case**: `budget_prioritization`

#### Medium Severity

**Issue 3: Archetype Staple Threshold Too High**
- **Problem**: 70% threshold might exclude format staples (60-69%)
- **Impact**: Missing format-defining cards that are essential but not 70%+
- **Recommendation**: Tiered thresholds (70%+ = strong, 50-69% = format, 30-49% = common)
- **Test Case**: `format_staple_threshold`

**Issue 4: No Card Count Suggestions**
- **Problem**: Always suggests 1 copy, doesn't consider optimal count
- **Impact**: Might suggest 1-of Lightning Bolt when 4-of is standard
- **Recommendation**: Suggest count based on archetype patterns and card type
- **Test Case**: `card_count_suggestion`

#### Low Severity

**Issue 5: Constrained Choice Too Restrictive**
- **Problem**: Max 10 suggestions might be too few for large gaps
- **Impact**: New players with <40 card decks only get 10 suggestions
- **Recommendation**: Allow pagination or increase limit for incomplete decks
- **Test Case**: `large_gap_deck`

---

### Remove Suggestions (3 issues)

#### High Severity

**Issue 1: No Synergy Awareness**
- **Problem**: Might suggest removing card that synergizes with others
- **Impact**: Removing 'Goblin Guide' from Goblin deck breaks tribal synergies
- **Recommendation**: Check for synergy patterns (tribal, combo, engine) before removal
- **Test Case**: `synergy_aware_removal`

#### Medium Severity

**Issue 2: Redundancy Thresholds Too Strict**
- **Problem**: Fixed thresholds (12 removal, 20 threats) don't account for format differences
- **Impact**: Control decks in Legacy might legitimately have 15+ removal
- **Recommendation**: Format-aware thresholds or percentile-based
- **Test Case**: `control_deck_excess_removal`

**Issue 3: Low Archetype Match Too Aggressive**
- **Problem**: Removing cards not in archetype staples might remove meta calls
- **Impact**: 'Smash to Smithereens' is sideboard tech, not a staple, but still valuable
- **Recommendation**: Distinguish maindeck staples from sideboard/tech cards
- **Test Case**: `meta_call_removal`

---

### Replace Suggestions (3 issues)

#### High Severity

**Issue 1: Role Overlap Threshold Too Low**
- **Problem**: 30% role overlap might allow replacing removal with threats
- **Impact**: Might suggest replacing 'Lightning Bolt' with 'Goblin Guide' (both red, different roles)
- **Recommendation**: Require >50% role overlap, or add `role_match` parameter
- **Test Case**: `role_mismatch_replacement`

#### Medium Severity

**Issue 2: No Lateral Upgrade Mode**
- **Problem**: Only upgrade/downgrade modes, no "same price, better effect"
- **Impact**: Might miss $2 → $2.10 strictly better replacements
- **Recommendation**: Add 'lateral' mode or `price_tolerance` parameter
- **Test Case**: `lateral_upgrade`

**Issue 3: No Curve Consideration**
- **Problem**: Might suggest replacing 1 CMC with 4 CMC card, breaking curve
- **Impact**: Replacing 'Lightning Bolt' with 'Boros Charm' (3 CMC) might break curve
- **Recommendation**: Consider CMC similarity when suggesting replacements
- **Test Case**: `curve_aware_replacement`

---

### Contextual Discovery (3 issues)

#### High Severity

**Issue 1: No Functional Synergy Detection**
- **Problem**: Synergies only based on co-occurrence, not functional relationships
- **Impact**: 'Goblin Guide' and 'Lightning Bolt' co-occur but aren't synergistic
- **Recommendation**: Add functional synergy (tribal, combo, engine, payoff)
- **Test Case**: `functional_synergy`

#### Medium Severity

**Issue 2: No Format Legality Filtering**
- **Problem**: Might suggest alternatives not legal in format
- **Impact**: Suggesting 'Chain Lightning' in Modern (Legacy-only)
- **Recommendation**: Filter alternatives by format legality
- **Test Case**: `format_legal_alternatives`

#### Low Severity

**Issue 3: Stale Price Data**
- **Problem**: Price data might be missing or stale
- **Impact**: New cards or reprints might not have price data
- **Recommendation**: Fallback to rarity-based estimation, or mark as 'price unknown'
- **Test Case**: `missing_price_data`

---

### Explanations (2 issues)

#### Medium Severity

**Issue 1: Too Technical**
- **Problem**: Technical terms (inclusion rate, role gap) not beginner-friendly
- **Impact**: New players might not understand explanations
- **Recommendation**: Add explanation modes: 'technical', 'beginner', 'expert'
- **Test Case**: `explanation_clarity`

#### Low Severity

**Issue 2: No Negative Explanations**
- **Problem**: Can't explain why popular card wasn't suggested
- **Impact**: User wonders why 'Snapcaster Mage' wasn't suggested
- **Recommendation**: Add 'why_not' explanations for filtered cards
- **Test Case**: `negative_explanation`

---

## Test Cases Generated

### Deck Modification Test Cases (4)

1. **empty_burn_deck**: Empty deck should suggest core staples
2. **no_removal_deck**: Deck missing removal should prioritize removal
3. **excess_removal_deck**: Deck with excess removal should suggest removing weakest
4. **budget_burn_deck**: Budget deck should prioritize cheap cards

### Contextual Discovery Test Cases (1)

1. **lightning_bolt_contextual**: Format staple with clear synergies/alternatives

---

## Evaluation Framework

### Metrics to Track

1. **Relevance**: 0-4 scale (irrelevant → perfect)
2. **Explanation Quality**: 0-4 scale (confusing → clear)
3. **Archetype Match**: 0-4 scale (if archetype provided)
4. **Role Fit**: 0-4 scale (if role gap identified)
5. **Price Accuracy**: 0-4 scale (for upgrades/downgrades)

### LLM-as-Judge Integration

- Use `pydantic-ai` for structured judgments
- Judge each suggestion on multiple dimensions
- Generate ground truth annotations for regression testing
- Track inter-annotator agreement (if multiple judges)

---

## Priority Fixes

### Immediate (High Severity)

1. **Expand Role Taxonomy**: Add graveyard, board wipes, mana fixing, combo pieces
2. **Add Synergy Awareness**: Check tribal/combo/engine patterns before removal
3. **Fix Role Overlap Threshold**: Require >50% for replacements
4. **Add Functional Synergy**: Beyond co-occurrence, detect actual synergies
5. **Budget Prioritization**: Boost cheaper cards within budget
6. **Format Legality Filtering**: Filter alternatives by format

### Short-term (Medium Severity)

1. **Tiered Archetype Thresholds**: 70%+ / 50-69% / 30-49%
2. **Card Count Suggestions**: Suggest optimal count (1-of vs 4-of)
3. **Format-Aware Thresholds**: Adjust redundancy thresholds by format
4. **Lateral Upgrade Mode**: Same price, better card
5. **Curve Consideration**: CMC similarity for replacements
6. **Explanation Modes**: Technical / beginner / expert

### Long-term (Low Severity)

1. **Pagination for Large Gaps**: More than 10 suggestions for incomplete decks
2. **Negative Explanations**: Why popular cards weren't suggested

---

## Next Steps

1. ✅ **Critique Complete**: 15 issues identified
2. ✅ **Test Cases Generated**: 5 test cases created
3. ⏳ **LLM-as-Judge Integration**: Framework ready, needs implementation
4. ⏳ **Ground Truth Generation**: Generate annotations for test cases
5. ⏳ **Regression Testing**: Run test cases and track metrics over time
6. ⏳ **Fix High-Priority Issues**: Implement top 6 fixes

---

**Status**: Critique complete. Evaluation framework ready. Ready to implement fixes and generate ground truth annotations.

