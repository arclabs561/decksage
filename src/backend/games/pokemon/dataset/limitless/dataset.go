package limitless

import (
	"collections/blob"
	"collections/games"
	"collections/games/pokemon/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// Dataset scrapes Pokemon tournament data from Limitless TCG API
// API Docs: https://docs.limitlesstcg.com/developer/tournaments
type Dataset struct {
	log    *logger.Logger
	blob   *blob.Bucket
	apiKey string
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) *Dataset {
	apiKey := os.Getenv("LIMITLESS_API_KEY")
	if apiKey == "" {
		log.Warnf(context.Background(), "LIMITLESS_API_KEY not set - scraper will fail")
	}
	return &Dataset{
		log:    log,
		blob:   blob,
		apiKey: apiKey,
	}
}

func (d *Dataset) Description() games.Description {
	return games.Description{
		Game: "pokemon",
		Name: "limitless",
	}
}

// API Response structures based on https://docs.limitlesstcg.com/developer/tournaments

type apiTournament struct {
	ID      string    `json:"id"`
	Game    string    `json:"game"`
	Format  string    `json:"format"`
	Name    string    `json:"name"`
	Date    time.Time `json:"date"`
	Players int       `json:"players"`
}

type apiStanding struct {
	Player   string         `json:"player"`
	Name     string         `json:"name"`
	Country  string         `json:"country"`
	Placing  int            `json:"placing"`
	Record   apiRecord      `json:"record"`
	Decklist map[string]int `json:"decklist"` // card name -> count
	Deck     *apiDeckType   `json:"deck"`     // optional
	Drop     *int           `json:"drop"`     // optional
}

type apiRecord struct {
	Wins   int `json:"wins"`
	Losses int `json:"losses"`
	Ties   int `json:"ties"`
}

type apiDeckType struct {
	ID    string   `json:"id"`
	Name  string   `json:"name"`
	Icons []string `json:"icons"` // card identifiers
}

// apiMatch represents a single match/round result
type apiMatch struct {
	RoundNumber int    `json:"roundNumber"`
	PhaseNumber int    `json:"phaseNumber"`
	TableNumber int    `json:"tableNumber,omitempty"`
	Player1     string `json:"player1"`
	Player2     string `json:"player2"`
	Winner      string `json:"winner,omitempty"` // Player ID of winner
	MatchLabel  string `json:"matchLabel,omitempty"`
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	if d.apiKey == "" {
		return fmt.Errorf("LIMITLESS_API_KEY environment variable not set - get one at https://play.limitlesstcg.com/account/settings/api")
	}

	opts, err := games.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	d.log.Infof(ctx, "Extracting Pokemon tournament decks from Limitless TCG API...")

	// Step 1: Fetch tournament list
	tournaments, err := d.fetchTournaments(ctx, sc, opts)
	if err != nil {
		return fmt.Errorf("failed to fetch tournaments: %w", err)
	}

	d.log.Infof(ctx, "Found %d tournaments", len(tournaments))

	// Step 2: For each tournament, fetch standings (which include decklists)
	totalDecks := 0
	for i, tournament := range tournaments {
		if limit, ok := opts.ItemLimit.Get(); ok && totalDecks >= limit {
			d.log.Infof(ctx, "Reached item limit of %d decks", limit)
			break
		}

		d.log.Infof(ctx, "Processing tournament %d/%d: %s (%s)", i+1, len(tournaments), tournament.Name, tournament.ID)

		standings, err := d.fetchStandings(ctx, sc, tournament.ID, opts)
		if err != nil {
			d.log.Field("tournament_id", tournament.ID).Errorf(ctx, "Failed to fetch standings: %v", err)
			continue
		}

		// Fetch match data for round results
		matches, err := d.fetchMatches(ctx, sc, tournament.ID, opts)
		if err != nil {
			d.log.Field("tournament_id", tournament.ID).Warnf(ctx, "Failed to fetch matches: %v (continuing without round results)", err)
			matches = nil
		}

		// Create lookup map: player ID -> matches
		playerMatches := make(map[string][]apiMatch)
		if matches != nil {
			for _, match := range matches {
				playerMatches[match.Player1] = append(playerMatches[match.Player1], match)
				playerMatches[match.Player2] = append(playerMatches[match.Player2], match)
			}
		}

		// Store each decklist as a collection
		for _, standing := range standings {
			if limit, ok := opts.ItemLimit.Get(); ok && totalDecks >= limit {
				break
			}

			// Get round results for this player
			var roundResults []game.RoundResult
			if playerMatches != nil {
				roundResults = d.buildRoundResults(standing.Player, playerMatches, standings)
			}

			if err := d.storeDecklist(ctx, tournament, standing, roundResults, opts); err != nil {
				d.log.Field("player", standing.Player).Errorf(ctx, "Failed to store decklist: %v", err)
				continue
			}

			totalDecks++
		}
	}

	d.log.Infof(ctx, "✅ Extracted %d Pokemon tournament decks from Limitless TCG", totalDecks)
	return nil
}

func (d *Dataset) fetchTournaments(
	ctx context.Context,
	sc *scraper.Scraper,
	opts games.ResolvedUpdateOptions,
) ([]apiTournament, error) {
	// API endpoint: GET /tournaments?game=PTCG&limit=100
	url := "https://play.limitlesstcg.com/api/tournaments?game=PTCG&limit=100"

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Access-Key", d.apiKey)

	resp, err := games.Do(ctx, sc, &opts, req)
	if err != nil {
		return nil, err
	}

	var tournaments []apiTournament
	if err := json.Unmarshal(resp.Response.Body, &tournaments); err != nil {
		return nil, fmt.Errorf("failed to parse tournaments response: %w", err)
	}

	// Apply scroll limit if specified
	if limit, ok := opts.ScrollLimit.Get(); ok && len(tournaments) > limit {
		tournaments = tournaments[:limit]
	}

	return tournaments, nil
}

func (d *Dataset) fetchStandings(
	ctx context.Context,
	sc *scraper.Scraper,
	tournamentID string,
	opts games.ResolvedUpdateOptions,
) ([]apiStanding, error) {
	url := fmt.Sprintf("https://play.limitlesstcg.com/api/tournaments/%s/standings", tournamentID)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Access-Key", d.apiKey)

	resp, err := games.Do(ctx, sc, &opts, req)
	if err != nil {
		return nil, err
	}

	var standings []apiStanding
	if err := json.Unmarshal(resp.Response.Body, &standings); err != nil {
		return nil, fmt.Errorf("failed to parse standings response: %w", err)
	}

	return standings, nil
}

func (d *Dataset) fetchMatches(
	ctx context.Context,
	sc *scraper.Scraper,
	tournamentID string,
	opts games.ResolvedUpdateOptions,
) ([]apiMatch, error) {
	// API endpoint: GET /tournaments/{id}/matches
	url := fmt.Sprintf("https://play.limitlesstcg.com/api/tournaments/%s/matches", tournamentID)

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Access-Key", d.apiKey)

	resp, err := games.Do(ctx, sc, &opts, req)
	if err != nil {
		return nil, err
	}

	var matches []apiMatch
	if err := json.Unmarshal(resp.Response.Body, &matches); err != nil {
		return nil, fmt.Errorf("failed to parse matches response: %w", err)
	}

	return matches, nil
}

func (d *Dataset) buildRoundResults(
	playerID string,
	playerMatches map[string][]apiMatch,
	standings []apiStanding,
) []game.RoundResult {
	matches := playerMatches[playerID]
	if len(matches) == 0 {
		return nil
	}

	// Create lookup maps for efficient lookup
	playerNameMap := make(map[string]string)      // playerID -> playerName
	playerArchetypeMap := make(map[string]string) // playerID -> archetype

	for _, standing := range standings {
		if standing.Player != "" {
			playerNameMap[standing.Player] = standing.Name
			if standing.Deck != nil && standing.Deck.Name != "" {
				playerArchetypeMap[standing.Player] = standing.Deck.Name
			}
		}
	}

	var roundResults []game.RoundResult
	for _, match := range matches {
		// Validate match data
		if match.RoundNumber <= 0 {
			continue // Skip invalid round numbers
		}

		// Determine opponent
		var opponentID string
		if match.Player1 == playerID {
			opponentID = match.Player2
		} else if match.Player2 == playerID {
			opponentID = match.Player1
		} else {
			continue // Match doesn't involve this player
		}

		// Get opponent name and archetype from lookup maps
		opponentName := playerNameMap[opponentID]
		if opponentName == "" {
			opponentName = opponentID // Fallback to ID if name not found
		}
		opponentDeck := playerArchetypeMap[opponentID]

		// Determine result
		result := "T" // Default to tie
		if match.Winner != "" {
			if match.Winner == playerID {
				result = "W"
			} else if match.Winner == opponentID {
				result = "L"
			}
			// If winner is neither player, keep as tie
		}

		roundResults = append(roundResults, game.RoundResult{
			RoundNumber:  match.RoundNumber,
			Opponent:     opponentName,
			OpponentDeck: opponentDeck,
			Result:       result,
			// GameWins/GameLosses not available from API, would need match detail endpoint
		})
	}

	// Sort by round number (using Go's sort package for efficiency)
	if len(roundResults) > 1 {
		sort.Slice(roundResults, func(i, j int) bool {
			return roundResults[i].RoundNumber < roundResults[j].RoundNumber
		})
	}

	return roundResults
}

func (d *Dataset) storeDecklist(
	ctx context.Context,
	tournament apiTournament,
	standing apiStanding,
	roundResults []game.RoundResult,
	opts games.ResolvedUpdateOptions,
) error {
	// Build unique ID: tournament_id:player_id
	id := fmt.Sprintf("%s:%s", tournament.ID, standing.Player)
	bkey := d.collectionKey(id)

	// Check if already exists (unless reparse requested)
	if !opts.Reparse && !opts.FetchReplaceAll {
		exists, err := d.blob.Exists(ctx, bkey)
		if err != nil {
			return fmt.Errorf("failed to check if collection exists: %w", err)
		}
		if exists {
			d.log.Field("player", standing.Player).Debugf(ctx, "Decklist already exists")
			return nil
		}
	}

	// Convert decklist to CardDesc format
	var cards []game.CardDesc
	for cardName, count := range standing.Decklist {
		cards = append(cards, game.CardDesc{
			Name:  cardName,
			Count: count,
		})
	}

	if len(cards) == 0 {
		return fmt.Errorf("decklist has no cards")
	}

	// Determine archetype name
	archetype := ""
	if standing.Deck != nil {
		archetype = standing.Deck.Name
	}

	// Extract tournament type from name
	tournamentType := extractTournamentType(tournament.Name)

	// Extract location from tournament name (e.g., "Regional Pittsburgh, PA")
	location := extractLocation(tournament.Name)

	// Build collection metadata
	deckType := &game.CollectionTypeDeck{
		Name:      fmt.Sprintf("%s - %s", tournament.Name, standing.Name),
		Format:    tournament.Format,
		Archetype: archetype,
		Player:    standing.Name,
		// Add custom metadata
		Event:          tournament.Name,
		Placement:      standing.Placing,
		EventDate:      tournament.Date.Format("2006-01-02"),
		TournamentType: tournamentType,
		TournamentSize: tournament.Players,
		TournamentID:   tournament.ID,
		Location:       location,
		Country:        standing.Country,
		RoundResults:   roundResults,
	}

	tw := game.CollectionTypeWrapper{
		Type:  deckType.Type(),
		Inner: deckType,
	}

	collection := game.Collection{
		Type:        tw,
		ID:          id,
		URL:         fmt.Sprintf("https://play.limitlesstcg.com/tournament/%s/standings", tournament.ID),
		ReleaseDate: tournament.Date,
		Partitions: []game.Partition{{
			Name:  "Deck",
			Cards: cards,
		}},
		Source: "limitless",
	}

	if err := collection.Canonicalize(); err != nil {
		return fmt.Errorf("collection is invalid: %w", err)
	}

	b, err := json.Marshal(collection)
	if err != nil {
		return err
	}

	return d.blob.Write(ctx, bkey, b)
}

// extractTournamentType extracts tournament type from tournament name
func extractTournamentType(name string) string {
	nameLower := strings.ToLower(name)

	// Check for common tournament types
	if strings.Contains(nameLower, "regional") {
		return "Regional"
	}
	if strings.Contains(nameLower, "championship") || strings.Contains(nameLower, "worlds") {
		return "Championship"
	}
	if strings.Contains(nameLower, "league cup") {
		return "League Cup"
	}
	if strings.Contains(nameLower, "league challenge") {
		return "League Challenge"
	}
	if strings.Contains(nameLower, "international") {
		return "International"
	}
	if strings.Contains(nameLower, "special event") {
		return "Special Event"
	}

	return ""
}

// extractLocation extracts location from tournament name
// Examples: "Regional Pittsburgh, PA", "Championship Las Vegas, NV"
func extractLocation(name string) string {
	// Look for patterns like "City, State" or "City, Country"
	// Common patterns: "Regional Pittsburgh, PA", "Championship Las Vegas, NV"

	// Try to find comma-separated location
	parts := strings.Split(name, ",")
	if len(parts) >= 2 {
		// Check if last part looks like a state/country (2-3 letters or full country name)
		lastPart := strings.TrimSpace(parts[len(parts)-1])
		if len(lastPart) <= 3 || strings.Contains(strings.ToLower(lastPart), "united states") {
			// Likely a location
			city := strings.TrimSpace(parts[len(parts)-2])
			// Remove tournament type prefix if present
			city = strings.TrimPrefix(city, "Regional")
			city = strings.TrimPrefix(city, "Championship")
			city = strings.TrimPrefix(city, "League Cup")
			city = strings.TrimPrefix(city, "League Challenge")
			city = strings.TrimSpace(city)
			return fmt.Sprintf("%s, %s", city, lastPart)
		}
	}

	return ""
}

var prefix = filepath.Join("pokemon", "limitless")

func (d *Dataset) collectionKey(collectionID string) string {
	return filepath.Join(prefix, collectionID+".json")
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(item games.Item) error,
	options ...games.IterItemsOption,
) error {
	return games.IterItemsBlobPrefix(
		ctx,
		d.blob,
		prefix+"/",
		func(key string, data []byte) (games.Item, error) {
			var collection game.Collection
			if err := json.Unmarshal(data, &collection); err != nil {
				return nil, err
			}
			return &games.CollectionItem{
				Collection: &collection,
			}, nil
		},
		fn,
		options...,
	)
}
