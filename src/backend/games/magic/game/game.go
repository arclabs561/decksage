package game

import (
	"collections/games"

	"github.com/samber/mo"
)

// Register MTG collection types with the global registry
func init() {
	games.RegisterCollectionType("Set", func() games.CollectionType { return new(CollectionTypeSet) })
	games.RegisterCollectionType("Deck", func() games.CollectionType { return new(CollectionTypeDeck) })
	games.RegisterCollectionType("Cube", func() games.CollectionType { return new(CollectionTypeCube) })
}

type Card struct {
	Name       string          `json:"name"`
	Faces      []CardFace      `json:"faces"`
	Images     []CardImage     `json:"image"`
	References []CardReference `json:"references"`
	Features   CardFeatures    `json:"features"`

	// Enrichment data from Scryfall
	Keywords      []string          `json:"keywords,omitempty"`       // Mechanical keywords (Flash, Flying, etc.)
	Colors        []string          `json:"colors,omitempty"`         // Actual color identity
	ColorIdentity []string          `json:"color_identity,omitempty"` // Commander color identity
	CMC           float64           `json:"cmc,omitempty"`            // Converted mana cost
	Prices        CardPrices        `json:"prices,omitempty"`         // Market pricing
	Legalities    map[string]string `json:"legalities,omitempty"`     // Format legality
	Rarity        string            `json:"rarity,omitempty"`         // Common, Uncommon, Rare, Mythic
	Set           string            `json:"set,omitempty"`            // Set code
	SetName       string            `json:"set_name,omitempty"`       // Set name
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

type CardPrices struct {
	USD     *float64 `json:"usd,omitempty"`      // USD paper price
	USDFoil *float64 `json:"usd_foil,omitempty"` // USD foil price
	EUR     *float64 `json:"eur,omitempty"`      // EUR price
	EURFoil *float64 `json:"eur_foil,omitempty"` // EUR foil price
	TIX     *float64 `json:"tix,omitempty"`      // MTGO tickets
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

// Type aliases for shared types - use games.Collection, games.Partition, games.CardDesc
type (
	CardDesc              = games.CardDesc
	Collection            = games.Collection
	Partition             = games.Partition
	CollectionType        = games.CollectionType
	CollectionTypeWrapper = games.CollectionTypeWrapper
)

// MTG-specific collection types

type CollectionTypeSet struct {
	Name string `json:"name"`
	Code string `json:"code"`
}

type CollectionTypeDeck struct {
	Name      string `json:"name"`
	Format    string `json:"format"`
	Archetype string `json:"archetype,omitempty"`

	// Tournament/player metadata (extracted from deck pages)
	Player    string `json:"player,omitempty"`
	Event     string `json:"event,omitempty"`
	Placement int    `json:"placement,omitempty"`  // 0 = unknown, 1 = 1st place, etc.
	EventDate string `json:"event_date,omitempty"` // As string since formats vary
}

type CollectionTypeCube struct {
	Name string `json:"name"`
}

func (ct *CollectionTypeSet) Type() string  { return "Set" }
func (ct *CollectionTypeDeck) Type() string { return "Deck" }
func (ct *CollectionTypeCube) Type() string { return "Cube" }

func (ct *CollectionTypeSet) IsCollectionType()  {}
func (ct *CollectionTypeDeck) IsCollectionType() {}
func (ct *CollectionTypeCube) IsCollectionType() {}

// TODO
type DeckFormat int
