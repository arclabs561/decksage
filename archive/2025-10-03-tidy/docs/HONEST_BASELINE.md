# DeckSage Baseline - October 2025

## Performance

**Co-occurrence similarity on tournament decks:**
- P@10: **0.08** (38-query test set)
- Data: 4,718 tournament decks (Modern, Pauper, Legacy, cEDH, Standard, Pioneer, Vintage)
- Method: Jaccard similarity on card co-occurrence graphs

## What This Means

**Realistic performance** on diverse queries including:
- Staples (Lightning Bolt, Brainstorm)
- Ramp (Sol Ring, Arcane Signet)
- Interaction (Counterspell, Fatal Push)
- Utility lands (Ancient Tomb, Boseiju)

**Not cherry-picked.** Previous claims of 0.12-0.15 were on smaller test sets.

## Use Cases That Work

### ✅ Archetype Discovery
Query: "What cards appear with Lightning Bolt?"
→ Red aggro staples (good!)

### ✅ Format-Specific Suggestions
Query: "Pauper cards similar to Counterspell"
→ Format-appropriate alternatives

### ✅ Meta Analysis
Track which cards co-occur in winning decks

### ❌ Functional Similarity
Query: "Cards like Lightning Bolt"
→ Returns other burn spells BUT also creatures from same decks
→ Co-occurrence ≠ function

## Next Steps

1. **More data**: Expand to 10K+ decks across more sources
2. **Specific use cases**: Format-specific, budget substitutes, archetype staples
3. **Better features**: Add text embeddings, card types, mana costs
4. **Different metrics**: Deck-level similarity, not just card pairs

## Honest Claims

**Do claim:**
- "Discovers card relationships from tournament data"
- "Suggests cards based on competitive play patterns"
- "P@10 ~ 0.08 on diverse queries"

**Don't claim:**
- "Production-ready card similarity"
- "Finds functional equivalents"
- "Matches human expert judgment"



