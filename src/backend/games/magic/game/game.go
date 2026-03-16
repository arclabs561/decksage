package game

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"sort"
	"strconv"
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
	ManaCost string   `json:"mana_cost"`
	CMC      int      `json:"cmc"`
	Colors   []string `json:"colors,omitempty"`
	// TypeLine TypeLine `json:"type_line"`
	TypeLine   string   `json:"type_line"`
	Supertypes []string `json:"supertypes,omitempty"`
	Types      []string `json:"types,omitempty"`
	Subtypes   []string `json:"subtypes,omitempty"`
	OracleText string   `json:"oracle_text"`
	FlavorText string   `json:"flavor_text,omitempty"`
	Power      string   `json:"power,omitempty"`
	Toughness  string   `json:"toughness,omitempty"`
}

// knownSupertypes lists recognized MTG supertypes.
var knownSupertypes = map[string]bool{
	"Legendary": true, "Basic": true, "Snow": true,
	"World": true, "Ongoing": true,
}

// knownTypes lists recognized MTG card types.
var knownTypes = map[string]bool{
	"Creature": true, "Instant": true, "Sorcery": true,
	"Enchantment": true, "Artifact": true, "Land": true,
	"Planeswalker": true, "Battle": true, "Kindred": true,
	"Tribal": true, "Conspiracy": true, "Plane": true,
	"Phenomenon": true, "Scheme": true, "Vanguard": true,
	"Dungeon": true,
}

// ParseTypeLine splits an MTG type_line into supertypes, types, and subtypes.
// Format: "[Supertypes] [Types] \u2014 [Subtypes]"
func ParseTypeLine(typeLine string) (supertypes, types, subtypes []string) {
	if typeLine == "" {
		return nil, nil, nil
	}

	// Split on em-dash (with surrounding spaces)
	parts := strings.SplitN(typeLine, "\u2014", 2)
	leftSide := strings.TrimSpace(parts[0])

	if len(parts) == 2 {
		right := strings.TrimSpace(parts[1])
		if right != "" {
			for _, s := range strings.Fields(right) {
				subtypes = append(subtypes, s)
			}
		}
	}

	for _, word := range strings.Fields(leftSide) {
		switch {
		case knownSupertypes[word]:
			supertypes = append(supertypes, word)
		case knownTypes[word]:
			types = append(types, word)
		default:
			// Unknown token on left side -- treat as type
			types = append(types, word)
		}
	}

	return supertypes, types, subtypes
}

// colorSymbols maps Scryfall mana symbols to color names.
var colorSymbols = map[string]string{
	"W": "White",
	"U": "Blue",
	"B": "Black",
	"R": "Red",
	"G": "Green",
}

// ParseManaCost parses a Scryfall mana cost string like "{2}{U}{B}" and
// returns the converted mana cost (CMC) and the set of colors present.
// Generic {N} adds N to CMC; each colored/snow/colorless symbol adds 1;
// {X} adds 0. Hybrid symbols like {W/U} add 1 to CMC and contribute
// both colors.
func ParseManaCost(manaCost string) (cmc int, colors []string) {
	if manaCost == "" {
		return 0, nil
	}
	colorSet := make(map[string]bool)
	i := 0
	for i < len(manaCost) {
		if manaCost[i] != '{' {
			i++
			continue
		}
		end := strings.IndexByte(manaCost[i:], '}')
		if end < 0 {
			break
		}
		symbol := manaCost[i+1 : i+end]
		i += end + 1

		if symbol == "X" {
			// Variable: contributes 0
			continue
		}

		// Check for hybrid (e.g. "W/U", "2/W")
		if strings.Contains(symbol, "/") {
			parts := strings.Split(symbol, "/")
			for _, p := range parts {
				if c, ok := colorSymbols[p]; ok {
					colorSet[c] = true
				}
			}
			cmc++
			continue
		}

		// Check for generic numeric
		if n, err := strconv.Atoi(symbol); err == nil {
			cmc += n
			continue
		}

		// Colored, colorless, snow, or other named symbol: each adds 1
		if c, ok := colorSymbols[symbol]; ok {
			colorSet[c] = true
		}
		cmc++
	}

	// Build sorted color list for deterministic output
	colorOrder := []string{"White", "Blue", "Black", "Red", "Green"}
	for _, c := range colorOrder {
		if colorSet[c] {
			colors = append(colors, c)
		}
	}
	return cmc, colors
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

	// Enhanced tournament metadata
	TournamentType   string  `json:"tournamentType,omitempty"`   // "GP", "PTQ", "FNM", "Regional", "Championship"
	TournamentSize   int     `json:"tournamentSize,omitempty"`   // Number of players
	Location         string  `json:"location,omitempty"`         // City, State/Country
	Region           string  `json:"region,omitempty"`           // "North America", "Europe", "Asia-Pacific"
	TournamentID     string  `json:"tournamentId,omitempty"`     // Unique tournament identifier
	RoundCount       int     `json:"roundCount,omitempty"`       // Swiss rounds
	TopCutSize       int     `json:"topCutSize,omitempty"`       // Top 8, Top 16, etc.

	// Temporal context (computed)
	DaysSinceRotation  int     `json:"daysSinceRotation,omitempty"`  // Days since last format rotation
	DaysSinceBanUpdate  int     `json:"daysSinceBanUpdate,omitempty"` // Days since last ban list
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

type CollectionTypeCube struct {
	Name string `json:"name"`
}

func (ct CollectionTypeSet) Type() string  { return "Set" }
func (ct CollectionTypeDeck) Type() string { return "Deck" }
func (ct CollectionTypeCube) Type() string { return "Cube" }

func (ct *CollectionTypeSet) collectionType()  {}
func (ct *CollectionTypeDeck) collectionType() {}
func (ct *CollectionTypeCube) collectionType() {}
