# Problem Diagnosis: Why Node2Vec Fails

## TL;DR

**We're solving the wrong problem.**

- Training objective: Edge prediction (co-occurrence)
- Evaluation objective: Functional similarity
- These are fundamentally different tasks

## Experimental Evidence

### Test 1: More Data
- 150 decks → 500 decks (3x increase)
- Jaccard: 0.141 → 0.145 (+2.8%) ✓
- Node2Vec: 0.136 → 0.070 (-52%) ✗

**Interpretation:** Node2Vec learns noise, not signal.

### Test 2: What Node2Vec Actually Learns

**Query: Lightning Bolt**

Node2Vec predictions (500 decks):
1. Monastery Swiftspear (creature)
2. Burning-Tree Emissary (mana dork)
3. Chain Lightning (burn spell) ✓
4. Kessig Flamebreather (creature)

Pattern: **"Cards in Pauper red aggro"** not **"burn spells"**

Jaccard predictions:
1. Chain Lightning (burn spell) ✓
2. Fireblast (burn spell) ✓
3. Lava Dart (burn spell) ✓

Pattern: **Direct co-occurrence neighbors** (actually similar!)

## Root Cause Analysis

### Issue 1: Mismatched Objectives

**Training Loss (Node2Vec):**
```
L = -log P(context | node)
  = Predict which cards appear near card in random walk
```

**What this learns:**
- Cards in same archetype (Prowess deck)
- Cards in same format (Pauper)
- Cards in same color (Red)

**What we want:**
- Cards with same function (burn)
- Cards that substitute for each other
- Cards that serve same strategic role

**These are NOT aligned!**

### Issue 2: No Supervision

We have:
- Deck lists (which cards appear together)

We don't have:
- Card functions (burn, draw, removal)
- Card attributes (color, type, CMC)
- Strategic roles (aggro, control, combo)
- Substitution relationships

**We're doing unsupervised learning for a supervised problem.**

### Issue 3: Graph Structure Mismatch

**What co-occurrence graph encodes:**
```
Lightning Bolt -- Monastery Swiftspear (both in Prowess)
Lightning Bolt -- Lava Spike (both in Burn)
```

Both edges have same weight, but mean different things:
- First: Spell + creature synergy
- Second: Spell + spell substitutes

**Node2Vec can't distinguish these without attributes.**

## What Would Actually Work

### Option A: Supervised Learning (Best)

Collect labels:
```yaml
- query: Lightning Bolt
  substitutes: [Chain Lightning, Lava Spike]
  synergies: [Monastery Swiftspear, Eidolon of the Great Revel]
  context: "Red instant dealing 3 damage"
```

Train model:
```python
# Supervised similarity learning
model.train(
    positive_pairs=[(Bolt, Chain Lightning)],
    negative_pairs=[(Bolt, Counterspell)],
    loss=contrastive_loss
)
```

**Requires:** Human annotation (100-500 queries)

### Option B: Add Card Attributes (Next Best)

Use Scryfall data:
```python
node_features = {
    'Lightning Bolt': {
        'color': [1,0,0,0,0],  # Red
        'type': 'Instant',
        'cmc': 1,
        'text_embedding': bert("deals 3 damage"),
        'tags': ['burn', 'removal']
    }
}
```

Then:
```python
# GNN with node features
from torch_geometric.nn import GATConv

# Learn function from attributes + structure
embeddings = GAT(node_features, edge_index)
```

**Hypothesis:** Cards with similar attributes that co-occur should be similar.

**Requires:** Feature engineering (1-2 days)

### Option C: Use Jaccard (Simplest)

Just deploy what works:
```python
def jaccard_similarity(c1, c2):
    neighbors1 = set(cards_that_cooccur_with_c1)
    neighbors2 = set(cards_that_cooccur_with_c2)
    return len(neighbors1 & neighbors2) / len(neighbors1 | neighbors2)
```

**Works because:** Direct neighborhood overlap captures actual co-occurrence better than random walks.

## What Our Data Actually Contains

Looking at `pairs_500decks.csv`:
```csv
NAME_1,NAME_2,COUNT_SET,COUNT_MULTISET
Lightning Bolt,Monastery Swiftspear,42,84
Lightning Bolt,Chain Lightning,12,18
Lightning Bolt,Brainstorm,38,76
```

**We know:**
- Which cards appear together (COUNT)
- That's it.

**We don't know:**
- Why they appear together
- What function each card serves
- Whether they're substitutes or synergies
- Card attributes (beyond name)

**Jaccard uses exactly this information. Node2Vec tries to infer patterns that don't exist.**

## Actionable Recommendations

### Immediate (Today)

1. **STOP training Node2Vec variants** - we've proven it doesn't work
2. **Deploy Jaccard API** - it works, it's simple, it's interpretable
3. **Document why Node2Vec failed** - save future effort

### Short-term (This Week)

4. **Fetch Scryfall attributes** for all cards:
   ```bash
   python fetch_scryfall_features.py
   ```

5. **Try attributed GNN**:
   ```python
   # With card features
   model = GAT(card_features, edge_index)
   ```

6. **Compare to Jaccard**:
   - If GNN beats Jaccard: Deploy GNN
   - If Jaccard still wins: Keep Jaccard

### Medium-term (2-3 Weeks)

7. **Create annotation task**:
   - 50-100 queries
   - Label substitutes vs synergies
   - Human review

8. **Supervised learning**:
   ```python
   model.train(
       labeled_pairs=annotations,
       loss=triplet_loss
   )
   ```

9. **Final comparison**:
   - Jaccard (unsupervised)
   - Attributed GNN (semi-supervised)
   - Supervised similarity (fully supervised)

## Conclusion

**Our mistake:** Assumed unsupervised Node2Vec would learn functional similarity from co-occurrence alone.

**Reality:** Co-occurrence ≠ function. Need supervision or attributes.

**Path forward:**
1. Ship Jaccard (works now)
2. Add attributes → GNN (may work)
3. Add labels → supervised learning (should work)

**Don't waste time:** Node2Vec on unattributed co-occurrence graphs is the wrong tool.


