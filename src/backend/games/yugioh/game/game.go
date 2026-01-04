package game

import (
	"collections/games"
)

// Register Yu-Gi-Oh! collection types with the global registry
func init() {
	games.RegisterCollectionType("YGODeck", func() games.CollectionType {
		return new(CollectionTypeDeck)
	})
	games.RegisterCollectionType("YGOCollection", func() games.CollectionType {
		return new(CollectionTypeCollection)
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

// Yu-Gi-Oh! specific Card structure
type Card struct {
	Name        string       `json:"name"`
	Type        CardType     `json:"type"` // Monster, Spell, Trap
	MonsterType *MonsterType `json:"monster_type,omitempty"`
	Attribute   string       `json:"attribute,omitempty"` // DARK, LIGHT, EARTH, etc.
	Level       int          `json:"level,omitempty"`
	Rank        int          `json:"rank,omitempty"`        // Xyz
	LinkRating  int          `json:"link_rating,omitempty"` // Link
	ATK         int          `json:"atk,omitempty"`
	DEF         int          `json:"def,omitempty"`
	Scale       int          `json:"scale,omitempty"` // Pendulum
	Description string       `json:"description"`
	Archetype   string       `json:"archetype,omitempty"`
	Race        string       `json:"race,omitempty"` // Dragon, Warrior, Spellcaster, etc.
	Images      []CardImage  `json:"images,omitempty"`
	References  []CardRef    `json:"references,omitempty"`
	
	// Enrichment data
	Prices     CardPrices   `json:"prices,omitempty"`     // Market pricing
	BanStatus  string       `json:"ban_status,omitempty"` // Forbidden, Limited, Semi-Limited, Unlimited
	Set        string       `json:"set,omitempty"`        // Set code
	SetName    string       `json:"set_name,omitempty"`   // Set name
	Rarity     string       `json:"rarity,omitempty"`     // Common, Rare, Ultra Rare, etc.
}

type CardPrices struct {
	TCGPlayer  *float64 `json:"tcgplayer,omitempty"`   // TCGPlayer market price
	Cardmarket *float64 `json:"cardmarket,omitempty"`   // Cardmarket price (EUR)
	Amazon     *float64 `json:"amazon,omitempty"`       // Amazon price
	Ebay       *float64 `json:"ebay,omitempty"`         // eBay average
	CoolStuff  *float64 `json:"coolstuff,omitempty"`    // CoolStuffInc price
}

type CardType string

const (
	TypeMonster CardType = "Monster"
	TypeSpell   CardType = "Spell"
	TypeTrap    CardType = "Trap"
)

type MonsterType struct {
	MainType   string   `json:"main_type"` // Normal, Effect, Fusion, Synchro, Xyz, Link, Ritual, Pendulum
	SubTypes   []string `json:"sub_types"` // Tuner, Gemini, Spirit, etc.
	IsEffect   bool     `json:"is_effect"`
	IsFusion   bool     `json:"is_fusion"`
	IsSynchro  bool     `json:"is_synchro"`
	IsXyz      bool     `json:"is_xyz"`
	IsLink     bool     `json:"is_link"`
	IsRitual   bool     `json:"is_ritual"`
	IsPendulum bool     `json:"is_pendulum"`
}

type CardImage struct {
	URL string `json:"url"`
}

type CardRef struct {
	URL string `json:"url"`
}

// Yu-Gi-Oh! specific collection types

type CollectionTypeDeck struct {
	Name      string `json:"name"`
	Format    string `json:"format"` // TCG, OCG, Speed Duel, Master Duel
	Archetype string `json:"archetype,omitempty"`
	Player    string `json:"player,omitempty"`
	// Tournament metadata (from YGOPRODeck tournament section)
	Event     string `json:"event,omitempty"`     // Tournament name
	Placement string `json:"placement,omitempty"` // "Top 16", "Winner", etc.
	EventDate string `json:"eventDate,omitempty"` // Tournament date
	
	// Enhanced tournament metadata
	TournamentType   string  `json:"tournamentType,omitempty"`   // "Regional", "YCS", "WCQ", "Local"
	TournamentSize   int     `json:"tournamentSize,omitempty"`   // Number of players
	Location         string  `json:"location,omitempty"`         // City, State/Country
	Region           string  `json:"region,omitempty"`           // "North America", "Europe", "Asia-Pacific"
	TournamentID     string  `json:"tournamentId,omitempty"`     // Unique tournament identifier
	RoundCount       int     `json:"roundCount,omitempty"`       // Swiss rounds
	TopCutSize       int     `json:"topCutSize,omitempty"`       // Top 8, Top 16, etc.
	
	// Temporal context (computed)
	DaysSinceRotation  int     `json:"daysSinceRotation,omitempty"`  // Days since last format rotation (N/A for YGO)
	DaysSinceBanUpdate int     `json:"daysSinceBanUpdate,omitempty"` // Days since last ban list
	MetaShare           float64 `json:"metaShare,omitempty"`          // Deck's meta share at event time (%)
	
	// Round-by-round results
	RoundResults []RoundResult `json:"roundResults,omitempty"`
}

// RoundResult represents a single round/match result
type RoundResult struct {
	RoundNumber  int    `json:"roundNumber"`
	Opponent     string `json:"opponent,omitempty"`      // Opponent player name
	OpponentDeck string `json:"opponentDeck,omitempty"` // Opponent archetype
	Result       string `json:"result"`                  // "W", "L", "T", "BYE"
	GameWins     int    `json:"gameWins,omitempty"`      // 2-0, 2-1, etc.
	GameLosses   int    `json:"gameLosses,omitempty"`
}

type CollectionTypeCollection struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
}

func (ct *CollectionTypeDeck) Type() string       { return "YGODeck" }
func (ct *CollectionTypeCollection) Type() string { return "YGOCollection" }

func (ct *CollectionTypeDeck) IsCollectionType()       {}
func (ct *CollectionTypeCollection) IsCollectionType() {}

// Standard partition names for Yu-Gi-Oh!
const (
	PartitionMain  = "Main Deck"
	PartitionExtra = "Extra Deck"
	PartitionSide  = "Side Deck"
)
