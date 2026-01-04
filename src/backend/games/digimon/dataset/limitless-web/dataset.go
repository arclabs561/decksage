package limitlessweb

import (
	"bytes"
	"collections/blob"
	"collections/games"
	"collections/games/digimon/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
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

// Dataset scrapes Digimon tournament decks from Limitless TCG public website
// No API key required - scrapes https://limitlesstcg.com/decks/lists?game=DCG
type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

var base *url.URL

func init() {
	u, err := url.Parse("https://limitlesstcg.com/")
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

var reDeckListURL = regexp.MustCompile(`^https://limitlesstcg\.com/decks/list/\d+$`)

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	opts, err := games.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	d.log.Infof(ctx, "Extracting Digimon tournament decks from Limitless TCG website...")

	// Scrape deck listing pages to get deck URLs
	deckURLs := []string{}
	if len(opts.ItemOnlyURLs) > 0 {
		deckURLs = opts.ItemOnlyURLs
	} else {
		var err error
		deckURLs, err = d.scrapeDeckListingPages(ctx, sc, opts)
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
					if err := d.parseDeck(ctx, sc, deckURL, opts); err != nil {
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

	d.log.Infof(ctx, "✅ Extracted %d Digimon tournament decks from Limitless TCG website", totalDecks.Load())
	return nil
}

func (d *Dataset) scrapeDeckListingPages(
	ctx context.Context,
	sc *scraper.Scraper,
	opts games.ResolvedUpdateOptions,
) ([]string, error) {
	// Use game=DCG filter for Digimon
	listingURL := "https://limitlesstcg.com/decks/lists?game=DCG"

	allURLs := []string{}
	page := 1
	maxPages := 10
	if limit, ok := opts.ScrollLimit.Get(); ok {
		maxPages = limit
	}

	for page <= maxPages {
		pageURL := listingURL
		if page > 1 {
			pageURL = fmt.Sprintf("%s&page=%d", listingURL, page)
		}

		req, err := http.NewRequest("GET", pageURL, nil)
		if err != nil {
			return nil, err
		}

		resp, err := d.fetch(ctx, sc, req, opts)
		if err != nil {
			return nil, fmt.Errorf("failed to fetch listing page %d: %w", page, err)
		}

		doc, err := goquery.NewDocumentFromReader(bytes.NewReader(resp.Response.Body))
		if err != nil {
			return nil, err
		}

		seenURLs := make(map[string]bool)
		pageURLs := []string{}
		doc.Find("table tbody tr td a[href^='/decks/list/']").Each(func(i int, s *goquery.Selection) {
			href, exists := s.Attr("href")
			if !exists {
				return
			}
			fullURL := "https://limitlesstcg.com" + href
			if !seenURLs[fullURL] {
				seenURLs[fullURL] = true
				pageURLs = append(pageURLs, fullURL)
			}
		})

		if len(pageURLs) == 0 {
			d.log.Infof(ctx, "No more decks found on page %d, stopping", page)
			break
		}

		d.log.Infof(ctx, "Found %d deck URLs on page %d", len(pageURLs), page)
		allURLs = append(allURLs, pageURLs...)
		page++
	}

	return allURLs, nil
}

func (d *Dataset) parseDeck(
	ctx context.Context,
	sc *scraper.Scraper,
	deckURL string,
	opts games.ResolvedUpdateOptions,
) error {
	reDeckID := regexp.MustCompile(`/decks/list/(\d+)$`)
	matches := reDeckID.FindStringSubmatch(deckURL)
	if len(matches) < 2 {
		return fmt.Errorf("failed to extract deck ID from URL")
	}
	deckID := matches[1]
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

	// Extract deck metadata
	deckName := doc.Find("h1").First().Text()
	deckName = strings.TrimSpace(deckName)

	// Extract tournament info
	tournamentName := ""
	playerName := ""
	placement := 0
	eventDateStr := ""

	doc.Find(".deck-info, .tournament-info").Each(func(i int, s *goquery.Selection) {
		text := s.Text()
		if strings.Contains(text, "Tournament:") {
			tournamentName = strings.TrimSpace(strings.Split(text, "Tournament:")[1])
		}
		if strings.Contains(text, "Player:") {
			playerName = strings.TrimSpace(strings.Split(text, "Player:")[1])
		}
		if strings.Contains(text, "Placement:") || strings.Contains(text, "Place:") {
			placeStr := strings.TrimSpace(strings.Split(text, ":")[1])
			if p, err := strconv.Atoi(strings.Fields(placeStr)[0]); err == nil {
				placement = p
			}
		}
		if strings.Contains(text, "Date:") {
			eventDateStr = strings.TrimSpace(strings.Split(text, "Date:")[1])
		}
	})

	// Extract cards from deck list
	cards := []game.CardDesc{}
	doc.Find(".deck-list .card, .card-list .card, table tbody tr").Each(func(i int, s *goquery.Selection) {
		cardName := s.Find(".card-name, td:first-child").Text()
		cardName = strings.TrimSpace(cardName)
		if cardName == "" {
			return
		}

		countStr := s.Find(".card-count, td:last-child").Text()
		countStr = strings.TrimSpace(countStr)
		count := 1
		if c, err := strconv.Atoi(countStr); err == nil {
			count = c
		}

		for i := 0; i < count; i++ {
			cards = append(cards, game.CardDesc{
				Name: cardName,
			})
		}
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
	defaultFetchOpts = []scraper.DoOption{
		&scraper.OptDoSilentThrottle{
			PageBytesRegexp: reSilentThrottle,
		},
		&scraper.OptDoLimiter{
			Limiter: limiter,
		},
	}
)

func (d *Dataset) fetch(
	ctx context.Context,
	sc *scraper.Scraper,
	req *http.Request,
	opts games.ResolvedUpdateOptions,
) (*scraper.Page, error) {
	return games.Do(ctx, sc, &opts, req)
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
