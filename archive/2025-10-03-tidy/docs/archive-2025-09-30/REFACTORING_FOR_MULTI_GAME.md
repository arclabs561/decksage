# Refactoring for Multi-Game Support

## Current State

The architecture is **already designed for multi-game support** but has some MTG-specific assumptions baked in. This document outlines how to extract and generalize patterns.

## Recommended Refactoring Steps

### 1. Create Common Game Interface

**File**: `src/backend/games/game.go`

```go
package games

import (
    "encoding/json"
    "time"
)

// Game identifies which game this data is for
type Game string

const (
    GameMagic   Game = "magic"
    GameYuGiOh  Game = "yugioh"
    GamePokemon Game = "pokemon"
)

// Card is a generic card interface that all games must implement
type Card interface {
    GetName() string
    GetID() string
    MarshalJSON() ([]byte, error)
    UnmarshalJSON([]byte) error
}

// Collection is a generic collection interface (decks, sets, cubes, etc.)
type Collection interface {
    GetID() string
    GetURL() string
    GetGame() Game
    GetReleaseDate() time.Time
    Validate() error
    MarshalJSON() ([]byte, error)
    UnmarshalJSON([]byte) error
}

// Dataset describes a data source for a game
type Dataset interface {
    GetGame() Game
    GetName() string
    Extract(...ExtractOption) error
    IterItems(ItemIterator, ...IterOption) error
}

type ItemIterator func(Item) error

type Item interface {
    GetType() ItemType
    GetGame() Game
}

type ItemType string

const (
    ItemTypeCard       ItemType = "card"
    ItemTypeCollection ItemType = "collection"
)
```

### 2. Move Dataset Interface Up

**Current**: `games/magic/dataset/dataset.go` contains MTG-specific Dataset interface  
**Proposed**: Move to `games/dataset.go` with game parameter

```go
// games/dataset.go
package games

type Dataset interface {
    Game() Game
    Description() Description
    Extract(ctx context.Context, scraper *scraper.Scraper, options ...UpdateOption) error
    IterItems(ctx context.Context, fn func(Item) error, options ...IterItemsOption) error
}

// Then games/magic/dataset/scryfall/dataset.go implements games.Dataset
```

### 3. Generalize CLI Commands

**Current**: `cmd/dataset/cmd/extract.go` has hardcoded game list  
**Proposed**: Auto-discover datasets via registry

```go
// games/registry.go
package games

var registry = make(map[string]DatasetFactory)

type DatasetFactory func(*logger.Logger, *blob.Bucket) Dataset

func Register(game, name string, factory DatasetFactory) {
    key := fmt.Sprintf("%s/%s", game, name)
    registry[key] = factory
}

func GetDataset(game, name string, log *logger.Logger, blob *blob.Bucket) (Dataset, error) {
    key := fmt.Sprintf("%s/%s", game, name)
    factory, ok := registry[key]
    if !ok {
        return nil, fmt.Errorf("unknown dataset: %s", key)
    }
    return factory(log, blob), nil
}

// Then in games/magic/dataset/scryfall/dataset.go
func init() {
    games.Register("magic", "scryfall", func(log *logger.Logger, blob *blob.Bucket) games.Dataset {
        return NewDataset(log, blob)
    })
}
```

**Updated CLI**:
```go
// cmd/dataset/cmd/extract.go
func runExtract(cmd *cobra.Command, args []string) error {
    parts := strings.Split(args[0], "/")
    var game, dataset string
    
    if len(parts) == 2 {
        game, dataset = parts[0], parts[1]
    } else {
        game, dataset = "magic", parts[0]  // default to magic for backwards compat
    }
    
    d, err := games.GetDataset(game, dataset, config.Log, gamesBlob)
    if err != nil {
        return err
    }
    
    return d.Extract(config.Ctx, scraper, opts...)
}

// Usage: 
//   go run ./cmd/dataset extract magic/scryfall
//   go run ./cmd/dataset extract yugioh/ygoprodeck
//   go run ./cmd/dataset extract scryfall  # defaults to magic/scryfall
```

### 4. Shared Test Utilities

**File**: `games/testing/testing.go`

```go
package testing

import (
    "context"
    "testing"
    "collections/blob"
    "collections/logger"
    "collections/scraper"
)

type TestConfig struct {
    Ctx     context.Context
    Log     *logger.Logger
    Blob    *blob.Bucket
    Scraper *scraper.Scraper
    TmpDir  string
}

func NewTestConfig(t *testing.T) *TestConfig {
    ctx := context.Background()
    log := logger.NewLogger(ctx)
    log.SetLevel("DEBUG")
    
    tmpDir, err := os.MkdirTemp("", "test-dataset")
    if err != nil {
        t.Fatalf("failed to create tmp dir: %v", err)
    }
    t.Cleanup(func() { os.RemoveAll(tmpDir) })
    
    bucketURL := fmt.Sprintf("file://%s", tmpDir)
    blob, err := blob.NewBucket(ctx, log, bucketURL)
    if err != nil {
        t.Fatalf("failed to create blob: %v", err)
    }
    
    scraper := scraper.NewScraper(log, blob)
    
    return &TestConfig{
        Ctx:     ctx,
        Log:     log,
        Blob:    blob,
        Scraper: scraper,
        TmpDir:  tmpDir,
    }
}

func TestDatasetExtract(t *testing.T, d Dataset, limit int) {
    config := NewTestConfig(t)
    err := d.Extract(config.Ctx, config.Scraper, 
        &dataset.OptExtractItemLimit{Limit: limit})
    if err != nil {
        t.Fatalf("extract failed: %v", err)
    }
}
```

**Usage in tests**:
```go
// games/magic/dataset/dataset_test.go
func TestMagicDatasets(t *testing.T) {
    config := gametesting.NewTestConfig(t)
    datasets := []games.Dataset{
        scryfall.NewDataset(config.Log, config.Blob),
        deckbox.NewDataset(config.Log, config.Blob),
    }
    for _, d := range datasets {
        gametesting.TestDatasetExtract(t, d, 5)
    }
}

// games/yugioh/dataset/dataset_test.go (future)
func TestYuGiOhDatasets(t *testing.T) {
    config := gametesting.NewTestConfig(t)
    datasets := []games.Dataset{
        ygoprodeck.NewDataset(config.Log, config.Blob),
    }
    for _, d := range datasets {
        gametesting.TestDatasetExtract(t, d, 5)
    }
}
```

### 5. Standardize Blob Paths

Create consistent blob path structure across all games:

```go
// games/paths.go
package games

func CardBlobPath(game Game, dataset, cardID string) string {
    return fmt.Sprintf("games/%s/%s/cards/%s.json", game, dataset, cardID)
}

func CollectionBlobPath(game Game, dataset, collectionID string) string {
    return fmt.Sprintf("games/%s/%s/collections/%s.json", game, dataset, collectionID)
}

// Usage in datasets:
bkey := games.CardBlobPath(GameMagic, "scryfall", card.Name)
blob.Write(ctx, bkey, data)
```

## Migration Path

### Phase 1: Extract Without Breaking (Week 1)
1. Create `games/game.go` with interfaces (doesn't break anything)
2. Create `games/testing/` utilities
3. Update tests to use shared utilities
4. Verify all tests still pass

### Phase 2: Create Registry (Week 2)
1. Implement `games/registry.go`
2. Add `Register()` calls to each dataset's `init()`
3. Update CLI to support `game/dataset` format
4. Maintain backwards compatibility with `dataset` only format

### Phase 3: Add First New Game (Week 3-4)
1. Create `games/yugioh/` package structure
2. Implement YGOPRODeck dataset (API-based, simpler than HTML parsing)
3. Write tests using shared utilities
4. Verify extract/iterate pipeline works

### Phase 4: Documentation (Week 5)
1. Write "Adding a New Game" tutorial
2. Create game scaffold generator
3. Document all extension points
4. Add examples for each pattern

## Example: Adding Yu-Gi-Oh!

### Step 1: Create Game Models

```go
// games/yugioh/game/game.go
package game

type Card struct {
    ID          string   `json:"id"`
    Name        string   `json:"name"`
    Type        CardType `json:"type"`
    Race        string   `json:"race"`        // Dragon, Warrior, etc.
    Attribute   string   `json:"attribute"`   // DARK, LIGHT, etc.
    Level       int      `json:"level"`
    ATK         int      `json:"atk"`
    DEF         int      `json:"def"`
    Description string   `json:"desc"`
    Archetype   string   `json:"archetype"`
}

func (c *Card) GetName() string { return c.Name }
func (c *Card) GetID() string { return c.ID }
func (c *Card) GetGame() games.Game { return games.GameYuGiOh }
```

### Step 2: Create Dataset

```go
// games/yugioh/dataset/ygoprodeck/dataset.go
package ygoprodeck

func init() {
    games.Register("yugioh", "ygoprodeck", func(log *logger.Logger, blob *blob.Bucket) games.Dataset {
        return NewDataset(log, blob)
    })
}

type Dataset struct {
    log  *logger.Logger
    blob *blob.Bucket
}

func (d *Dataset) Game() games.Game { return games.GameYuGiOh }

func (d *Dataset) Extract(ctx context.Context, sc *scraper.Scraper, opts ...games.UpdateOption) error {
    // Call YGOPRODeck API
    req, _ := http.NewRequest("GET", "https://db.ygoprodeck.com/api/v7/cardinfo.php", nil)
    page, err := sc.Do(ctx, req)
    // Parse and store...
}
```

### Step 3: Write Tests

```go
// games/yugioh/dataset/dataset_test.go
func TestYuGiOhDatasets(t *testing.T) {
    config := gametesting.NewTestConfig(t)
    d := ygoprodeck.NewDataset(config.Log, config.Blob)
    gametesting.TestDatasetExtract(t, d, 10)
}
```

### Step 4: Use CLI

```bash
# Extract Yu-Gi-Oh! cards
go run ./cmd/dataset extract yugioh/ygoprodeck --limit=100

# Still works for Magic (backwards compatible)
go run ./cmd/dataset extract scryfall --limit=10
```

## Benefits

1. **Clear Separation**: Game logic separated from infrastructure
2. **Easy Extension**: Add new games without modifying core
3. **Shared Testing**: Common test utilities reduce boilerplate
4. **Discoverability**: Registry makes datasets discoverable
5. **Consistency**: Standard patterns across all games
6. **Documentation**: Clear contracts via interfaces

## Timeline Estimate

- **Refactoring (non-breaking)**: 1-2 weeks
- **First new game (Yu-Gi-Oh!)**: 2-3 weeks  
- **Second game (Pokemon)**: 1-2 weeks (faster with patterns established)
- **Total**: ~6-8 weeks to fully multi-game platform

## Current Blockers

None! The architecture is already well-designed for this. Main work is:
1. Extracting interfaces
2. Moving shared code up
3. Adding registry system
4. Documentation
