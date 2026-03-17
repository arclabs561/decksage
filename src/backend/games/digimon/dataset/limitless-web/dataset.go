package limitlessweb

import (
	"bytes"
	"collections/blob"
	"collections/games"
	"collections/games/digimon/game"
	"collections/logger"
	"context"
	"encoding/json"
	"fmt"
	limpet "github.com/arclabs561/limpet"
	"net/http"
	"net/url"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/PuerkitoBio/goquery"
	"go.uber.org/ratelimit"
)

// Dataset scrapes Digimon tournament decks from Limitless TCG play platform.
// Digimon decklists are hosted on play.limitlesstcg.com (the tournament platform),
// not the main database site. Decks are organized by archetype under
// /decks?game=DCG, with individual decklists at /tournament/{id}/player/{name}/decklist.
type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

var base *url.URL

func init() {
	u, err := url.Parse("https://play.limitlesstcg.com/")
	if err != nil {
		panic(err)
	}
	base = u
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) *Dataset {
	return &Dataset{
		log:  log,
		blob: blob,
	}
}

func (d *Dataset) Description() games.Description {
	return games.Description{
		Game: "digimon",
		Name: "limitless-web",
	}
}

var reDeckListURL = regexp.MustCompile(`^https://play\.limitlesstcg\.com/tournament/[a-f0-9]+/player/[^/]+/decklist$`)

func (d *Dataset) Extract(
	ctx context.Context,
	sc *limpet.Client,
	options ...games.UpdateOption,
) error {
	opts, err := games.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	d.log.Infof(ctx, "Extracting Digimon tournament decks from Limitless TCG play platform...")

	// Scrape deck listing pages to get deck URLs
	deckURLs := []string{}
	if len(opts.ItemOnlyURLs) > 0 {
		deckURLs = opts.ItemOnlyURLs
	} else {
		var err error
		deckURLs, err = d.scrapeDeckListingPages(ctx, sc, &opts)
		if err != nil {
			return fmt.Errorf("failed to scrape deck listings: %w", err)
		}
	}

	d.log.Infof(ctx, "Found %d deck URLs to process", len(deckURLs))

	// Process deck URLs in parallel using worker pool
	tasks := make(chan string, len(deckURLs))
	wg := new(sync.WaitGroup)
	var totalDecks atomic.Int64

	for i := 0; i < opts.Parallel; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				select {
				case <-ctx.Done():
					return
				case deckURL, ok := <-tasks:
					if !ok {
						return
					}
					if limit, ok := opts.ItemLimit.Get(); ok && int(totalDecks.Load()) >= limit {
						return
					}
					if err := d.parseDeck(ctx, sc, deckURL, &opts); err != nil {
						d.log.Field("url", deckURL).Errorf(ctx, "Failed to parse deck: %v", err)
						if stats := games.ExtractStatsFromContext(ctx); stats != nil {
							stats.RecordCategorizedError(ctx, deckURL, "limitless-web", err)
						}
						continue
					}
					totalDecks.Add(1)
					if totalDecks.Load()%10 == 0 {
						d.log.Infof(ctx, "Processed %d/%d decks...", totalDecks.Load(), len(deckURLs))
					}
				}
			}
		}()
	}

	// Send all URLs to workers
	for _, deckURL := range deckURLs {
		if limit, ok := opts.ItemLimit.Get(); ok && int(totalDecks.Load()) >= limit {
			break
		}
		tasks <- deckURL
	}
	close(tasks)
	wg.Wait()

	d.log.Infof(ctx, "Extracted %d Digimon tournament decks from Limitless TCG play platform", totalDecks.Load())
	return nil
}

func (d *Dataset) scrapeDeckListingPages(
	ctx context.Context,
	sc *limpet.Client,
	opts *games.ResolvedUpdateOptions,
) ([]string, error) {
	// Digimon decks are on the play platform, organized by archetype.
	// First, scrape the metagame page to get archetype URLs.
	metaURL := "https://play.limitlesstcg.com/decks?game=DCG&format=standard"

	req, err := http.NewRequest("GET", metaURL, nil)
	if err != nil {
		return nil, err
	}

	resp, err := d.fetch(ctx, sc, req, opts)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch metagame page: %w", err)
	}

	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(resp.Response.Body))
	if err != nil {
		return nil, err
	}

	// Collect archetype page URLs (e.g., /decks/styraco?game=DCG&format=standard&set=EX11)
	archetypeURLs := []string{}
	seenArchetypes := make(map[string]bool)
	doc.Find("a[href*='/decks/'][href*='game=DCG']").Each(func(i int, s *goquery.Selection) {
		href, exists := s.Attr("href")
		if !exists {
			return
		}
		// Skip matchup links
		if strings.Contains(href, "/matchups") {
			return
		}
		fullURL := "https://play.limitlesstcg.com" + href
		if !seenArchetypes[fullURL] {
			seenArchetypes[fullURL] = true
			archetypeURLs = append(archetypeURLs, fullURL)
		}
	})

	d.log.Infof(ctx, "Found %d Digimon archetypes to scrape", len(archetypeURLs))

	// For each archetype, scrape individual decklist URLs
	allURLs := []string{}
	seenURLs := make(map[string]bool)
	maxPages := 10
	if limit, ok := opts.ScrollLimit.Get(); ok {
		maxPages = limit
	}

	// Limit number of archetypes to scrape based on page limit
	archetypeLimit := maxPages
	if archetypeLimit > len(archetypeURLs) {
		archetypeLimit = len(archetypeURLs)
	}

	for i, archURL := range archetypeURLs[:archetypeLimit] {
		d.log.Infof(ctx, "Scraping archetype %d/%d: %s", i+1, archetypeLimit, archURL)

		archReq, err := http.NewRequest("GET", archURL, nil)
		if err != nil {
			d.log.Errorf(ctx, "Failed to create request for archetype: %v", err)
			continue
		}

		archResp, err := d.fetch(ctx, sc, archReq, opts)
		if err != nil {
			d.log.Errorf(ctx, "Failed to fetch archetype page: %v", err)
			continue
		}

		archDoc, err := goquery.NewDocumentFromReader(bytes.NewReader(archResp.Response.Body))
		if err != nil {
			d.log.Errorf(ctx, "Failed to parse archetype page: %v", err)
			continue
		}

		// Find individual decklist links: /tournament/{id}/player/{name}/decklist
		archDoc.Find("a[href*='/player/'][href*='/decklist']").Each(func(j int, s *goquery.Selection) {
			href, exists := s.Attr("href")
			if !exists {
				return
			}
			fullURL := "https://play.limitlesstcg.com" + href
			if !seenURLs[fullURL] {
				seenURLs[fullURL] = true
				allURLs = append(allURLs, fullURL)
			}
		})
	}

	return allURLs, nil
}

// reDeckCard matches Digimon card lines: "4 CardName (SET-NNN)" or "1 CardName (SET-NNN)"
var reDeckCard = regexp.MustCompile(`^(\d+)\s+(.+?)\s+\(([A-Z0-9]+-[A-Z]?\d+)\)$`)

func (d *Dataset) parseDeck(
	ctx context.Context,
	sc *limpet.Client,
	deckURL string,
	opts *games.ResolvedUpdateOptions,
) error {
	// Extract a stable ID from the URL: tournament_id + player_name
	reDeckID := regexp.MustCompile(`/tournament/([a-f0-9]+)/player/([^/]+)/decklist$`)
	matches := reDeckID.FindStringSubmatch(deckURL)
	if len(matches) < 3 {
		return fmt.Errorf("failed to extract deck ID from URL")
	}
	deckID := matches[1] + "_" + matches[2]
	bkey := d.collectionKey(deckID)

	if !opts.Reparse && !opts.FetchReplaceAll {
		exists, err := d.blob.Exists(ctx, bkey)
		if err != nil {
			return fmt.Errorf("failed to check if deck exists: %w", err)
		}
		if exists {
			d.log.Field("deck_id", deckID).Debugf(ctx, "Deck already exists")
			return nil
		}
	}

	req, err := http.NewRequest("GET", deckURL, nil)
	if err != nil {
		return err
	}

	resp, err := d.fetch(ctx, sc, req, opts)
	if err != nil {
		return fmt.Errorf("failed to fetch deck page: %w", err)
	}

	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(resp.Response.Body))
	if err != nil {
		return err
	}

	// Extract player name and deck archetype from .infobox
	playerName := ""
	deckName := ""
	infobox := doc.Find(".infobox")
	if infobox.Length() > 0 {
		heading := infobox.Find(".heading")
		// Player name is the text node before the flag image
		playerName = strings.TrimSpace(heading.Clone().Children().Remove().End().Text())
		// Deck archetype from .deck-name
		deckName = strings.TrimSpace(heading.Find(".deck-name").Text())
	}

	// Extract tournament name from tournament header
	tournamentName := strings.TrimSpace(doc.Find(".tournament-header .name").Text())

	// Extract placement from .details text (e.g., "15 points (5-0-0)")
	placement := 0
	details := strings.TrimSpace(infobox.Find(".details").Text())
	_ = details // Placement is not directly available in this format

	eventDateStr := time.Now().Format("2006-01-02")

	// Parse cards from the decklist.
	// Structure: .decklist .column .cards, with <p><a>4 CardName (SET-NNN)</a></p>
	cards := []game.CardDesc{}

	doc.Find(".decklist .cards p").Each(func(i int, s *goquery.Selection) {
		text := strings.TrimSpace(s.Text())
		if text == "" {
			return
		}

		m := reDeckCard.FindStringSubmatch(text)
		if m == nil {
			return
		}

		count, err := strconv.Atoi(m[1])
		if err != nil {
			return
		}

		// Card name includes the set code in parens, e.g., "Elizamon (BT21-008)"
		// Keep the full name with set code for uniqueness (same card name can appear
		// from different sets)
		cardName := fmt.Sprintf("%s (%s)", m[2], m[3])
		normalizedName := games.NormalizeCardName(cardName)
		if normalizedName == "" {
			return
		}

		cards = append(cards, game.CardDesc{
			Name:  normalizedName,
			Count: count,
		})
	})

	if len(cards) == 0 {
		return fmt.Errorf("no cards found in deck")
	}

	archetype := deckName

	deckType := &game.CollectionTypeDeck{
		Name:      deckName,
		Format:    "Standard",
		Archetype: archetype,
		Player:    playerName,
		Event:     tournamentName,
		Placement: placement,
		EventDate: eventDateStr,
	}

	tw := game.CollectionTypeWrapper{
		Type:  deckType.Type(),
		Inner: deckType,
	}

	collection := game.Collection{
		Type:        tw,
		ID:          deckID,
		URL:         deckURL,
		ReleaseDate: games.ParseDateWithFallback(eventDateStr, time.Now()),
		Partitions: []game.Partition{{
			Name:  "Deck",
			Cards: cards,
		}},
		Source: "limitless-web",
	}

	if err := collection.Canonicalize(); err != nil {
		return fmt.Errorf("collection is invalid: %w", err)
	}

	b, err := json.Marshal(collection)
	if err != nil {
		return err
	}

	if err := d.blob.Write(ctx, bkey, b); err != nil {
		return err
	}

	if stats := games.ExtractStatsFromContext(ctx); stats != nil {
		stats.RecordSuccess()
	}

	return nil
}

var (
	reSilentThrottle = regexp.MustCompile(`rate.?limit|too.?many.?requests`)
	limiter          = ratelimit.New(30, ratelimit.Per(time.Minute))
	defaultFetchCfg  = limpet.DoConfig{
		SilentThrottle: reSilentThrottle,
		Limiter:        limiter,
	}
)

func (d *Dataset) fetch(
	ctx context.Context,
	sc *limpet.Client,
	req *http.Request,
	opts *games.ResolvedUpdateOptions,
) (*limpet.Page, error) {
	cfg := defaultFetchCfg
	cfg.Replace = opts.FetchReplaceAll
	return sc.Do(ctx, req, cfg)
}

var prefix = filepath.Join("digimon", "limitless-web")

func (d *Dataset) collectionKey(collectionID string) string {
	return filepath.Join(prefix, collectionID+".json")
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(item games.Item) error,
	options ...games.IterItemsOption,
) error {
	return games.IterItemsBlobPrefix(ctx, d.blob, prefix, games.DeserializeAsCollection, fn, options...)
}
