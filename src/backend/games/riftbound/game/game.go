package game

import (
	"collections/games"
)

// Register Riftbound collection types with the global registry
func init() {
	games.RegisterCollectionType("RiftboundDeck", func() games.CollectionType {
		return new(CollectionTypeDeck)
	})
	games.RegisterCollectionType("RiftboundSet", func() games.CollectionType {
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

// Riftbound specific Card structure
type Card struct {
	Name        string      `json:"name"`
	Type        string      `json:"type"`        // Champion, Spell, Battlefield, Rune
	Champion    string      `json:"champion,omitempty"` // Champion name (for Champion cards)
	Domain      []string    `json:"domain,omitempty"`   // Body, Calm, Chaos, Fury, Mind, Order
	Cost        int         `json:"cost,omitempty"`     // Mana cost
	Power       int         `json:"power,omitempty"`    // Attack power
	Health      int         `json:"health,omitempty"`   // Health/Defense
	Effect      string      `json:"effect,omitempty"`
	Keywords    []string    `json:"keywords,omitempty"` // Keywords like Quick Attack, Overwhelm, etc.
	Images      []CardImage `json:"images,omitempty"`
	References  []CardRef   `json:"references,omitempty"`
	
	// Enrichment data
	Prices     CardPrices `json:"prices,omitempty"`     // Market pricing
	Set        string     `json:"set,omitempty"`        // Set code (e.g., "ORI", "SFG")
	SetName    string     `json:"set_name,omitempty"`   // Set name
	Rarity     string     `json:"rarity,omitempty"`     // Common, Rare, Epic, Legendary
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

// Riftbound specific collection types

type CollectionTypeDeck struct {
	Name      string `json:"name"`
	Format    string `json:"format"` // Origins, Spiritforged, Constructed
	Archetype string `json:"archetype,omitempty"`
	Player    string `json:"player,omitempty"`
	Champion  string `json:"champion,omitempty"` // Champion name
	// Tournament metadata
	Event     string `json:"event,omitempty"`
	Placement int    `json:"placement,omitempty"`
	EventDate string `json:"eventDate,omitempty"`
}

type CollectionTypeSet struct {
	Name         string `json:"name"`
	Code         string `json:"code"`   // Set code (e.g., "ORI", "SFG")
	Series       string `json:"series"` // Series name
	ReleaseDate  string `json:"releaseDate,omitempty"`
	PrintedTotal int    `json:"printedTotal,omitempty"`
	Total        int    `json:"total,omitempty"`
}

func (ct *CollectionTypeDeck) Type() string   { return "RiftboundDeck" }
func (ct *CollectionTypeSet) Type() string    { return "RiftboundSet" }

func (ct *CollectionTypeDeck) IsCollectionType()   {}
func (ct *CollectionTypeSet) IsCollectionType()    {}

// Standard partition names for Riftbound
const (
	PartitionDeck = "Deck"
)

