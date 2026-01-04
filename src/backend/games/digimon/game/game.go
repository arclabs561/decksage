package game

import (
	"collections/games"
)

// Register Digimon collection types with the global registry
func init() {
	games.RegisterCollectionType("DigimonDeck", func() games.CollectionType {
		return new(CollectionTypeDeck)
	})
	games.RegisterCollectionType("DigimonSet", func() games.CollectionType {
		return new(CollectionTypeSet)
	})
}

// Type aliases for shared types (universal across all card games)
type (
	CardDesc              = games.CardDesc
	Collection            = games.Collection
	Partition             = games.Partition
	CollectionType        = games.CollectionType
	CollectionTypeWrapper = games.CollectionTypeWrapper
)

// Digimon specific Card structure
type Card struct {
	Name        string      `json:"name"`
	Type        string      `json:"type"`        // Digimon, Tamer, Option
	Color       string      `json:"color"`       // Red, Blue, Yellow, Green, Black, Purple, White
	Level       string      `json:"level"`       // Lv.2, Lv.3, Lv.4, Lv.5, Lv.6, Lv.7
	Attribute   string      `json:"attribute,omitempty"`   // Data, Virus, Vaccine, Free
	TypeCategory string     `json:"type_category,omitempty"` // Dragon, Beast, etc.
	DP          int         `json:"dp,omitempty"`         // Digimon Power
	PlayCost    int         `json:"play_cost,omitempty"`  // Memory cost
	EvolutionCost int       `json:"evolution_cost,omitempty"`
	Description string      `json:"description"`
	Effects     []Effect    `json:"effects,omitempty"`
	Inherited   []Effect    `json:"inherited,omitempty"`  // Inherited effects
	Images      []CardImage `json:"images,omitempty"`
	References  []CardRef   `json:"references,omitempty"`
	
	// Enrichment data
	Prices     CardPrices `json:"prices,omitempty"`     // Market pricing
	Set        string     `json:"set,omitempty"`        // Set code
	SetName    string     `json:"set_name,omitempty"`   // Set name
	Rarity     string     `json:"rarity,omitempty"`     // Common, Uncommon, Rare, Super Rare, etc.
	CardNumber string     `json:"card_number,omitempty"` // Card number in set
}

type Effect struct {
	Type string `json:"type"` // Main Effect, When Digivolving, When Attacking, etc.
	Text string `json:"text"`
}

type CardPrices struct {
	TCGPlayer   *float64 `json:"tcgplayer,omitempty"`
	TCGPlayerLow *float64 `json:"tcgplayer_low,omitempty"`
	TCGPlayerMid *float64 `json:"tcgplayer_mid,omitempty"`
	TCGPlayerHigh *float64 `json:"tcgplayer_high,omitempty"`
	Cardmarket  *float64 `json:"cardmarket,omitempty"`
	Ebay        *float64 `json:"ebay,omitempty"`
}

type CardImage struct {
	URL   string `json:"url"`
	Small string `json:"small,omitempty"`
	Large string `json:"large,omitempty"`
}

type CardRef struct {
	URL string `json:"url"`
}

// Digimon specific collection types

type CollectionTypeDeck struct {
	Name      string `json:"name"`
	Format    string `json:"format"` // Standard, Unlimited
	Archetype string `json:"archetype,omitempty"`
	Player    string `json:"player,omitempty"`
	// Tournament metadata (from Limitless TCG API)
	Event     string `json:"event,omitempty"`
	Placement int    `json:"placement,omitempty"`
	EventDate string `json:"eventDate,omitempty"`
}

type CollectionTypeSet struct {
	Name         string `json:"name"`
	Code         string `json:"code"`   // Set code (e.g., "BT01", "EX01")
	Series       string `json:"series"` // Series name
	ReleaseDate  string `json:"releaseDate,omitempty"`
	PrintedTotal int    `json:"printedTotal,omitempty"`
	Total        int    `json:"total,omitempty"`
}

func (ct *CollectionTypeDeck) Type() string   { return "DigimonDeck" }
func (ct *CollectionTypeSet) Type() string    { return "DigimonSet" }

func (ct *CollectionTypeDeck) IsCollectionType()   {}
func (ct *CollectionTypeSet) IsCollectionType()    {}

// Standard partition names for Digimon
const (
	PartitionDeck = "Deck"
)

