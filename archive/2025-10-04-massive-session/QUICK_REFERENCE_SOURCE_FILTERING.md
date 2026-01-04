# Quick Reference: Source Filtering API

## Python Data Loading

### Load Tournament Decks Only
```python
from utils.data_loading import load_tournament_decks

decks = load_tournament_decks()  # mtgtop8 + goldfish
# Returns: 55,293 decks
```

### Advanced Filtering
```python
from utils.data_loading import load_decks_jsonl

# Modern only
modern = load_decks_jsonl(formats=['Modern'])

# Top 8 finishes only
top8 = load_decks_jsonl(max_placement=8)

# Combined: Modern Top 8 from mtgtop8
modern_top8 = load_decks_jsonl(
    sources=['mtgtop8'],
    formats=['Modern'],
    max_placement=8
)
```

### Statistics
```python
from utils.data_loading import deck_stats

stats = deck_stats(decks)
print(f"Total: {stats['total']}")
print(f"By source: {stats['by_source']}")
print(f"By format: {stats['by_format']}")
print(f"Has player: {stats['has_player']}")
```

## Go Analysis

### Analyze Dataset
```bash
cd src/backend/cmd/analyze-decks
./analyze-decks ../../data-full/games/magic
```

Shows:
- Format distribution
- Source distribution
- Metadata coverage
- Top players
- Recommendations

### Export with Metadata
```bash
cd src/backend
go run ./cmd/export-hetero data-full/games/magic decks_hetero.jsonl
```

Exports all decks with:
- source, player, event, placement, event_date
- archetype, format, cards with partitions

## Data Model

### Collection Fields
- `source`: "mtgtop8", "goldfish", "deckbox", "unknown"
- All other standard fields (id, url, type, etc.)

### Deck Fields (MTG)
- `player`: Player name (when available)
- `event`: Tournament name (when available)
- `placement`: 1 = 1st, 2 = 2nd, etc., 0 = unknown
- `event_date`: Event date string (when available)

## Current Coverage
- **Source**: 55,293/55,293 (100.0%)
- **Player**: 1/55,293 (0.0%) - new decks only
- **Event**: 1/55,293 (0.0%) - new decks only
- **Placement**: 1/55,293 (0.0%) - new decks only

Note: Historical decks have source tracking only. New decks (scraped after Oct 4, 2025) have full metadata.
