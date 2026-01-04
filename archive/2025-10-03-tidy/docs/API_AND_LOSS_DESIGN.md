# Deck Improvement API & Loss Function Design

## The Improvement API

### Input
```python
{
  "current_deck": ["Lightning Bolt", "Monastery Swiftspear", ...],  # 60 cards
  "format": "Modern",
  "budget": 500,  # USD (optional)
  "goal": "competitive"  # vs "casual", "budget"
}
```

### Output
```python
{
  "suggestions": [
    {
      "action": "swap",
      "remove": "Lightning Bolt",
      "add": "Orcish Bowmasters",
      "improvement_score": 0.23,  # Predicted win rate increase
      "reasoning": "Better card advantage in current meta",
      "confidence": 0.87,
      "cost": 45.00
    },
    ...
  ],
  "overall_improvement": 0.15,  # Expected total improvement
  "deck_analysis": {
    "current_archetype": "Burn (87% match)",
    "mana_curve": "Aggressive (avg CMC: 1.2)",
    "missing_functions": ["Card draw", "Interaction"]
  }
}
```

## The Loss Function

### Problem: Predict Deck Quality

Let $D$ be a deck, $Q(D) \in [0,1]$ be quality.

**Quality Proxies:**
1. Win rate (if simulatable)
2. Tournament placement (if available)
3. Meta score (pick rate × win rate from 17lands)
4. Expert rating (human labels)

### Learning to Rank for Swaps

Given deck $D$, candidate swaps $S = \{(c_{out}, c_{in})\}$

**Objective:** Rank swaps by improvement

$$\Delta Q(D, c_{out}, c_{in}) = Q(D \setminus \{c_{out}\} \cup \{c_{in}\}) - Q(D)$$

**Features for Each Swap:**
```python
φ(D, c_out, c_in) = [
    # Similarity features
    jaccard_sim(c_in, D \ {c_out}),           # How well it fits
    embedding_sim(c_in, D),                    # Semantic fit

    # Meta features (if available)
    win_rate(c_in) - win_rate(c_out),         # Quality diff
    pick_rate(c_in) - pick_rate(c_out),       # Popularity diff

    # Deck context features
    color_match(c_in, D),                      # Fits mana base
    cmc_curve_improvement(c_in, c_out, D),    # Mana curve
    function_coverage(c_in, D),                # Fills gap

    # Archetype features
    archetype_coherence(c_in, D),             # Matches strategy

    # Redundancy features
    num_similar_cards_in_deck(c_in, D),       # Avoid redundancy

    # Price features (if budget constrained)
    price(c_in) - price(c_out),               # Cost
]
```

### LambdaRank Loss

Training data: $\{(D_i, S_i, y_i)\}$ where
- $D_i$ = deck
- $S_i$ = candidate swaps
- $y_i$ = improvement labels (from tournament results, win rate changes, or expert)

For deck $D$, swaps $(s_i, s_j)$ with $y_i > y_j$:

$$L_{LambdaRank} = \sum_{i,j: y_i > y_j} \lambda_{ij} \log(1 + \exp(-(\hat{y}_i - \hat{y}_j)))$$

Where $\lambda_{ij} = |\Delta NDCG|$ (change in ranking metric)

**Predicted scores:**
$$\hat{y}_i = f_\theta(\phi(D, s_i))$$

Model $f_\theta$: LightGBM, neural network, or linear

### Why This is Different

**Current (Similarity):**
- Input: Single card
- Output: Similar cards
- Loss: P@10 (precision)
- Missing: Deck context, improvement notion

**Correct (Improvement):**
- Input: Full deck
- Output: Ranked improvements
- Loss: LambdaRank (pairwise improvement)
- Uses: Deck context, meta stats, card features

## Path Forward

### Phase 1: Data Collection (This Week)

1. **Export heterogeneous structure:**
```bash
go run cmd/export-decks-hetero \
  data-full/games/magic \
  decks_structured.jsonl
```

Output: One deck per line with full structure:
```json
{
  "deck_id": "d001",
  "archetype": "Burn",
  "format": "Modern",
  "placement": "1st",
  "cards": [{"name": "Lightning Bolt", "count": 4, "partition": "main"}],
  "event": "GP_Vegas_2024"
}
```

2. **Build heterogeneous graph:**
```python
Card --in_deck--> Deck
Deck --has_archetype--> Archetype
Deck --placed_in--> Event
```

### Phase 2: Annotation (Week 2)

Collect deck improvement labels:
```yaml
- deck: [Lightning Bolt, Monastery Swiftspear, ...]
  suggested_swap:
    remove: Lightning Bolt #4
    add: Orcish Bowmasters
  expert_rating: 8/10  # Would improve deck
  reason: "Need card advantage vs aggro"
```

Use LLM judge + expert validation:
- LLM suggests improvements
- Expert rates 1-10
- Build training set

### Phase 3: LTR Model (Week 3)

```python
import lightgbm as lgb

# Features
X = [φ(D, swap) for D, swap in training_data]

# Labels (improvement scores)
y = [expert_rating for ...]

# Groups (which samples belong to same deck)
groups = [len(swaps_for_deck_i) for ...]

# Train ranker
model = lgb.LGBMRanker()
model.fit(X, y, group=groups)

# Predict improvements
improvements = model.predict(features_for_new_deck)
```

### Phase 4: Meta Statistics (Week 4)

Integrate 17lands.com or compute from our data:
```python
card_stats = {
    'Lightning Bolt': {
        'pick_rate': 0.85,      # How often picked
        'win_rate': 0.52,       # Win rate when in deck
        'games_played': 10000,  # Sample size
        'archetype_win_rates': {
            'Burn': 0.54,
            'Prowess': 0.51
        }
    }
}
```

Use as features in LTR model.

## Immediate Actions

**Tomorrow:**
1. Write `cmd/export-decks-hetero` to preserve structure
2. Build Card-Deck-Archetype heterogeneous graph
3. Try metapath2vec on heterogeneous graph
4. Compare to homogeneous baseline (should beat 0.12)

**Week 2:**
5. Collect 50 deck improvement labels (LLM + expert)
6. Build LTR features from heterogeneous graph
7. Train LightGBM ranker
8. Evaluate on deck improvement task

**Week 3:**
9. Integrate meta statistics
10. Add to LTR features
11. Target: 0.40+ P@improvement (vs papers' 0.42)

## Why This Will Work

**Papers show:** Multi-modal + meta stats = 42-68%
**We discovered:** Structure exists, export collapses it
**Solution:** Preserve structure + add meta stats + LTR
**Expected:** Match or beat papers (we have more data - 39K decks)

## Loss Function Summary

**Current:**
$$L = 1 - P@10_{similarity}$$

**Correct:**
$$L = \sum_{decks, swaps} \lambda_{ij} \log(1 + \exp(-(\hat{\Delta Q}_i - \hat{\Delta Q}_j)))$$

Where $\hat{\Delta Q}$ = predicted deck improvement

This changes the entire problem from similarity search to decision making.
