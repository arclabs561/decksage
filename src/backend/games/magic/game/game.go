package game

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/samber/mo"
)

type Card struct {
	Name       string          `json:"name"`
	Faces      []CardFace      `json:"faces"`
	Images     []CardImage     `json:"image"`
	References []CardReference `json:"references"`
	Features   CardFeatures    `json:"features"`
}

type CardImage struct {
	URL string `json:"url"`
}

type CardReference struct {
	URL string `json:"url"`
}

type CardFeatures struct {
	Popularity float64 `json:"popularity"`
	Centrality float64 `json:"centrality"`
}

type CardFace struct {
	Name string `json:"name"`
	// ManaCost ManaCost `json:"mana_cost"`
	ManaCost string `json:"mana_cost"`
	// TypeLine TypeLine `json:"type_line"`
	TypeLine   string `json:"type_line"`
	OracleText string `json:"oracle_text"`
	FlavorText string `json:"flavor_text,omitempty"`
	Power      string `json:"power,omitempty"`
	Toughness  string `json:"toughness,omitempty"`
}

type ManaCost struct {
	Parts []ManaCostPart `json:"parts"`
}

type ManaCostPart interface {
	manaCostPart()
}

type ManaCostPartScalar struct {
	Unit   ManaUnit       `json:"unit"`
	Scalar ManaCostScalar `json:"scalar"`
}

type ManaCostScalar struct{}

func (p ManaCostPartScalar) manaCostPart() {}

type ManaUnit int

const (
	ManaGeneric ManaUnit = iota
	ManaPlains
	ManaIsland
	ManaSwamp
	ManaMountain
	ManaForest
	ManaColorless
	ManaSnow
)

type TypeLine struct {
	Supertype mo.Option[Supertype]
	Type      Type
	Subtype   mo.Option[Subtype]
}

type Supertype int

type Type int

const (
	Planeswalker Type = iota
	Creature
	Instant
	Sorcery
	Enchantment
	Artifact
	Land
	Tribal
	Conspiracy
	Plane
	Phenomenon
	Scheme
	Vanguard
	Dungeon
)

type Subtype int

type CardDesc struct {
	Name  string `json:"name"`
	Count int    `json:"count"`
}

type Collection struct {
	ID          string                `json:"id"`
	URL         string                `json:"url"`
	Type        CollectionTypeWrapper `json:"type"`
	ReleaseDate time.Time             `json:"release_date"`
	Partitions  []Partition           `json:"partitions"`
}

var reBadCardName = regexp.MustCompile(`(^\s*$)|(\p{Cc})`)

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
	sort.SliceStable(c.Partitions, func(i, j int) bool {
		return c.Partitions[i].Name < c.Partitions[j].Name
	})
	for i, p := range c.Partitions {
		if p.Name == "" {
			return fmt.Errorf("partition %d has empty name", i)
		}
		if len(p.Cards) == 0 {
			return fmt.Errorf("partition %s has no cards", p.Name)
		}
		// Track card names to detect duplicates
		cardNames := make(map[string]bool)
		for _, card := range p.Cards {
			if card.Count < 1 {
				return fmt.Errorf(
					"card %q has count 0 in partition %q",
					card.Name,
					p.Name,
				)
			}
			if card.Count > 100 {
				return fmt.Errorf(
					"card %q has invalid count %d in partition %q (max 100)",
					card.Name,
					card.Count,
					p.Name,
				)
			}
			if reBadCardName.MatchString(card.Name) {
				return fmt.Errorf("bad card name %q in partition %q", card.Name, p.Name)
			}
			// Check for duplicates (case-insensitive)
			normalized := strings.ToLower(strings.TrimSpace(card.Name))
			if cardNames[normalized] {
				return fmt.Errorf("duplicate card %q in partition %q", card.Name, p.Name)
			}
			cardNames[normalized] = true
		}
		sort.SliceStable(p.Cards, func(i, j int) bool {
			return p.Cards[i].Name < p.Cards[j].Name
		})
	}
	return nil
}

type Partition struct {
	Name  string     `json:"name"`
	Cards []CardDesc `json:"cards"`
}

type CollectionTypeWrapper struct {
	Type  string         `json:"type"`
	Inner CollectionType `json:"inner"`
}

type collectionTypeWrapper struct {
	Type  string          `json:"type"`
	Inner json.RawMessage `json:"inner"`
}

func (w *CollectionTypeWrapper) UnmarshalJSON(b []byte) error {
	var ww collectionTypeWrapper
	if err := json.Unmarshal(b, &ww); err != nil {
		return err
	}
	var inner CollectionType
	switch strings.ToLower(ww.Type) {
	case "set":
		inner = new(CollectionTypeSet)
	case "deck":
		inner = new(CollectionTypeDeck)
	case "cube":
		inner = new(CollectionTypeCube)
	default:
		return fmt.Errorf("unknown type %q", ww.Type)
	}
	if err := json.Unmarshal(ww.Inner, inner); err != nil {
		return err
	}
	*w = CollectionTypeWrapper{
		Type:  inner.Type(),
		Inner: inner,
	}
	return nil
}

type CollectionType interface {
	Type() string
	collectionType()
}

type CollectionTypeSet struct {
	Name string `json:"name"`
	Code string `json:"code"`
}

type CollectionTypeDeck struct {
	Name      string `json:"name"`
	Format    string `json:"format"`
	Archetype string `json:"archetype,omitempty"`
	// Tournament metadata
	Player    string `json:"player,omitempty"`    // Player name
	Event     string `json:"event,omitempty"`     // Tournament/event name
	Placement string `json:"placement,omitempty"` // "1st", "Top 8", etc.
	EventDate string `json:"eventDate,omitempty"` // Tournament date
	Wins      int    `json:"wins,omitempty"`      // Win count
	Losses    int    `json:"losses,omitempty"`    // Loss count
	Ties      int    `json:"ties,omitempty"`      // Tie count
	Record    string `json:"record,omitempty"`    // Record string like "5-2-1"
}

type CollectionTypeCube struct {
	Name string `json:"name"`
}

func (ct CollectionTypeSet) Type() string  { return "Set" }
func (ct CollectionTypeDeck) Type() string { return "Deck" }
func (ct CollectionTypeCube) Type() string { return "Cube" }

func (ct *CollectionTypeSet) collectionType()  {}
func (ct *CollectionTypeDeck) collectionType() {}
func (ct *CollectionTypeCube) collectionType() {}

// TODO
type DeckFormat int

const ()
