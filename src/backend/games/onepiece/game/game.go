package game

import (
	"collections/games"
)

// Register One Piece collection types with the global registry
func init() {
	games.RegisterCollectionType("OnePieceDeck", func() games.CollectionType {
		return new(CollectionTypeDeck)
	})
	games.RegisterCollectionType("OnePieceSet", func() games.CollectionType {
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

// One Piece specific Card structure
type Card struct {
	Name        string      `json:"name"`
	Type        string      `json:"type"`        // Leader, Character, Event, Stage
	Color       []string    `json:"color"`       // Red, Green, Blue, Purple, Black, Yellow
	Cost        int         `json:"cost,omitempty"`        // Don cost
	Power       int         `json:"power,omitempty"`       // Character power
	Counter     int         `json:"counter,omitempty"`     // Counter value
	Attribute   string      `json:"attribute,omitempty"`   // Slash, Strike, Ranged, Special
	Effect      string      `json:"effect,omitempty"`
	Trigger     string      `json:"trigger,omitempty"`      // Trigger effect
	Images      []CardImage `json:"images,omitempty"`
	References  []CardRef   `json:"references,omitempty"`
	
	// Enrichment data
	Prices     CardPrices `json:"prices,omitempty"`     // Market pricing
	Set        string     `json:"set,omitempty"`        // Set code (e.g., "OP01", "OP02")
	SetName    string     `json:"set_name,omitempty"`   // Set name
	Rarity     string     `json:"rarity,omitempty"`     // Common, Uncommon, Rare, Super Rare, etc.
	CardNumber string     `json:"card_number,omitempty"` // Card number in set
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

// One Piece specific collection types

type CollectionTypeDeck struct {
	Name      string `json:"name"`
	Format    string `json:"format"` // Standard, Unlimited
	Archetype string `json:"archetype,omitempty"`
	Player    string `json:"player,omitempty"`
	Leader    string `json:"leader,omitempty"` // Leader card name
	// Tournament metadata (from Limitless TCG API)
	Event     string `json:"event,omitempty"`
	Placement int    `json:"placement,omitempty"`
	EventDate string `json:"eventDate,omitempty"`
}

type CollectionTypeSet struct {
	Name         string `json:"name"`
	Code         string `json:"code"`   // Set code (e.g., "OP01", "OP02")
	Series       string `json:"series"` // Series name
	ReleaseDate  string `json:"releaseDate,omitempty"`
	PrintedTotal int    `json:"printedTotal,omitempty"`
	Total        int    `json:"total,omitempty"`
}

func (ct *CollectionTypeDeck) Type() string   { return "OnePieceDeck" }
func (ct *CollectionTypeSet) Type() string    { return "OnePieceSet" }

func (ct *CollectionTypeDeck) IsCollectionType()   {}
func (ct *CollectionTypeSet) IsCollectionType()    {}

// Standard partition names for One Piece
const (
	PartitionDeck = "Deck"
)

