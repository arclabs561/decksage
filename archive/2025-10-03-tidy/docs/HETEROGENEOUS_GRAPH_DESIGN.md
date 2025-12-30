# Heterogeneous Graph Design for Card Similarity

## Current (Wrong): Homogeneous Graph

```
Card -- co_occurs (count) --> Card
```

Treats all co-occurrence equally:
- Pack contents (forced by rarity)
- Deck choices (intentional synergy)
- Format restrictions
- Archetype patterns

## Correct: Heterogeneous Graph

### Node Types

```python
nodes = {
    'card': ['Lightning Bolt', 'Brainstorm', ...],
    'deck': ['deck_001', 'deck_002', ...],
    'set': ['Foundations', 'Modern Horizons 3', ...],
    'pack_type': ['draft_booster', 'set_booster', 'collector_booster'],
    'format': ['Modern', 'Legacy', 'Pauper', 'Commander'],
    'archetype': ['Burn', 'Control', 'Combo', 'Aggro'],
    'event': ['GP_Vegas_2024', 'SCG_Open_Baltimore', ...],
    'player': ['player_001', 'player_002', ...]
}
```

### Edge Types

```python
edges = {
    # Pack context
    ('card', 'appears_in_pack', 'set'): {
        weight: rarity_adjusted_count,
        attributes: ['rarity', 'pack_type']
    },
    
    # Deck context (MOST IMPORTANT)
    ('card', 'in_deck', 'deck'): {
        weight: count_in_deck,
        attributes: ['partition (main/side)', 'position']
    },
    
    # Archetype
    ('card', 'staple_of', 'archetype'): {
        weight: frequency_in_archetype,
        attributes: ['core (yes/no)', 'flex_slot']
    },
    
    # Format legality
    ('card', 'legal_in', 'format'): {
        weight: 1.0,
        attributes: ['restricted', 'banned']
    },
    
    # Tournament success
    ('deck', 'placed_in', 'event'): {
        weight: 1.0,
        attributes: ['placement (1st, 2nd, top8)', 'num_players']
    },
    
    # Player preferences
    ('player', 'built', 'deck'): {
        weight: 1.0,
        attributes: ['skill_rating']
    },
    
    # Deck archetype
    ('deck', 'is_archetype', 'archetype'): {
        weight: coherence_score
    }
}
```

## Metapath2Vec Approach

Instead of random walks on homogeneous graph, use metapaths:

### Metapath 1: Card Synergy
```
Card -in_deck-> Deck -in_deck-> Card
```

Meaning: Cards that appear in same decks (intentional choices)

### Metapath 2: Archetype Staples  
```
Card -staple_of-> Archetype -staple_of-> Card
```

Meaning: Cards that define same archetype

### Metapath 3: Winning Combinations
```
Card -in_deck-> Deck -placed_in-> Event
```

Weight by placement: 1st place decks have higher weight

### Metapath 4: Format-Specific
```
Card -legal_in-> Format -legal_in-> Card
```

### Metapath 5: Pack Co-occurrence (LOW WEIGHT)
```
Card -in_pack-> Set -in_pack-> Card
```

This is NOISE, not signal (random booster contents)

## Why This Matters

Example: Lightning Bolt

**Homogeneous (current):**
```
Lightning Bolt -- co_occurs --> Mountain (in every red deck)
Lightning Bolt -- co_occurs --> Chain Lightning (in Burn)
Lightning Bolt -- co_occurs --> Preordain (in some set's packs)
```

All treated equally!

**Heterogeneous (correct):**
```
Lightning Bolt -in_deck-> BurnDeck001 -placed-> 1st_place (HIGH WEIGHT)
Lightning Bolt -staple_of-> Burn_Archetype (SEMANTIC)
Lightning Bolt -legal_in-> Modern (CONSTRAINT)
Lightning Bolt -in_pack-> Foundations (NOISE, low weight)
```

Each edge type has different meaning!

## Implementation with PyTorch Geometric

```python
from torch_geometric.data import HeteroData

data = HeteroData()

# Node features
data['card'].x = card_features  # [num_cards, feature_dim]
data['deck'].x = deck_features  # [num_decks, feature_dim]

# Edge indices and types
data['card', 'in_deck', 'deck'].edge_index = torch.tensor([...])
data['card', 'in_deck', 'deck'].edge_attr = torch.tensor([...])  # count, partition

data['deck', 'placed_in', 'event'].edge_index = torch.tensor([...])
data['deck', 'placed_in', 'event'].edge_attr = torch.tensor([...])  # placement

# Metapath2Vec or HeteroGNN
from torch_geometric.nn import HGTConv  # Heterogeneous Graph Transformer

# Learn separate embeddings for each node type
# Use metapaths to capture different semantic relationships
```

## Data We Have vs Need

**Have:**
- Deck lists (cards in decks) ✓
- Format labels (in metadata, can't parse yet) ⚠️
- Archetype labels (in metadata, can't parse yet) ⚠️
- Dates (in metadata) ⚠️

**Missing:**
- Pack contents (booster configurations)
- Tournament placements (need to parse from URLs/scrape)
- Player IDs (in some sources)
- Win rates (need external source like 17lands)

**Can Build Now:**
- Card-Deck edges ✓ (have deck lists)
- Deck-Archetype (if we fix parsing)
- Card-Archetype (derived from above)

**Can't Build Yet:**
- Card-Pack (don't have pack contents)
- Deck-Event-Placement (need to extract from tournament results)
- Win rate edges (need external data)

## Immediate Next Step

Build simplified heterogeneous graph with what we HAVE:
```
Card -in_deck-> Deck
Deck -has_format-> Format (if parseable)
```

This is already better than homogeneous!

## Experiment Design

exp_042: Heterogeneous graph with Card-Deck-Format structure
  - Distinguish deck choices from pack randomness
  - Use metapath: Card -in_deck-> Deck -same_format-> Deck -in_deck-> Card
  - Should beat homogeneous co-occurrence

Expected: P@10 > 0.12 (finally an improvement!)


