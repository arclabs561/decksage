# Use Cases & Similarity Types

## The Problem

We've been treating "similarity" as one thing. It's not.

## Distinct Use Cases

### 1. **Substitutes/Replacements**
**User query:** "I don't have Lightning Bolt, what can I play instead?"

**Need:** Functional equivalence
- Same card type (instant)
- Same mana cost or close (R vs 1R)
- Same effect (3 damage)

**Best method:** Card attributes + text similarity
- BERT embeddings on oracle text
- Filter by type/cost
- Returns: Chain Lightning, Lava Spike

**Current support:** ❌ None (need card attributes)

---

### 2. **Synergies/Combos**
**User query:** "What cards work well with Monastery Swiftspear?"

**Need:** Co-occurrence in winning decks
- Cards that appear together
- Same archetype
- Proven synergistic

**Best method:** Jaccard similarity
- Direct deck co-occurrence
- Returns: Lightning Bolt, Lava Dart, Rift Bolt

**Current support:** ✅ Jaccard API method

---

### 3. **Deck Completion**
**User query:** "I'm building Burn, what am I missing?"

**Need:** Archetype staples
- Cards common in this archetype
- Role coverage (threats + removal + reach)
- Format-specific

**Best method:** Deck clustering + archetype templates
- Cluster decks by archetype
- Find common cards in cluster
- Returns: Burn staples you don't have

**Current support:** ❌ None (need deck clustering)

---

### 4. **Budget Upgrades**
**User query:** "How do I upgrade my deck without spending $500?"

**Need:** Performance improvement at similar price
- Card power level
- Price constraints
- Meta relevance

**Best method:** Hybrid (similarity + price + win rate)
- Find better cards in price range
- Filter by format legality
- Returns: Skewer the Critics instead of Lava Spike

**Current support:** ❌ None (need price/power data)

---

### 5. **Strategic Similarity**
**User query:** "I like playing Burn, what other decks would I enjoy?"

**Need:** Playstyle similarity
- Game plan similarity
- Turn speed
- Interaction level

**Best method:** Deck embeddings (not card embeddings)
- Embed entire decks
- Cluster by strategy
- Returns: Prowess, Infect (fast aggressive decks)

**Current support:** ❌ None (need deck-level embeddings)

---

### 6. **Meta Analysis**
**User query:** "What's popular with Orcish Bowmasters?"

**Need:** Current metagame patterns
- Recent tournament data
- Trending combinations
- Format breakdowns

**Best method:** Temporal co-occurrence
- Weight recent decks higher
- Track trends over time
- Returns: Current meta pairings

**Current support:** ⚠️ Partial (have co-occurrence, no temporal weighting)

---

## What Each Method Actually Provides

### Jaccard Similarity
**Measures:** Direct co-occurrence
**Good for:** Synergies, meta analysis
**Bad for:** Substitutes, upgrades
**Example:**
- Query: Lightning Bolt
- Returns: Cards that appear WITH Bolt (synergies)
- Monastery Swiftspear, Rift Bolt, Lava Dart

### Node2Vec
**Measures:** Semantic/functional patterns
**Good for:** Substitutes, similar cards
**Bad for:** Exact synergies, price-aware upgrades
**Example:**
- Query: Lightning Bolt
- Returns: Cards LIKE Bolt (burn spells)
- Chain Lightning, Fireblast, Lava Spike

### Card Attributes (Not Built Yet)
**Measures:** Feature similarity
**Good for:** Exact replacements
**Bad for:** Strategic similarity
**Example:**
- Query: Lightning Bolt
- Returns: Same type/cost/effect
- Shock (strictly worse), Burst Lightning (conditional)

---

## Recommended API Design

```python
@app.post("/similar")
async def find_similar(
    query: str,
    use_case: str,  # NEW: specify use case
    top_k: int = 10
):
    """
    Use cases:
    - "substitute": Find functional replacements
    - "synergy": Find cards that work well together
    - "deck_complete": Find missing archetype staples
    - "upgrade": Find better cards in budget
    - "similar_deck": Find similar deck archetypes
    - "meta": What's popular with this card
    """

    if use_case == "substitute":
        # Use Node2Vec (semantic similarity)
        return node2vec_similar(query, k)

    elif use_case == "synergy":
        # Use Jaccard (co-occurrence)
        return jaccard_similar(query, k)

    elif use_case == "deck_complete":
        # Cluster-based recommendation
        archetype = detect_archetype(user_deck)
        return archetype_staples(archetype, k)

    elif use_case == "upgrade":
        # Similarity + price + power
        similar = node2vec_similar(query, k*3)
        return filter_by_price_and_power(similar, budget, k)

    # etc.
```

---

## Current Reality

**What we have:**
- ✅ Jaccard (synergies/meta)
- ✅ Node2Vec (substitutes/functional)

**What we're missing:**
- ❌ Card attributes (exact replacements)
- ❌ Deck clustering (archetype completion)
- ❌ Price data (budget upgrades)
- ❌ Temporal weighting (meta trends)

**What we've been doing:**
- Evaluating both methods on same generic "similarity" task
- Wondering why results are confusing
- Not realizing they solve different problems

---

## Proposed Solution

### Phase 1: Clarify API (This Week)
```python
# Make use case explicit
{
  "query": "Lightning Bolt",
  "use_case": "substitute",  # vs "synergy"
  "top_k": 10
}
```

### Phase 2: Add Missing Use Cases (2-3 Weeks)

1. **Fetch card attributes** (Scryfall API)
   - Color, type, CMC, text
   - Enable: Exact replacements

2. **Cluster decks** (unsupervised)
   - K-means on deck vectors
   - Enable: Archetype completion

3. **Add price data** (Scryfall/TCGPlayer)
   - Current market prices
   - Enable: Budget upgrades

4. **Temporal weighting** (decay old data)
   - Weight by deck date
   - Enable: Meta trends

### Phase 3: Unified Interface (4-6 Weeks)

```python
similarity_engine = UnifiedSimilarity(
    node2vec_model=...,
    jaccard_graph=...,
    card_attributes=...,
    price_data=...,
    deck_clusters=...
)

# Automatically pick best method per use case
result = similarity_engine.find_similar(
    query="Lightning Bolt",
    use_case="substitute",
    filters={"budget": 50, "format": "Modern"}
)
```

---

## Evaluation Strategy

**For each use case, different ground truth:**

1. **Substitutes:** Expert labels (functional equivalents)
2. **Synergies:** Deck co-occurrence (observed pairings)
3. **Deck completion:** Tournament decklists (actual archetypes)
4. **Upgrades:** Win rate + price data
5. **Meta:** Recent tournament frequency

**Don't evaluate substitute-finder on synergy task!**

---

## Immediate Action

Update API to expose both methods clearly:

```python
# Substitutes
POST /similar {"query": "Bolt", "type": "functional"}
→ Uses Node2Vec

# Synergies
POST /similar {"query": "Bolt", "type": "cooccurrence"}
→ Uses Jaccard

# Smart (pick best method automatically)
POST /similar {"query": "Bolt"}
→ Analyzes query, picks method
```

This explains why both Jaccard AND Node2Vec have value.
They solve different problems.
