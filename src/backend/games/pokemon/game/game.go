package game

import (
	"collections/games"
)

// Register Pokemon collection types with the global registry
func init() {
	games.RegisterCollectionType("PokemonDeck", func() games.CollectionType {
		return new(CollectionTypeDeck)
	})
	games.RegisterCollectionType("PokemonSet", func() games.CollectionType {
		return new(CollectionTypeSet)
	})
	games.RegisterCollectionType("PokemonBinder", func() games.CollectionType {
		return new(CollectionTypeBinder)
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

// Pokemon specific Card structure
type Card struct {
	Name        string       `json:"name"`
	SuperType   string       `json:"supertype"` // Pokémon, Trainer, Energy
	SubTypes    []string     `json:"subtypes"`  // Basic, Stage 1, Stage 2, Item, Supporter, Stadium
	HP          string       `json:"hp,omitempty"`
	Types       []string     `json:"types,omitempty"` // Fire, Water, Grass, etc.
	EvolvesFrom string       `json:"evolvesFrom,omitempty"`
	EvolvesTo   []string     `json:"evolvesTo,omitempty"`
	Attacks     []Attack     `json:"attacks,omitempty"`
	Abilities   []Ability    `json:"abilities,omitempty"`
	Weaknesses  []Resistance `json:"weaknesses,omitempty"`
	Resistances []Resistance `json:"resistances,omitempty"`
	RetreatCost []string     `json:"retreatCost,omitempty"` // Energy symbols
	Rules       []string     `json:"rules,omitempty"`       // For special cards (GX, V, VMAX, etc.)
	Rarity      string       `json:"rarity,omitempty"`
	Artist      string       `json:"artist,omitempty"`
	NationalDex int          `json:"nationalPokedexNumber,omitempty"`
	Images      []CardImage  `json:"images,omitempty"`
	References  []CardRef    `json:"references,omitempty"`
	
	// Enrichment data
	Prices      CardPrices `json:"prices,omitempty"`      // Market pricing
	Set         string     `json:"set,omitempty"`         // Set code
	SetName     string     `json:"set_name,omitempty"`    // Set name
	Regulation  string     `json:"regulation,omitempty"`  // Regulation mark (D, E, F, etc.)
	Legalities  map[string]string `json:"legalities,omitempty"` // Standard, Expanded legality
}

type CardPrices struct {
	TCGPlayer   *float64 `json:"tcgplayer,omitempty"`    // TCGPlayer market price
	TCGPlayerLow *float64 `json:"tcgplayer_low,omitempty"` // Low price
	TCGPlayerMid *float64 `json:"tcgplayer_mid,omitempty"` // Mid price
	TCGPlayerHigh *float64 `json:"tcgplayer_high,omitempty"` // High price
	Cardmarket  *float64 `json:"cardmarket,omitempty"`   // Cardmarket price (EUR)
	Ebay        *float64 `json:"ebay,omitempty"`         // eBay average
}

type Attack struct {
	Name                string   `json:"name"`
	Cost                []string `json:"cost"` // Energy symbols
	ConvertedEnergyCost int      `json:"convertedEnergyCost"`
	Damage              string   `json:"damage"`
	Text                string   `json:"text"`
}

type Ability struct {
	Name string `json:"name"`
	Text string `json:"text"`
	Type string `json:"type"` // Ability, Poké-Power, Poké-Body
}

type Resistance struct {
	Type  string `json:"type"`  // Fire, Water, etc.
	Value string `json:"value"` // -20, -30, ×2, etc.
}

type CardImage struct {
	URL   string `json:"url"`
	Small string `json:"small,omitempty"`
	Large string `json:"large,omitempty"`
}

type CardRef struct {
	URL string `json:"url"`
}

// Pokemon specific collection types

type CollectionTypeDeck struct {
	Name      string `json:"name"`
	Format    string `json:"format"` // Standard, Expanded, Unlimited
	Archetype string `json:"archetype,omitempty"`
	Player    string `json:"player,omitempty"`
	// Tournament metadata (from Limitless TCG API)
	Event     string `json:"event,omitempty"`     // Tournament name
	Placement int    `json:"placement,omitempty"` // Finishing position (1 = 1st place)
	EventDate string `json:"eventDate,omitempty"` // Tournament date
	
	// Enhanced tournament metadata
	TournamentType   string  `json:"tournamentType,omitempty"`   // "Regional", "Championship", "League Cup", "League Challenge"
	TournamentSize   int     `json:"tournamentSize,omitempty"`   // Number of players (from Limitless API)
	Location         string  `json:"location,omitempty"`         // City, State/Country
	Region           string  `json:"region,omitempty"`           // "North America", "Europe", "Asia-Pacific"
	TournamentID     string  `json:"tournamentId,omitempty"`     // Unique tournament identifier
	Country          string  `json:"country,omitempty"`          // Player country (from Limitless API)
	
	// Temporal context (computed)
	DaysSinceRotation  int     `json:"daysSinceRotation,omitempty"`  // Days since last format rotation
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

type CollectionTypeSet struct {
	Name         string `json:"name"`
	Code         string `json:"code"`   // Set code (e.g., "base1", "swsh1")
	Series       string `json:"series"` // Base Set, Sword & Shield, etc.
	ReleaseDate  string `json:"releaseDate,omitempty"`
	PrintedTotal int    `json:"printedTotal,omitempty"`
	Total        int    `json:"total,omitempty"`
}

type CollectionTypeBinder struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
}

func (ct *CollectionTypeDeck) Type() string   { return "PokemonDeck" }
func (ct *CollectionTypeSet) Type() string    { return "PokemonSet" }
func (ct *CollectionTypeBinder) Type() string { return "PokemonBinder" }

func (ct *CollectionTypeDeck) IsCollectionType()   {}
func (ct *CollectionTypeSet) IsCollectionType()    {}
func (ct *CollectionTypeBinder) IsCollectionType() {}

// Standard partition names for Pokemon
const (
	PartitionDeck   = "Deck"
	PartitionPrizes = "Prizes"
)
