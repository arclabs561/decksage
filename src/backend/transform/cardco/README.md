# Card Co-occurrence Transform

**Purpose**: Build card similarity matrices from deck/collection data

## What It Does

Analyzes collections (decks, sets, cubes) to find which cards appear together, creating a co-occurrence matrix useful for:

- **Card recommendations**: "Cards similar to Lightning Bolt"
- **Deck building**: "What cards work well with this one?"
- **Meta analysis**: "What cards are played together in top decks?"

## Algorithm

For each collection:
1. Iterate through all partitions (Main Deck, Sideboard, etc.)
2. For each pair of cards in the partition:
   - **Set count**: Increment by 1 (cards appear together)
   - **Multiset count**: Increment by count1 × count2 (weighted by copies)

Example:
```
Deck with:
- 4x Lightning Bolt  
- 2x Monastery Swiftspear

Co-occurrence:
- (Lightning Bolt, Monastery Swiftspear): set=1, multiset=8
- (Lightning Bolt, Lightning Bolt): set=0, multiset=6 (self-pairs from 4 copies)
```

## Output Format

**CSV**: `pairs.csv`
```csv
NAME_1,NAME_2,COUNT_SET,COUNT_MULTISET
Lightning Bolt,Monastery Swiftspear,1,8
Lightning Bolt,Lava Spike,1,16
```

**JSON**: `cooccurrence.json`
```json
{
  "pairs": [
    {
      "card1": "Lightning Bolt",
      "card2": "Monastery Swiftspear",
      "set_count": 142,
      "multiset_count": 2847
    }
  ],
  "metadata": {
    "total_collections": 100,
    "total_pairs": 5420,
    "game": "magic"
  }
}
```

## Usage

```go
import "collections/transform/cardco"

// Create transform
tr, err := cardco.NewTransform(ctx, log)
if err != nil {
    return err
}
defer tr.Close()

// Run transform on datasets
output, err := tr.Transform(ctx, datasets,
    &transform.OptTransformLimit{Limit: 1000},
    &transform.OptTransformParallel{Parallel: 64},
)

// Export results
if err := tr.ExportCSV("pairs.csv"); err != nil {
    return err
}
```

## From CLI

```bash
cd src/backend

# Transform MTG decks
go run ./cmd/dataset transform mtgtop8 \
  --limit=100 \
  --output=pairs.csv \
  --bucket=file://./data

# Transform all datasets
go run ./cmd/dataset transform scryfall,mtgtop8,goldfish \
  --limit=1000 \
  --output=cooccurrence.json \
  --format=json
```

## Applications

### 1. Card Similarity Search

```python
import pandas as pd

# Load co-occurrence matrix
df = pd.read_csv('pairs.csv')

# Find cards similar to "Lightning Bolt"
similar = df[
    (df['NAME_1'] == 'Lightning Bolt') | 
    (df['NAME_2'] == 'Lightning Bolt')
].sort_values('COUNT_MULTISET', ascending=False).head(10)
```

### 2. Deck Recommendations

Given a partial deck, suggest cards that often appear with the cards you have.

### 3. Meta Analysis

```python
# Most co-occurring pairs in the meta
top_pairs = df.sort_values('COUNT_SET', ascending=False).head(20)
```

### 4. Archetype Detection

Cluster cards by co-occurrence patterns to discover deck archetypes.

## Implementation Notes

- Uses **Badger KV store** for efficient aggregation
- Symmetric pairs: `(A, B) == (B, A)` stored once
- Self-pairs included for multiset (e.g., 4 Lightning Bolts → 6 self-pairs)
- Parallel processing with configurable workers
- Memory efficient: streams results without loading all pairs

## Performance

- **100 decks**: ~30 seconds, ~50K pairs
- **1000 decks**: ~5 minutes, ~500K pairs  
- **10000 decks**: ~45 minutes, ~3M pairs

Memory usage: O(unique pairs) ≈ 100MB per 1M pairs
