# DeckSage Use Cases

## What Actually Works

### 1. Format-Specific Deck Building 🎯

**Use Case**: "I play Modern Burn, suggest cards for my 75"

**Method**:
```python
# Filter to format
modern_decks = [d for d in decks if d['format'] == 'Modern']
# Filter to archetype
burn_decks = [d for d in modern_decks if 'burn' in d['archetype'].lower()]
# Find co-occurring cards
suggestions = most_common_cards_in(burn_decks)
```

**Why it works**: Specific context (format + archetype) narrows search space

**Deliverable**: "Top cards in Modern Burn decks (last 6 months)"

---

### 2. Budget Substitutes 💰

**Use Case**: "I can't afford Force of Will, what's the budget alternative in Legacy?"

**Method**:
```python
# Find decks with Force of Will
decks_with_fow = [d for d in decks if 'Force of Will' in cards(d)]
# Find what ELSE they play in same slot (countermagic)
alternatives = co_occurring_counters(decks_with_fow)
# Filter by price
budget = [c for c in alternatives if price(c) < 5]
```

**Why it works**: Context is "decks that want this effect"

**Deliverable**: "Budget alternatives in Legacy blue decks"

---

### 3. Archetype Staples 📊

**Use Case**: "What are the essential cards for Reanimator?"

**Method**:
```python
reanimator_decks = [d for d in decks if d['archetype'] == 'Reanimator']
staples = cards_in_N_percent_of_decks(reanimator_decks, threshold=0.7)
```

**Why it works**: High frequency = archetype staple

**Deliverable**: "Core cards that define Reanimator (appear in 70%+ of decks)"

---

### 4. Meta Tracking 📈

**Use Case**: "What's trending with Ledger Shredder this month?"

**Method**:
```python
recent = [d for d in decks if d['date'] > last_30_days]
with_shredder = [d for d in recent if 'Ledger Shredder' in cards(d)]
trending = compare_frequencies(with_shredder, older_decks)
```

**Why it works**: Temporal signal shows meta shifts

**Deliverable**: "Cards gaining popularity with Ledger Shredder"

---

### 5. Sideboard Tech 🔧

**Use Case**: "What sideboard cards do Affinity decks use?"

**Method**:
```python
affinity = [d for d in decks if d['archetype'] == 'Affinity']
sideboard_cards = [c for d in affinity for c in d['sideboard']]
common_sb = most_frequent(sideboard_cards)
```

**Why it works**: Sideboard is specific context (vs specific matchups)

**Deliverable**: "Common Affinity sideboard cards"

---

## What Doesn't Work (Yet)

### ❌ Generic "Similar Cards"

**Problem**: "Cards like Lightning Bolt" returns creatures from Burn decks

**Why**: Co-occurrence captures deck context, not card function

**Need**: Text embeddings, type matching, rules text

---

### ❌ Cross-Format Analogies

**Problem**: "Modern equivalent of Legacy card X"

**Why**: Different card pools, different meta

**Need**: Format-aware embeddings, card legality filtering

---

### ❌ Combo Discovery

**Problem**: "What combos with Thassa's Oracle?"

**Why**: Combos are 2-3 card interactions, not frequent co-occurrence

**Need**: Rules engine, card interaction modeling

---

## Implementation Priority

### Phase 1: Quick Wins (This Week)
1. **Format-specific suggestions** - Already have format labels
2. **Archetype staples** - Already have archetype labels
3. **Basic web UI** - Show these use cases

### Phase 2: Expand Data (Next 2 Weeks)
1. **More sources** - MTGO leagues, Arena data
2. **More formats** - cEDH, Old School, Premodern
3. **Temporal data** - Track meta over time

### Phase 3: Better Features (Month 2)
1. **Card text** - Scryfall oracle text embeddings
2. **Card types** - Creature/instant/sorcery/land
3. **Mana costs** - CMC distribution in decks

---

## API Design

```python
# Use Case 1: Format-specific building
POST /suggest/format
{
  "format": "Modern",
  "archetype": "Burn",
  "current_deck": ["Lightning Bolt", "Monastery Swiftspear", ...],
  "budget_max": 100
}

# Use Case 2: Budget alternatives
POST /suggest/budget
{
  "card": "Force of Will",
  "format": "Legacy",
  "max_price": 5
}

# Use Case 3: Archetype staples
GET /archetype/Reanimator/staples?format=Legacy

# Use Case 4: Meta trends
GET /meta/trending?card=Ledger+Shredder&days=30

# Use Case 5: Sideboard tech
GET /archetype/Affinity/sideboard?format=Modern
```

---

## Success Metrics

**Not**: "Precision @ 10 on generic similarity"

**Instead**:
- "% of suggestions legal in requested format" (should be 100%)
- "% of suggestions under budget constraint" (should be 100%)
- "% of archetype staples that expert agrees with" (target: 70%+)
- "Sideboard suggestions that appear in > 20% of decks" (measure adoption)

**Key insight**: Constrained problems are easier than general similarity.




