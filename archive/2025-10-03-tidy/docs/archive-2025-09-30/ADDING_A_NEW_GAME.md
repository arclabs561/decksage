# Adding a New Game to DeckSage

**Status**: Architecture validated with MTG implementation
**Time Required**: ~2-3 days for a new game with 2-3 data sources

## Architecture Overview

DeckSage separates **game-agnostic** infrastructure from **game-specific** implementations:

```
games/                    # Shared (all games)
├── game.go              # Collection, Partition, CardDesc, CollectionType interface
└── dataset.go           # Dataset interface, update options, iteration

games/{game}/            # Game-specific
├── game/
│   └── game.go          # Card struct, CollectionType implementations
└── dataset/
    ├── {source1}/       # First data source (e.g., ygoprodeck)
    ├── {source2}/       # Second data source
    └── dataset.go       # Game-specific dataset helpers
```

## Universal Types (Already Provided)

These are **shared across all games** in `games/game.go`:

- **`games.Collection`** - A collection of cards (deck/set/cube)
- **`games.Partition`** - A named group of cards (e.g., "Main Deck", "Extra Deck")
- **`games.CardDesc`** - A card reference with count
- **`games.CollectionType`** - Interface for game-specific metadata
- **`games.Canonicalize()`** - Universal validation logic

## Step-by-Step Guide: Adding Yu-Gi-Oh!

### Step 1: Create Game Package Structure

```bash
mkdir -p src/backend/games/yugioh/game
mkdir -p src/backend/games/yugioh/dataset
```

### Step 2: Define Game-Specific Card Type

**File: `games/yugioh/game/game.go`**

```go
package game

import "collections/games"

// Register Yu-Gi-Oh! collection types
func init() {
	games.RegisterCollectionType("YGODeck", func() games.CollectionType {
		return new(CollectionTypeDeck)
	})
	games.RegisterCollectionType("YGOCollection", func() games.CollectionType {
		return new(CollectionTypeCollection)
	})
}

// Type aliases for shared types
type (
	CardDesc              = games.CardDesc
	Collection            = games.Collection
	Partition             = games.Partition
	CollectionType        = games.CollectionType
	CollectionTypeWrapper = games.CollectionTypeWrapper
)

// Yu-Gi-Oh! specific Card structure
type Card struct {
	Name        string      `json:"name"`
	Type        CardType    `json:"type"`       // Monster, Spell, Trap
	Attribute   string      `json:"attribute"`  // DARK, LIGHT, etc.
	Level       int         `json:"level,omitempty"`
	Rank        int         `json:"rank,omitempty"`
	LinkRating  int         `json:"link_rating,omitempty"`
	ATK         int         `json:"atk,omitempty"`
	DEF         int         `json:"def,omitempty"`
	Description string      `json:"description"`
	Archetype   string      `json:"archetype,omitempty"`
	Race        string      `json:"race,omitempty"`        // Dragon, Warrior, etc.
	Images      []CardImage `json:"images,omitempty"`
}

type CardType int

const (
	TypeMonster CardType = iota
	TypeSpell
	TypeTrap
)

type CardImage struct {
	URL string `json:"url"`
}

// Yu-Gi-Oh! specific collection types

type CollectionTypeDeck struct {
	Name      string `json:"name"`
	Format    string `json:"format"`    // TCG, OCG, Speed Duel
	Archetype string `json:"archetype,omitempty"`
}

type CollectionTypeCollection struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
}

func (ct *CollectionTypeDeck) Type() string       { return "YGODeck" }
func (ct *CollectionTypeCollection) Type() string { return "YGOCollection" }

func (ct *CollectionTypeDeck) IsCollectionType()       {}
func (ct *CollectionTypeCollection) IsCollectionType() {}
```

### Step 3: Create First Dataset Implementation

**File: `games/yugioh/dataset/ygoprodeck/dataset.go`**

```go
package ygoprodeck

import (
	"collections/blob"
	"collections/games"
	"collections/games/yugioh/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) *Dataset {
	return &Dataset{
		log:  log,
		blob: blob,
	}
}

func (d *Dataset) Description() games.Description {
	return games.Description{
		Game: "yugioh",
		Name: "ygoprodeck",
	}
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	opts, err := games.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	// YGOPRODeck API endpoint
	req, err := http.NewRequest("GET", "https://db.ygoprodeck.com/api/v7/cardinfo.php", nil)
	if err != nil {
		return err
	}

	page, err := games.Do(ctx, sc, opts, req)
	if err != nil {
		return fmt.Errorf("failed to fetch cards: %w", err)
	}

	// Parse API response
	var apiResp struct {
		Data []struct {
			Name      string `json:"name"`
			Type      string `json:"type"`
			Desc      string `json:"desc"`
			Atk       int    `json:"atk"`
			Def       int    `json:"def"`
			Level     int    `json:"level"`
			Race      string `json:"race"`
			Attribute string `json:"attribute"`
			Archetype string `json:"archetype"`
			CardImages []struct {
				ImageURL string `json:"image_url"`
			} `json:"card_images"`
		} `json:"data"`
	}

	if err := json.Unmarshal(page.Response.Body, &apiResp); err != nil {
		return fmt.Errorf("failed to parse API response: %w", err)
	}

	// Store each card
	for _, cardData := range apiResp.Data {
		card := game.Card{
			Name:        cardData.Name,
			Description: cardData.Desc,
			ATK:         cardData.Atk,
			DEF:         cardData.Def,
			Level:       cardData.Level,
			Race:        cardData.Race,
			Attribute:   cardData.Attribute,
			Archetype:   cardData.Archetype,
		}

		for _, img := range cardData.CardImages {
			card.Images = append(card.Images, game.CardImage{
				URL: img.ImageURL,
			})
		}

		// Store in blob: games/yugioh/ygoprodeck/cards/{name}.json
		key := fmt.Sprintf("games/yugioh/ygoprodeck/cards/%s.json", cardData.Name)
		data, err := json.Marshal(card)
		if err != nil {
			return fmt.Errorf("failed to marshal card %s: %w", card.Name, err)
		}

		if err := d.blob.Write(ctx, key, data); err != nil {
			return fmt.Errorf("failed to write card %s: %w", card.Name, err)
		}
	}

	d.log.Infof(ctx, "Extracted %d Yu-Gi-Oh! cards from YGOPRODeck", len(apiResp.Data))
	return nil
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(item games.Item) error,
	options ...games.IterItemsOption,
) error {
	return games.IterItemsBlobPrefix(
		ctx,
		d.blob,
		"games/yugioh/ygoprodeck/",
		deserializeYGOCard,
		fn,
		options...,
	)
}

// CardItem for Yu-Gi-Oh!
type CardItem struct {
	Card *game.Card `json:"card"`
}

func (i *CardItem) Kind() string { return "Card" }
func (i *CardItem) item()        {}

func deserializeYGOCard(_ string, data []byte) (games.Item, error) {
	var card game.Card
	if err := json.Unmarshal(data, &card); err != nil {
		return nil, err
	}
	return &CardItem{Card: &card}, nil
}
```

### Step 4: Register Dataset in CLI

**File: `cmd/dataset/cmd/extract.go`** (add to switch statement)

```go
import (
	// ... existing imports
	"collections/games/yugioh/dataset/ygoprodeck"
)

// In the switch statement for dataset creation:
case "ygoprodeck":
	d = ygoprodeck.NewDataset(config.Log, gamesBlob)
```

### Step 5: Write Tests

**File: `games/yugioh/dataset/dataset_test.go`**

```go
package dataset

import (
	"collections/games/yugioh/dataset/ygoprodeck"
	"collections/logger"
	"collections/blob"
	"context"
	"testing"
)

func TestYuGiOhDatasets(t *testing.T) {
	ctx := context.Background()
	log := logger.NewLogger()

	// Create temp blob storage
	tmpBlob, err := blob.NewBucket(ctx, "file://./testdata")
	if err != nil {
		t.Fatal(err)
	}

	datasets := []struct {
		name string
		ds   games.Dataset
	}{
		{"ygoprodeck", ygoprodeck.NewDataset(log, tmpBlob)},
	}

	for _, tc := range datasets {
		t.Run(tc.name, func(t *testing.T) {
			desc := tc.ds.Description()
			if desc.Game != "yugioh" {
				t.Errorf("expected game=yugioh, got %s", desc.Game)
			}
			if desc.Name != tc.name {
				t.Errorf("expected name=%s, got %s", tc.name, desc.Name)
			}
		})
	}
}
```

### Step 6: Test Extraction

```bash
cd src/backend

# Extract Yu-Gi-Oh! cards
export SCRAPER_RATE_LIMIT=100/m
go run ./cmd/dataset extract ygoprodeck \
  --limit=100 \
  --bucket=file://./data

# Validate
go test ./games/yugioh/...
```

## Key Differences from MTG

### Partition Names

**MTG**: Main Deck, Sideboard, Command Zone
**Yu-Gi-Oh!**: Main Deck, Extra Deck, Side Deck
**Pokemon**: Deck, Prizes

### Collection Types

**MTG**: Set (with set code), Deck (with format), Cube
**Yu-Gi-Oh!**: Deck (TCG/OCG format), Collection (user lists)
**Pokemon**: Deck, Set, Binder

### Card Fields

Each game has unique fields:
- **MTG**: Mana cost, power/toughness, type line
- **Yu-Gi-Oh!**: ATK/DEF, level/rank, attribute
- **Pokemon**: HP, type, weakness/resistance, retreat cost

## Validation Checklist

- [ ] Package compiles: `go build ./games/{game}/...`
- [ ] Tests pass: `go test ./games/{game}/...`
- [ ] Collection types registered in `init()`
- [ ] Partitions have appropriate names for the game
- [ ] Cards stored in `games/{game}/{dataset}/cards/` or `/collections/`
- [ ] Dataset implements `games.Dataset` interface
- [ ] CLI can extract data: `go run ./cmd/dataset extract {dataset}`

## Common Pitfalls

1. **Forgetting to register collection types** → Runtime panic on unmarshal
2. **Wrong partition names** → Confusing user experience
3. **Not implementing `IsCollectionType()`** → Compile error
4. **Hardcoding MTG assumptions** → Check for "mana", "power", etc. in shared code

## Benefits of This Architecture

✅ **Shared infrastructure** - Scraper, storage, CLI work for all games
✅ **Type safety** - Compile-time checks for interfaces
✅ **Easy extension** - Add game in ~2-3 days
✅ **Isolated changes** - Game-specific code doesn't affect others
✅ **Testable** - Each game has independent tests

## Next Steps

After implementing the game:
1. Extract 100+ collections for quality validation
2. Build card co-occurrence transform for the game
3. Add game to similarity search index
4. Document game-specific quirks and edge cases
