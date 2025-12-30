# Working Tools Summary - October 3, 2025

## What We Built

All tools use co-occurrence data's **strength** (frequency analysis), not its weakness (similarity).

### 1. Archetype Staples (`archetype_staples.py`) ✅
**Use case**: "What should I put in my Burn deck?"

**Example output**:
- Red Deck Wins: 99.6% Mountain, 71% Burst Lightning
- Reanimator: 89% Archon of Cruelty, 81% Reanimate, 74% Entomb
- Boros Aggro: 70% Ocelot Pride, Guide of Souls, Ajani

**Why it works**: Shows what 70%+ of successful decks play

### 2. Sideboard Analysis (`sideboard_analysis.py`) ✅
**Use case**: "What do people sideboard?"

**Example output**:
- Most popular sideboard card: Consign to Memory (825 decks)
- Boros Aggro: 79% Wear/Tear, 64% Celestial Purge
- Sideboard-only cards: Pyroblast, Blue/Red Elemental Blast (color hosers)

**Why it works**: Partition data (Main vs Sideboard) shows strategic choices

### 3. Card Companions (`card_companions.py`) ✅
**Use case**: "What cards work with Lightning Bolt?"

**Example output**:
- Lightning Bolt: 77.8% Mountain, 25.8% Chain Lightning, 22.6% Fireblast
- Brainstorm: 83.4% Island, 73% Ponder, 66% Polluted Delta
- Sol Ring: 84.5% Ancient Tomb, 79.3% Mana Vault, 77.5% Lotus Petal

**Why it works**: Shows actual deck construction packages, not "similarity"

### 4. Deck Composition Stats (`deck_composition_stats.py`) ✅
**Use case**: "What's typical deck structure?"

**Example output**:
- Red Deck Wins: 21 unique cards, 3.6x avg copies (hyper-consistent)
- Dimir Control: 33 unique cards, 2.3x avg copies (toolbox)
- cEDH: 100 cards, 0% sideboards (singleton format)

**Why it works**: Statistical analysis of deck structure patterns

## Performance

All tools run instantly on 4,718 decks:
- Archetype staples: < 1 second
- Sideboard analysis: < 1 second  
- Card companions: < 1 second
- Composition stats: < 1 second

## Why These Work While Similarity Doesn't

**Co-occurrence is good at**:
- ✅ Frequency: "What % of decks play this?"
- ✅ Composition: "What do decks contain?"
- ✅ Patterns: "What appears together?"

**Co-occurrence is bad at**:
- ❌ Similarity: "What's functionally similar?"
- ❌ Semantics: "What does this card do?"
- ❌ Substitution: "What can replace this?"

## Usage Examples

```bash
# Archetype staples
cd src/ml
uv run python archetype_staples.py

# Sideboard analysis
uv run python sideboard_analysis.py

# Card companions
uv run python card_companions.py

# Deck composition
uv run python deck_composition_stats.py
```

## Next Tools to Build

Using the same approach:
1. **Meta trends over time** - Track card frequency changes
2. **Budget alternatives** - Filter by price + co-occurrence
3. **Format-specific staples** - Not filtering similarity, but showing "90% of Modern decks play fetch lands"
4. **Archetype evolution** - How has Burn changed over time?

## Lesson Learned

Stop chasing P@10 improvements. Build tools that use the data's actual strengths.

**Reality**: Co-occurrence at P@10 = 0.08 for similarity, but 100% useful for composition analysis.
