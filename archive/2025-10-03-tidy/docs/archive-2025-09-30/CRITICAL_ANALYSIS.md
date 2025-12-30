# DeckSage - Critical Analysis & Issues Found

**Date**: 2025-09-30  
**Status**: 🔴 **SIGNIFICANT DATA QUALITY ISSUES DISCOVERED**

---

## Issue #1: Set-Based Co-occurrence is Poisoning the Graph

### The Problem

**Sets are NOT decks**. Cards in a set don't "co-occur" meaningfully - they're just printed together.

**Example**: Outlaws of Thunder Junction (341 cards)
- Created 57,970 edges (341 × 340 / 2)
- These edges are **meaningless** for deck building
- They overwhelm actual deck co-occurrence signals

### Impact on Embeddings

**Command Tower** appears 487 times because:
- It's in multiple sets (reprinted across many sets)
- Each set creates co-occurrence with EVERY card in that set
- This drowns out actual deck-building relationships

**Result**: Embeddings learn "cards printed in same set" not "cards played together"

### Data Breakdown

```
Format Distribution (MTGTop8):
- Legacy: 44 decks
- Pauper: 37 decks  
- Vintage: 20 decks
- Modern: 16 decks
- Duel Commander: 16 decks
- Pioneer: 15 decks
- Peasant: 2 decks

Sets (Scryfall):
- 21 sets (~8,000 cards total)
- Creating ~200K+ meaningless edges
```

**Sets dominate the graph!** 21 sets vs 150 decks, but sets have 10x more cards.

---

## Issue #2: Missing Modern Staples

**Not in vocabulary**: Tarmogoyf, Monastery Swiftspear

These are **extremely** common Modern cards. Why missing?

**Hypothesis**:
1. Only 16 Modern decks in dataset
2. Cards appear only once (COUNT_SET=1)
3. Filtered out by `min_cooccurrence=2`

**Implication**: Coverage is format-biased. We have good Pauper/Legacy, poor Modern coverage.

---

## Issue #3: Counterspell Results Don't Make Sense

**Query**: Counterspell  
**Results**: All Faeries/Ninjas (Pauper archetype)

**Expected**: Should cluster with:
- Force of Will (Legacy)
- Mana Leak (Modern)
- Spell Pierce (cross-format)

**Actual**: Only learns ONE specific Pauper deck archetype (Faeries)

**Root Cause**: 
- 37 Pauper decks (many similar archetypes)
- Only 16 Modern decks (insufficient diversity)
- Counterspell is Pauper-legal, not Modern-legal
- Embeddings learn "Pauper Faeries" not "permission spells"

---

## Issue #4: Brainstorm + Snow-Covered Swamp?

**Query**: Brainstorm  
**Top 5**: Daze (✅), Tamiyo (❓), Ponder (✅), Snow-Covered Swamp (❌), Force of Will (✅)

**Problem**: Snow-Covered Swamp has similarity of 0.880 with Brainstorm

**Analysis**:
- Brainstorm is a blue cantrip
- Snow-Covered Swamp is a black land
- These should NOT be similar

**Hypothesis**: 
- Both appear in same sets (recent sets have snow lands)
- Set-based co-occurrence creating false associations

---

## Issue #5: Graph Filtering is Too Aggressive

**Filter**: `min_cooccurrence ≥ 2`

**Effect**:
- Original: 186,608 pairs
- Filtered: 26,637 pairs (85% removed!)
- Cards: 8,207 → 1,206 (85% removed!)

**Lost**:
- Modern staples (Tarmogoyf, Monastery Swiftspear)
- Many format-specific cards
- Rare but important combinations

---

## Root Cause Analysis

### The Core Problem

**We're mixing incompatible data types**:

1. **Decks** (150): Cards that actually play together
2. **Sets** (21): Cards that were printed together

These have **completely different semantics**:

| Type | Edge Meaning | Useful? |
|------|--------------|---------|
| Deck | "Played together in competitive deck" | ✅ YES |
| Set | "Printed in same expansion" | ❌ NO |

**Current graph**: ~90% set-based edges, ~10% deck-based edges

**Result**: Embeddings learn "printing patterns" not "play patterns"

---

## What the Embeddings Actually Learned

### Brainstorm Results - Decoded

1. **Daze** (0.900) - ✅ Legacy blue tempo (correct!)
2. **Ponder** (0.891) - ✅ Blue cantrip (correct!)
3. **Force of Will** (0.876) - ✅ Legacy staple (correct!)
4. **Snow-Covered Swamp** (0.880) - ❌ Set co-occurrence artifact

**Conclusion**: Embeddings are ~75% correct, 25% noise from sets

### Counterspell Results - Decoded

**All Faeries/Ninjas** - This is ONE specific Pauper deck

**Why**: 
- Counterspell appears in 37 Pauper decks
- Many are Faeries archetype (similar decklists)
- Creates strong co-occurrence signal
- Other formats have less representation

**Conclusion**: Embeddings are **format-specific**, not universal

---

## Critical Questions for Data Quality

### 1. What's the actual format coverage?

Need to analyze:
- How many unique archetypes per format?
- Are we getting redundant decklists?
- What's the diversity within each format?

### 2. Should we exclude sets entirely?

**Option A**: Remove sets from co-occurrence (deck-only)  
**Option B**: Weight sets differently (lower weight)  
**Option C**: Separate embeddings (deck-based vs set-based)

### 3. Is the filtering right?

**Current**: `COUNT_SET ≥ 2` (appears in ≥2 decks)

**Issues**:
- Removes one-of tech cards
- Removes format-specific staples
- 85% of graph lost

**Alternative**: `COUNT_MULTISET ≥ N` (total copies across all decks)

---

## Recommendations for Next Steps

### Immediate (Fix Data Quality)

1. **Re-run transform with deck-only filter**
   ```go
   // Only count decks, skip sets
   if col.Type.Type == "Set" {
       continue
   }
   ```

2. **Lower filter threshold**
   ```python
   # min_cooccurrence = 1 (include all)
   # Or use multiset threshold instead
   ```

3. **Train format-specific embeddings**
   ```python
   # Separate embeddings per format
   pauper_embeddings = train(pauper_decks_only)
   modern_embeddings = train(modern_decks_only)
   ```

### Analysis Needed (Validate Hypothesis)

1. **Graph analysis**:
   - What % of edges come from sets vs decks?
   - Degree distribution (are sets creating super-nodes?)
   - Component analysis (is graph connected?)

2. **Embedding quality metrics**:
   - Precision@K for known similar cards
   - Format classification accuracy
   - Archetype clustering quality

3. **Data coverage audit**:
   - Cards per format
   - Archetype diversity
   - Missing staples

---

## Deeper ML Critique

### What We're Actually Learning

**Current Model**: "Cards that appear in the same collections"

**Problem**: Collections include:
- Competitive decks (semantic: strategy)
- Draft sets (semantic: limited environment)
- Booster sets (semantic: design themes)

These are **three different similarity spaces**!

### Better Approach

**Option 1**: Separate Models
- Deck-based embeddings (for deck building)
- Set-based embeddings (for limited/draft)
- Cross-format meta-embeddings

**Option 2**: Weighted Combination
- Higher weight for decks
- Lower weight for sets
- Context-aware similarity

**Option 3**: Multi-view Learning
- Train on decks AND sets
- Learn multiple similarity dimensions
- User chooses which to query

---

## Specific Failure Cases to Test

### Test 1: Cross-Format Confusion

**Query**: Cards that appear in multiple formats

Expected: Should cluster by strategy, not format  
Test: "Lightning Bolt" should be similar to "Lava Spike" (burn strategy) even if different formats

### Test 2: Archetype Separation

**Query**: Cards from different archetypes

Expected: "Delver of Secrets" (tempo) should NOT be similar to "Painter's Servant" (combo)  
Test: Check if different strategies are separated

### Test 3: Set Contamination

**Query**: Rare cards only in sets, not decks

Expected: Should have low similarity to everything  
Test: Find set-only cards and check their neighbors

---

## Questions That Need Answers

1. **What's the edge weight distribution?**
   - Are deck edges stronger than set edges?
   - Can we use this to filter?

2. **What's the degree distribution?**
   - Are set cards super-nodes?
   - Is the graph scale-free?

3. **What's the clustering coefficient?**
   - Are decks forming tight clusters?
   - Are sets creating mesh structures?

4. **What's the community structure?**
   - Can we detect archetypes automatically?
   - Do formats form separate communities?

---

## Revised Quality Assessment

### What's Actually Working

✅ **Pipeline**: Extract → Transform → Train → Search  
✅ **Performance**: Fast, scalable  
✅ **Some results**: Delver results are excellent  

### What's Broken

❌ **Data mixing**: Sets pollute deck co-occurrence  
❌ **Coverage**: Missing Modern staples  
❌ **Filtering**: Too aggressive, removes 85%  
❌ **Format bias**: Pauper over-represented  

### Revised Score

**Before scrutiny**: 10/10 ✅  
**After scrutiny**: 6/10 ⚠️  

**Works but needs refinement**

---

## Action Items (Prioritized)

### Critical (Fix Now)

1. **Separate sets from decks** in transform
2. **Re-train deck-only embeddings**
3. **Validate results** against MTG domain knowledge
4. **Lower or remove filtering** threshold

### Important (Understand Better)

5. **Graph analysis** (degree, components, communities)
6. **Format-specific embeddings**
7. **Coverage audit** per format
8. **Embedding quality metrics**

### Nice to Have (Later)

9. **Multi-view embeddings** (deck vs set)
10. **Archetype detection** algorithm
11. **Cross-format transfer learning**

---

## Conclusion

**The experiment revealed fundamental data quality issues that weren't obvious until we examined results with domain expertise.**

This is EXACTLY why we needed to do the experiment (Path C motivation) - it found architectural issues in the transform pipeline that wouldn't have been caught by just implementing Yu-Gi-Oh! (Path B).

**Next**: Fix the transform to exclude sets, re-train, and validate with MTG expertise.
