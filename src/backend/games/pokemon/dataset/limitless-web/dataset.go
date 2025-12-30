package limitlessweb

import (
	"bytes"
	"collections/blob"
	"collections/games"
	"collections/games/pokemon/game"
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

// Dataset scrapes Pokemon tournament decks from Limitless TCG public website
// No API key required - scrapes https://limitlesstcg.com/decks/lists
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
		Game: "pokemon",
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

	d.log.Infof(ctx, "Extracting Pokemon tournament decks from Limitless TCG website...")

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
							// Record error in statistics if available
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

	d.log.Infof(ctx, "✅ Extracted %d Pokemon tournament decks from Limitless TCG website", totalDecks.Load())
	return nil
}

func (d *Dataset) scrapeDeckListingPages(
	ctx context.Context,
	sc *scraper.Scraper,
	opts games.ResolvedUpdateOptions,
) ([]string, error) {
	// Start with the main deck lists page
	listingURL := "https://limitlesstcg.com/decks/lists"

	allURLs := []string{}
	page := 1
	maxPages := 10 // Default to scraping 10 pages
	if limit, ok := opts.ScrollLimit.Get(); ok {
		maxPages = limit
	}

	for page <= maxPages {
		pageURL := listingURL
		if page > 1 {
			pageURL = fmt.Sprintf("%s?page=%d", listingURL, page)
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

		// Find all deck links in the table
		// Use map for O(1) deduplication instead of O(n) linear search
		seenURLs := make(map[string]bool)
		pageURLs := []string{}
		doc.Find("table tbody tr td a[href^='/decks/list/']").Each(func(i int, s *goquery.Selection) {
			href, exists := s.Attr("href")
			if !exists {
				return
			}
			fullURL := "https://limitlesstcg.com" + href
			// Deduplicate using map for efficiency
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
	// Extract deck ID from URL
	reDeckID := regexp.MustCompile(`/decks/list/(\d+)$`)
	matches := reDeckID.FindStringSubmatch(deckURL)
	if len(matches) < 2 {
		return fmt.Errorf("failed to extract deck ID from URL")
	}
	deckID := matches[1]
	bkey := d.collectionKey(deckID)

	// Check if already exists
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

	// Fetch deck page
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

	// Extract deck name
	deckName := strings.TrimSpace(doc.Find(".decklist-title").First().Clone().Children().Remove().End().Text())

	// Extract player and tournament info from bottom section
	playerName := ""
	tournamentName := ""
	placement := 0
	eventDateStr := ""

	doc.Find(".decklist-results ul li").Each(func(i int, s *goquery.Selection) {
		text := s.Text()
		// Format: "1st Place Regional Pittsburgh, PA - Liam Halliburton"
		if strings.Contains(text, " Place ") || strings.Contains(text, "st ") || strings.Contains(text, "nd ") || strings.Contains(text, "rd ") || strings.Contains(text, "th ") {
			parts := strings.Split(text, " - ")
			if len(parts) >= 2 {
				playerName = strings.TrimSpace(parts[len(parts)-1])

				// Parse placement and tournament
				leftPart := strings.TrimSpace(parts[0])
				placeParts := strings.Fields(leftPart)
				if len(placeParts) >= 1 {
					placeStr := strings.ToLower(placeParts[0])
					placeStr = strings.TrimSuffix(placeStr, "st")
					placeStr = strings.TrimSuffix(placeStr, "nd")
					placeStr = strings.TrimSuffix(placeStr, "rd")
					placeStr = strings.TrimSuffix(placeStr, "th")
					if p, err := strconv.Atoi(placeStr); err == nil {
						placement = p
					}
				}
				if len(placeParts) >= 3 {
					// "1st Place Regional Pittsburgh, PA"
					tournamentName = strings.Join(placeParts[2:], " ")
				}
			}
		}
	})

	// Try to extract date from tournament link on listing page
	// For now use current date as fallback
	eventDateStr = time.Now().Format("2006-01-02")
	// Note: Could be improved by extracting actual event date from page

	// Parse card list from the data attributes
	cards := []game.CardDesc{}

	doc.Find(".decklist-card").Each(func(i int, s *goquery.Selection) {
		countStr := strings.TrimSpace(s.Find(".card-count").Text())
		cardName := strings.TrimSpace(s.Find(".card-name").Text())

		if countStr == "" || cardName == "" {
			return
		}

		count, err := strconv.Atoi(countStr)
		if err != nil {
			return
		}

		// Normalize card name for consistency
		normalizedName := games.NormalizeCardName(cardName)
		if normalizedName == "" {
			return // Skip empty card names
		}
		cards = append(cards, game.CardDesc{
			Name:  normalizedName,
			Count: count,
		})
	})

	if len(cards) == 0 {
		return fmt.Errorf("no cards found in deck")
	}

	// Determine archetype from deck name
	archetype := deckName

	// Build collection
	deckType := &game.CollectionTypeDeck{
		Name:      deckName,
		Format:    "Standard", // Default to Standard
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
		ReleaseDate: games.ParseDateWithFallback(eventDateStr, time.Now()), // Use parsed date or fallback
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
	
	// Record success in statistics if available
	if stats := games.ExtractStatsFromContext(ctx); stats != nil {
		stats.RecordSuccess()
	}
	
	return nil
}

var (
	reSilentThrottle = regexp.MustCompile(`rate.?limit|too.?many.?requests`)
	limiter          = ratelimit.New(30, ratelimit.Per(time.Minute)) // Conservative rate
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

var prefix = filepath.Join("pokemon", "limitless-web")

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

