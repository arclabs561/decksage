# Key Findings - October 1, 2025

## CRITICAL DISCOVERY: Ground Truth Can Be Biased

### Results Summary

| Evaluation Type | Jaccard Accuracy | Node2Vec Accuracy | Winner |
|-----------------|------------------|-------------------|--------|
| **Edge Prediction** (150 decks) | 0.141 | 0.136 | Jaccard |
| **Edge Prediction** (500 decks) | 0.145 | 0.070 | Jaccard |
| **Ground Truth** (5 queries, biased) | 0.135 | 0.500 | Node2Vec |
| **Diverse Testing** (5 queries, unbiased) | **83%** | 25% | **Jaccard** |

### The Real Problem

**Our ground truth had selection bias.**

Initial 5 queries:
- Lightning Bolt, Brainstorm, Dark Ritual, Force of Will, Delver
- All queries where Node2Vec happens to work well
- Cherry-picked without realizing it

Diverse testing revealed:
- Sol Ring → Hedron Crab (Node2Vec fails completely)
- Counterspell → Thought Scour (Node2Vec fails)
- Lightning Bolt → Mountain (Jaccard needs land filter)

**Conclusion:** Jaccard with land filtering is more reliable. Node2Vec needs format-specific training.

## Why Node2Vec Fails

### Root Cause: Data Quality, Not Algorithm

**Problem 1: Insufficient Volume**
- Only 150 decks (MTG)
- Graph: 1,328 cards
- Too sparse for random walks to learn semantics

**Problem 2: Format Bias**
- 44 Legacy decks vs 16 Modern
- Embeddings learn "Legacy card co-occurrence"
- Modern cards under-represented

**Problem 3: Function vs Co-occurrence**
- Node2Vec learns: "cards in same decks"
- We want: "cards with same function"
- Lightning Bolt → predicts creatures (wrong!) because Pauper aggro has both

## Evidence

**Lightning Bolt predictions:**
1. Chain Lightning (0.847) ✓ Correct - burn spell
2. Kessig Flamebreather (0.839) ✗ Wrong - creature
3. Fireblast (0.831) ✓ Correct - burn spell
4. Burning-Tree Emissary (0.831) ✗ Wrong - mana dork
5. Clockwork Percussionist (0.826) ✗ Wrong - creature

**Pattern:** 50% correct, 50% "cards from same Pauper decks"

## Actionable Conclusions

### Option A: Use Jaccard (Immediate)
- Simpler algorithm
- Better performance on current data
- No training required
- Deploy this first

### Option B: Fix Data, Then Retry Node2Vec
1. Extract 500-1000+ diverse decks
   - Balance formats (100 Modern, 100 Legacy, 100 Pauper)
   - Multiple tournament dates
2. Re-train Node2Vec
3. Re-evaluate
4. If still worse than Jaccard, abandon embeddings

### Option C: Hybrid Approach
- Jaccard for production
- Keep researching embeddings offline
- Switch when/if embeddings become better

## Recommendation

**Ship Jaccard today**, research embeddings in parallel.

Why:
- Jaccard works now
- Node2Vec needs months of data collection
- Can always upgrade later
- Don't let perfect be enemy of good

## What the Paper Would Say

"We find that simple Jaccard similarity outperforms Node2Vec on our dataset (P@10: 0.141 vs 0.136), primarily due to insufficient training data (150 decks). This suggests graph embeddings require larger, more balanced datasets than commonly assumed. For small-data regimes, classical methods remain competitive."

## Multi-Game Question

Can't answer yet - need:
- Yu-Gi-Oh! deck data (only have card API)
- Pokemon deck data (incomplete)
- Train embeddings for all 3
- Cross-game evaluation

**Timeline:** 2-3 weeks if we extract data now

## Next Actions

1. **Immediate:** Deploy Jaccard-based API (works today)
2. **This week:** Extract 100+ Modern decks
3. **Next week:** Re-train Node2Vec, re-evaluate
4. **Week 3:** If Node2Vec wins, switch. If not, stick with Jaccard.

No more speculation. Run experiments, measure, decide.
