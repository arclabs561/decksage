# Deployment Reality Check

## What We Learned from Actually Using the System

### Test Date: Oct 1, 2025
### Queries Tested: 5 (Lightning Bolt, Brainstorm, Dark Ritual, Counterspell, Sol Ring)

## Results

| Query | Method | Top Prediction | Correct? | Issue |
|-------|--------|----------------|----------|-------|
| Lightning Bolt | Node2Vec | Chain Lightning | ✓ | But #3 is Burning-Tree Emissary (creature) |
| Lightning Bolt | Jaccard | Mountain | ✗ | Land spam |
| Brainstorm | Both | Ponder | ✓ | Works! |
| Counterspell | Node2Vec | Thought Scour | ✗ | Completely wrong function |
| Counterspell | Jaccard | Remand | ✓ | Works! |
| Sol Ring | Node2Vec | Hedron Crab | ✗ | Mill card (Commander contamination) |
| Sol Ring | Jaccard | Ancient Tomb | ✓ | Works! |

**Success Rate: 50%** (3/6 test cases work without manual filtering)

## Critical Issues

### Issue 1: Land Contamination (Jaccard)
- Lands appear in every deck of their color
- Dominate similarity scores
- Need: Hardcoded land filter or type-aware filtering

### Issue 2: Format Mixing (Node2Vec)
- Commander + Modern + Legacy in same embedding
- Sol Ring means "fast mana" in competitive, "auto-include" in Commander
- Hedron Crab appears with Sol Ring in Commander Mill
- Need: Format-specific embeddings

### Issue 3: Type Confusion (Node2Vec)
- Counterspell → Thought Scour (both blue instants, different functions)
- Need: Type-aware similarity or card attributes

## What This Means for Deployment

### Option A: Deploy with Heavy Disclaimers
- Works 50% of the time
- Show disclaimer: "Results may include lands and cross-format contamination"
- Not professional

### Option B: Add Minimal Filtering
- Filter out lands (quick fix)
- Still have format mixing
- Success rate → 60-70%
- Ship next week

### Option C: Build Properly
- Split by format
- Add card types
- Type-aware filtering
- Success rate → 85-90%
- Ship in 2-3 weeks

## Recommendation

**Do Option B this week, Option C in parallel:**

Week 1 (This Week):
1. Add land filtering to API
2. Test on 20 queries
3. Document known issues
4. Soft launch with beta label

Week 2-3:
5. Split graph by format
6. Train format-specific embeddings
7. Add card type filtering
8. Re-evaluate

Week 4:
9. Production launch with quality guarantees

## Honest Timeline

**MVP (with disclaimers):** 2-3 days
**Beta (filtered, known issues):** 1 week
**Production (format-aware):** 3 weeks

Current state: Not ready for production without filtering.

## Key Learnings

1. **Testing reveals truth** - Looked good on metrics, terrible on real queries
2. **Format matters** - Can't mix Commander and Modern
3. **Simple filtering helps** - Land filter would fix 30% of issues
4. **Need multiple iterations** - First version is never right

## Action Items

Immediate:
- [ ] Add land filter to API
- [ ] Test on 20 diverse queries
- [ ] Document success rate honestly
- [ ] Add format parameter to API

This Week:
- [ ] Build format-specific embeddings
- [ ] Re-test with format routing
- [ ] Measure improvement

Don't:
- [ ] ~~Claim "production ready"~~
- [ ] ~~Deploy without filtering~~
- [ ] ~~Ignore format mixing~~
