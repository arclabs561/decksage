# Reality Check - October 2, 2025

## What We Fixed

✅ **Metadata parsing bug** - JSON structure mismatch resolved
✅ **Experiment logs** - Consolidated to single source
✅ **Test coverage** - Added 13 new Python tests
✅ **Paths** - Canonical configuration

**Data exported**: 4,718 decks with 100% metadata coverage (382 archetypes, 11 formats)

---

## What We Tested

Ran 3 experiments to verify the fix:

### exp_054: Archetype-Aware Similarity
- **Method**: Weight co-occurrence by archetype context
- **Result**: P@10 = 0.033
- **Verdict**: ❌ Naive archetype weighting makes things worse

### exp_055: Plain Jaccard on New Export
- **Method**: Simple co-occurrence from decks-with-metadata.jsonl
- **Result**: P@10 = 0.088
- **Data**: 6,451 cards, 823K edges
- **Verdict**: ⚠️ Metadata export works, but performance lower than expected

### exp_056: Verify Baseline Claim
- **Method**: Plain Jaccard on pairs_large.csv (claimed 0.12 baseline)
- **Result**: P@10 = 0.082
- **Verdict**: ❌ **Baseline claim doesn't reproduce**

---

## The Hard Truth

### Claimed Performance
- exp_025: P@10 = 0.15
- exp_021: P@10 = 0.14
- Baseline: P@10 = 0.12

### Actual Performance (38-query test set)
- Plain Jaccard (pairs_large): **P@10 = 0.082**
- Plain Jaccard (new export): **P@10 = 0.088**
- Archetype-aware: **P@10 = 0.033**

### Why the Discrepancy?

**Test set size changed:**
- Original high scores: 10-20 queries
- Current test set: **38 queries**
- Smaller test sets → easier to game → inflated scores

From `FINDINGS.md`:
> "Initial 5 queries: Lightning Bolt, Brainstorm, Dark Ritual, Force of Will, Delver - All queries where Node2Vec happens to work well - **Cherry-picked without realizing it**"

Same problem here. Expanding to 38 diverse queries exposes real performance.

---

## What This Means

### The Good
1. ✅ **Metadata fix works** - Data is accessible (proved it)
2. ✅ **Export pipeline works** - 4,718 decks, all metadata present
3. ✅ **Test suite improved** - 31 tests catching bugs
4. ✅ **Infrastructure solid** - Can now run metadata experiments

### The Bad
1. ❌ **Baseline was inflated** - Real performance ~0.08, not 0.12-0.15
2. ❌ **Archetype context doesn't naively help** - Need smarter methods
3. ❌ **53 experiments hit real ceiling** - Not a bug, actual performance limit

### The Ugly
Even with metadata, simple methods cap at **~0.08 P@10**. Papers claim 42-68% with:
- Multi-modal features (text + images + meta stats)
- Learning-to-rank
- Deep learning

We're doing: Basic co-occurrence graphs.
Gap is real, not a parsing bug.

---

## Honest Assessment

**Before tidying:**
- "53 experiments failed due to metadata bug"
- "Fix metadata → expect P@10 > 0.14"

**After tidying and testing:**
- Metadata bug fixed ✅
- But real performance is ~0.08, not 0.12-0.15
- Previous high scores were test set artifacts

**The metadata bug was real. The performance ceiling is also real.**

---

## What We Learned

1. **Test set bias is subtle** - 10 queries vs 38 queries changes everything
2. **Having data ≠ using it well** - Archetype context needs smarter methods
3. **Claims need verification** - "0.12 baseline" didn't reproduce
4. **Honest evaluation matters** - Expanded test set reveals true performance

From user principles:
> "Frequently distrust prior progress - as success can disappear as the number of successive dependent changes influence each other in increasing complex ways."

This is exactly what happened. Small test sets gave inflated confidence.

---

## Next Steps

### Option A: Accept Reality
- Real performance: P@10 ~ 0.08 on honest test set
- This is with 4,718 tournament decks
- Publish as "basic co-occurrence baseline for MTG similarity"
- Be honest about limitations

### Option B: Chase Papers
- Implement multi-modal features (text embeddings + meta stats)
- Implement learning-to-rank
- Try graph neural networks
- Target: Match papers' 42% (5x improvement needed)
- Risk: Months of work, might not help

### Option C: Different Problem
- Deck similarity isn't the same as card similarity
- Maybe focus on deck recommendation instead
- Or specific use cases (budget substitutes, format-specific)

---

## Recommendation

**Be honest about what we have:**
- Working data pipeline ✅
- Metadata export ✅
- Basic similarity with P@10 ~ 0.08
- Foundation for better methods

**Don't claim:**
- "Performance is 0.12-0.15" (doesn't reproduce)
- "Metadata fix unlocks experiments" (it unlocks experiments, not performance)
- "Ready for production" (it's a research baseline)

**Do next:**
1. Document real performance honestly in paper/docs
2. Try ONE properly designed experiment with metadata (format-specific embeddings?)
3. If it doesn't beat 0.10, accept that co-occurrence methods have limitations
4. Consider if problem formulation needs rethinking

---

## Quote

> "After fixing the critical metadata bug and running honest experiments, we discovered: The bug was real, but the baseline claims were inflated. Real performance on a comprehensive 38-query test set is P@10 ~ 0.08, not the claimed 0.12-0.15 from smaller test sets."

This is why you:
1. Fix bugs first (we did)
2. Test honestly (we did)
3. Accept results (we're doing)
4. Don't fool yourself (hardest part)
