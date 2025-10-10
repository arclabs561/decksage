package limitlessweb

import (
	"bytes"
	"collections/blob"
	"collections/games/magic/dataset"
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

func (d *Dataset) Description() dataset.Description {
	return dataset.Description{
		Name: "limitless-web",
	}
}

var reDeckListURL = regexp.MustCompile(`^https://limitlesstcg\.com/decks/list/\d+$`)

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...dataset.UpdateOption,
) error {
	opts, err := dataset.ResolveUpdateOptions(options...)
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

	// Process each deck URL
	totalDecks := 0
	for i, deckURL := range deckURLs {
		if limit, ok := opts.ItemLimit.Get(); ok && totalDecks >= limit {
			d.log.Infof(ctx, "Reached item limit of %d", limit)
			break
		}

		if (i+1)%10 == 0 {
			d.log.Infof(ctx, "Processing deck %d/%d...", i+1, len(deckURLs))
		}

		if err := d.parseDeck(ctx, sc, deckURL, opts); err != nil {
			d.log.Field("url", deckURL).Errorf(ctx, "Failed to parse deck: %v", err)
			continue
		}

		totalDecks++
	}

	d.log.Infof(ctx, "✅ Extracted %d Pokemon tournament decks from Limitless TCG website", totalDecks)
	return nil
}

func (d *Dataset) scrapeDeckListingPages(
	ctx context.Context,
	sc *scraper.Scraper,
	opts dataset.ResolvedUpdateOptions,
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
		pageURLs := []string{}
		doc.Find("table tbody tr td a[href^='/decks/list/']").Each(func(i int, s *goquery.Selection) {
			href, exists := s.Attr("href")
			if !exists {
				return
			}
			fullURL := "https://limitlesstcg.com" + href
			// Deduplicate
			if !contains(allURLs, fullURL) && !contains(pageURLs, fullURL) {
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
	opts dataset.ResolvedUpdateOptions,
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
	eventDate := ""

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
	// For now use current date
	eventDate = time.Now().Format("2006-01-02")

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

		cards = append(cards, game.CardDesc{
			Name:  cardName,
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
		EventDate: eventDate,
	}

	tw := game.CollectionTypeWrapper{
		Type:  deckType.Type(),
		Inner: deckType,
	}

	collection := game.Collection{
		Type:        tw,
		ID:          deckID,
		URL:         deckURL,
		ReleaseDate: time.Now(), // Use current time as fallback
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

	return d.blob.Write(ctx, bkey, b)
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
	opts dataset.ResolvedUpdateOptions,
) (*scraper.Page, error) {
	return dataset.Do(ctx, sc, &opts, req)
}

var prefix = filepath.Join("pokemon", "limitless-web")

func (d *Dataset) collectionKey(collectionID string) string {
	return filepath.Join(prefix, collectionID+".json")
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(item dataset.Item) error,
	options ...dataset.IterItemsOption,
) error {
	return dataset.IterItemsBlobPrefix(
		ctx,
		d.blob,
		prefix+"/",
		func(key string, data []byte) (dataset.Item, error) {
			var collection game.Collection
			if err := json.Unmarshal(data, &collection); err != nil {
				return nil, err
			}
			return &dataset.CollectionItem{
				Collection: &collection,
			}, nil
		},
		fn,
		options...,
	)
}

func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}
