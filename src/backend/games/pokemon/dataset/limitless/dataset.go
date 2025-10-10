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

		// Store each decklist as a collection
		for _, standing := range standings {
			if limit, ok := opts.ItemLimit.Get(); ok && totalDecks >= limit {
				break
			}

			if err := d.storeDecklist(ctx, tournament, standing, opts); err != nil {
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

func (d *Dataset) storeDecklist(
	ctx context.Context,
	tournament apiTournament,
	standing apiStanding,
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

	// Build collection metadata
	deckType := &game.CollectionTypeDeck{
		Name:      fmt.Sprintf("%s - %s", tournament.Name, standing.Name),
		Format:    tournament.Format,
		Archetype: archetype,
		Player:    standing.Name,
		// Add custom metadata
		Event:     tournament.Name,
		Placement: standing.Placing,
		EventDate: tournament.Date.Format("2006-01-02"),
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
