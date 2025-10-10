// Package games defines the common abstractions for multi-game support.
//
// Architecture:
//   - Collection/Partition/CardDesc are universal across all card games
//   - Each game implements game-specific Card types and CollectionType metadata
//   - Dataset interface is game-agnostic but operates on game-specific models
//
// Adding a new game:
//  1. Create games/{game}/game/ with Card struct and CollectionType variants
//  2. Create games/{game}/dataset/ with Dataset implementations
//  3. Use the shared Collection, Partition, CardDesc types
package games

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"sort"
	"time"
)

// CardDesc represents a card reference with count.
// Universal across all card games.
type CardDesc struct {
	Name  string `json:"name"`
	Count int    `json:"count"`
}

// Partition represents a named group of cards.
// Examples: "Main Deck", "Sideboard", "Extra Deck", "Command Zone"
type Partition struct {
	Name  string     `json:"name"`
	Cards []CardDesc `json:"cards"`
}

// Collection represents a collection of cards (deck, set, cube, etc).
// Universal structure, game-specific metadata in Type field.
type Collection struct {
	ID          string                `json:"id"`
	URL         string                `json:"url"`
	Type        CollectionTypeWrapper `json:"type"`
	ReleaseDate time.Time             `json:"release_date"`
	Partitions  []Partition           `json:"partitions"`

	// Source tracking: which scraper/dataset extracted this
	// Examples: "mtgtop8", "goldfish", "deckbox", "scryfall", "limitless", "ygoprodeck"
	Source string `json:"source,omitempty"`
}

// CollectionTypeWrapper wraps game-specific collection types.
type CollectionTypeWrapper struct {
	Type  string         `json:"type"`
	Inner CollectionType `json:"inner"`
}

// CollectionType is implemented by game-specific collection metadata.
// Examples: MTG has Set/Deck/Cube, Yu-Gi-Oh! might have Deck/Collection
type CollectionType interface {
	Type() string
	// IsCollectionType is a marker method to prevent external types
	// from implementing this interface accidentally
	IsCollectionType()
}

type collectionTypeWrapper struct {
	Type  string          `json:"type"`
	Inner json.RawMessage `json:"inner"`
}

// TypeRegistry maps collection type names to constructors.
// Each game should register its types on init.
var TypeRegistry = make(map[string]func() CollectionType)

// RegisterCollectionType registers a type constructor.
// Call from game package init() functions.
// Panics if typeName is already registered (prevents silent overwrites).
func RegisterCollectionType(typeName string, constructor func() CollectionType) {
	if _, exists := TypeRegistry[typeName]; exists {
		panic(fmt.Sprintf("collection type %q already registered", typeName))
	}
	TypeRegistry[typeName] = constructor
}

func (w *CollectionTypeWrapper) UnmarshalJSON(b []byte) error {
	var ww collectionTypeWrapper
	if err := json.Unmarshal(b, &ww); err != nil {
		return err
	}

	constructor, ok := TypeRegistry[ww.Type]
	if !ok {
		return fmt.Errorf("unknown collection type %q (not registered)", ww.Type)
	}

	inner := constructor()
	if err := json.Unmarshal(ww.Inner, inner); err != nil {
		return err
	}

	*w = CollectionTypeWrapper{
		Type:  inner.Type(),
		Inner: inner,
	}
	return nil
}

var reBadCardName = regexp.MustCompile(`(^\s*$)|(\p{Cc})`)

// Canonicalize validates and normalizes a collection.
// Universal validation logic across all games.
//
// MUTATES: Sorts partitions and cards by name in place.
func (c *Collection) Canonicalize() error {
	if c.ID == "" {
		return errors.New("empty id")
	}
	if c.URL == "" {
		return errors.New("url is empty")
	}
	if _, err := url.Parse(c.URL); err != nil {
		return fmt.Errorf("failed to parse url: %w", err)
	}
	if c.Type.Type != c.Type.Inner.Type() {
		return fmt.Errorf(
			"mismatched types: %s != %s",
			c.Type.Type,
			c.Type.Inner.Type(),
		)
	}
	if c.ReleaseDate.IsZero() {
		return errors.New("release date is zero time")
	}
	if len(c.Partitions) == 0 {
		return errors.New("collection has no partitions")
	}

	// Sort partitions by name
	sort.SliceStable(c.Partitions, func(i, j int) bool {
		return c.Partitions[i].Name < c.Partitions[j].Name
	})

	// Validate each partition
	for i, p := range c.Partitions {
		if p.Name == "" {
			return fmt.Errorf("partition %d has empty name", i)
		}
		if len(p.Cards) == 0 {
			return fmt.Errorf("partition %s has no cards", p.Name)
		}
		for _, card := range p.Cards {
			if card.Count < 1 || card.Count > 100 {
				return fmt.Errorf(
					"card %q has invalid count %d in partition %q (must be 1-100)",
					card.Name,
					card.Count,
					p.Name,
				)
			}
			if reBadCardName.MatchString(card.Name) {
				return fmt.Errorf("bad card name %q in partition %q", card.Name, p.Name)
			}
		}
		// Sort cards by name
		sort.SliceStable(p.Cards, func(i, j int) bool {
			return p.Cards[i].Name < p.Cards[j].Name
		})
	}
	return nil
}
