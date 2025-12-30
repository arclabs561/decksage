# DeckSage Architecture

## Design Philosophy

**DeckSage is designed as a multi-game card game data collection and analysis platform**, supporting any card game with similar data patterns (decks, sets, individual cards). Currently implements Magic: The Gathering, with architecture ready for Yu-Gi-Oh!, Pokemon, and other TCGs.

## Directory Structure

```
src/backend/
├── games/                    # Game-specific implementations
│   ├── magic/               # Magic: The Gathering
│   │   ├── dataset/        # Data source scrapers
│   │   │   ├── scryfall/   # Card database
│   │   │   ├── deckbox/    # User collections
│   │   │   ├── goldfish/   # Tournament decks
│   │   │   └── mtgtop8/    # Tournament results
│   │   ├── game/           # MTG data models
│   │   └── store/          # MTG-specific storage
│   ├── yugioh/             # [Future] Yu-Gi-Oh!
│   └── pokemon/            # [Future] Pokemon TCG
├── scraper/                 # Generic HTTP scraper (game-agnostic)
├── blob/                    # Generic blob storage (game-agnostic)
├── transform/               # Data transformation pipeline
├── search/                  # Search indexing
└── cmd/                     # CLI commands
    ├── dataset/            # Dataset extraction tool
    └── server/             # [Future] API server
```

## Core Abstractions

### Game-Agnostic Layer

**Scraper** (`scraper/scraper.go`)
- Generic HTTP client with rate limiting
- Response caching in blob storage
- Retry logic and throttling detection
- **Used by all games**

**Blob Storage** (`blob/blob.go`)
- Abstraction over file:// and s3:// storage
- Key-value interface for storing scraped/parsed data
- **Used by all games**

### Game-Specific Layer

Each game implements:

**Dataset Interface** (`games/[game]/dataset/dataset.go`)
```go
type Dataset interface {
    Description() Description
    Extract(ctx, scraper, options) error
    IterItems(ctx, fn, options) error
}
```

**Data Models** (`games/[game]/game/game.go`)
```go
type Card struct { ... }           // Game-specific card representation
type Collection struct { ... }     // Decks, sets, cubes, etc.
type CollectionType interface { ... }
```

**Dataset Implementations**
- Each website is a separate dataset implementation
- Parses HTML/JSON into game-specific models
- Stores in blob storage under `games/{game}/{dataset}/`

## Data Flow

```
1. EXTRACT
   User runs: go run ./cmd/dataset extract [dataset-name]
   ↓
   Scraper fetches pages (with caching)
   ↓
   Dataset parses HTML → Game models
   ↓
   Store in blob: games/{game}/{dataset}/{id}.json

2. TRANSFORM [Future]
   Read from blob storage
   ↓
   Normalize/enrich data
   ↓
   Store in processed format

3. INDEX [Future]
   Read processed data
   ↓
   Index in search engine (MeiliSearch)
   ↓
   Enable similarity search, recommendations
```

## Adding a New Game

To add Yu-Gi-Oh! or Pokemon support:

### 1. Create Game Package
```
src/backend/games/yugioh/
├── game/
│   └── game.go          # Card, Deck, Set models
├── dataset/
│   ├── dataset.go       # Dataset interface
│   ├── ygoprodeck/      # Dataset: YGOPRODeck API
│   └── duelistsunite/   # Dataset: Duelists Unite
└── store/
    └── store.go         # Game-specific storage logic
```

### 2. Define Game Models
```go
// games/yugioh/game/game.go
type Card struct {
    Name        string
    Type        CardType  // Monster, Spell, Trap
    Attribute   string    // DARK, LIGHT, etc.
    Level       int
    ATK         int
    DEF         int
    Description string
    Archetype   string
}

type Deck struct {
    ID          string
    URL         string
    Name        string
    MainDeck    []CardDesc
    ExtraDeck   []CardDesc
    SideDeck    []CardDesc
    ReleaseDate time.Time
}
```

### 3. Implement Dataset
```go
// games/yugioh/dataset/ygoprodeck/dataset.go
type Dataset struct {
    log  *logger.Logger
    blob *blob.Bucket
}

func (d *Dataset) Extract(ctx context.Context, sc *scraper.Scraper, opts ...dataset.UpdateOption) error {
    // Fetch from YGOPRODeck API
    // Parse JSON into yugioh.Card and yugioh.Deck
    // Store in blob: games/yugioh/ygoprodeck/{id}.json
}
```

### 4. Register in CLI
```go
// cmd/dataset/cmd/extract.go
switch datasetName {
case "ygoprodeck":
    d = ygoprodeck.NewDataset(config.Log, gamesBlob)
// ...
}
```

### 5. Write Tests
```go
// games/yugioh/dataset/dataset_test.go
func TestYuGiOhDatasets(t *testing.T) {
    datasets := []dataset.Dataset{
        ygoprodeck.NewDataset(log, blob),
    }
    // ...
}
```

## Current Implementation Status

### ✅ Implemented
- **Core Infrastructure**: Scraper, blob storage, CLI framework
- **Magic: The Gathering**: 4 datasets, data models, basic testing

### 🚧 Partial
- **Testing**: Basic tests exist but need expansion
- **Transform Pipeline**: Structure exists but not fully implemented

### ❌ Not Yet Implemented
- **Yu-Gi-Oh!**: Game package, datasets
- **Pokemon TCG**: Game package, datasets
- **API Server**: REST API for querying data
- **Search Index**: MeiliSearch integration for similarity search
- **ML Features**: Card recommendations, deck similarity

## Design Patterns

### Dataset Pattern
Each website is a **Dataset** that:
1. Knows how to find items (scrolling, pagination)
2. Knows how to parse item pages into game models
3. Stores in a consistent blob structure
4. Can iterate over stored items

### Blob Storage Pattern
```
games/{game}/{dataset}/
  ├── cards/{card-name}.json
  └── collections/{collection-id}.json

scraper/{hostname}/
  └── {hash}.json    # Cached HTTP responses
```

### Options Pattern
Functions accept variadic options for flexibility:
```go
d.Extract(ctx, scraper,
    &dataset.OptExtractItemLimit{Limit: 100},
    &dataset.OptExtractParallel{Parallel: 64},
    &dataset.OptExtractSectionOnly{Section: "cards"},
)
```

## Testing Strategy

### Unit Tests
- Game model validation (`game/game_test.go`)
- Parser logic for each dataset
- Data transformation functions

### Integration Tests
- Full extract pipeline with fixture data
- Blob storage read/write
- Scraper caching behavior

### E2E Tests (Limited)
- Extract small sample from real websites
- Verify data quality and completeness

## Extensibility

The architecture supports:

1. **New Games**: Add package under `games/{game}/`
2. **New Datasets**: Implement Dataset interface
3. **New Storage Backends**: Implement blob interface
4. **New Transforms**: Add to transform pipeline
5. **New Search Backends**: Swap search implementation

## Performance Considerations

- **Parallel Processing**: Configurable worker pools for parsing
- **Rate Limiting**: Per-dataset or global rate limits
- **Caching**: All HTTP responses cached in blob storage
- **Streaming**: Iterate over large datasets without loading all in memory

## Future Enhancements

1. **GraphQL API**: Unified query interface across games
2. **Card Similarity**: Embedding-based recommendations
3. **Deck Analysis**: Win rates, meta analysis, popularity
4. **Image Processing**: OCR for card recognition
5. **Real-time Updates**: Webhooks for new deck publications
6. **Multi-language**: Support for non-English cards
7. **Historical Tracking**: Track meta shifts over time
