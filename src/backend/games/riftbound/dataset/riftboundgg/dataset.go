package riftboundgg

import (
	"bytes"
	"collections/blob"
	"collections/games"
	"collections/games/riftbound/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"net/url"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/PuerkitoBio/goquery"
)

// Dataset scrapes Riftbound tournament decks from riftbound.gg
// No API key required - scrapes https://riftbound.gg/decks
// Uses Playwright for JavaScript rendering
type Dataset struct {
	log           *logger.Logger
	blob          *blob.Bucket
	browserScraper *scraper.BrowserScraper
}

var base *url.URL

func init() {
	u, err := url.Parse("https://riftbound.gg/")
	if err != nil {
		panic(err)
	}
	base = u
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) (*Dataset, error) {
	browserScraper, err := scraper.NewBrowserScraper(log)
	if err != nil {
		return nil, fmt.Errorf("failed to create browser scraper: %w", err)
	}

	return &Dataset{
		log:           log,
		blob:          blob,
		browserScraper: browserScraper,
	}, nil
}

func (d *Dataset) Description() games.Description {
	return games.Description{
		Game: "riftbound",
		Name: "riftboundgg",
	}
}

var reDeckURL = regexp.MustCompile(`^https://riftbound\.gg/decks?/[^/?]+$`)

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	defer func() {
		if d.browserScraper != nil {
			if err := d.browserScraper.Close(); err != nil {
				d.log.Errorf(ctx, "Failed to close browser scraper: %v", err)
			}
		}
	}()

	opts, err := games.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	d.log.Infof(ctx, "Extracting Riftbound tournament decks from riftbound.gg (using Playwright for JS rendering)...")

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
							stats.RecordCategorizedError(ctx, deckURL, "riftboundgg", err)
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
		select {
		case <-ctx.Done():
			break
		case tasks <- deckURL:
		}
	}
	close(tasks)
	wg.Wait()

	d.log.Infof(ctx, "✅ Extracted %d Riftbound tournament decks from riftbound.gg", totalDecks.Load())
	return nil
}

func (d *Dataset) scrapeDeckListingPages(
	ctx context.Context,
	sc *scraper.Scraper,
	opts games.ResolvedUpdateOptions,
) ([]string, error) {
	listingURL := "https://riftbound.gg/decks"

	allURLs := []string{}
	seenURLs := make(map[string]bool)
	page := 1
	maxPages := 10
	if limit, ok := opts.ScrollLimit.Get(); ok {
		maxPages = limit
	}

	for page <= maxPages {
		select {
		case <-ctx.Done():
			return allURLs, ctx.Err()
		default:
		}

		pageURL := listingURL
		if page > 1 {
			pageURL = fmt.Sprintf("%s?page=%d", listingURL, page)
		}

		// Use Playwright to render JavaScript-rendered page
		d.log.Infof(ctx, "Rendering page %d with Playwright...", page)
		// Use shorter timeout - site can be slow, but we'll accept partial content
		html, err := d.browserScraper.RenderPage(ctx, pageURL, "body", 30*time.Second)
		if err != nil {
			// If it's just a timeout, try to parse what we got
			if strings.Contains(err.Error(), "timeout") {
				d.log.Warnf(ctx, "Timeout rendering listing page %d, but attempting to parse partial content", page)
				// Try to get content anyway
				html, err = d.browserScraper.RenderPage(ctx, pageURL, "", 10*time.Second)
			}
			if err != nil {
				d.log.Warnf(ctx, "Failed to render listing page %d: %v", page, err)
				if page == 1 {
					// First page failure is critical
					return nil, fmt.Errorf("failed to render first listing page: %w", err)
				}
				// Subsequent page failures might mean we've reached the end
				break
			}
		}

		doc, err := goquery.NewDocumentFromReader(bytes.NewReader(html))
		if err != nil {
			return nil, fmt.Errorf("failed to parse HTML: %w", err)
		}

		pageURLs := []string{}

		// Try multiple selectors for deck links (site structure may vary)
		selectors := []string{
			"a[href*='/decks/']",
			"a[href*='/deck/']",
			".deck-list a",
			".deck-card a",
			".deck-grid a",
			"[data-deck]",
			"table tbody tr td a[href*='deck']",
		}

		for _, selector := range selectors {
			doc.Find(selector).Each(func(i int, s *goquery.Selection) {
				var href string
				var exists bool

				// Check for data-deck attribute first (embedded widgets)
				if selector == "[data-deck]" {
					deckID, ok := s.Attr("data-deck")
					if ok && deckID != "" {
						href = "/decks/" + deckID
						exists = true
					}
				} else {
					href, exists = s.Attr("href")
				}

				if !exists || href == "" {
					return
				}

				// Skip listing pages and pagination
				if href == "/decks" || href == "/decks/" || strings.Contains(href, "?page=") {
					return
				}

				// Resolve relative URLs
				var fullURL string
				if strings.HasPrefix(href, "http") {
					fullURL = href
				} else if strings.HasPrefix(href, "/") {
					fullURL = "https://riftbound.gg" + href
				} else {
					fullURL = "https://riftbound.gg/decks/" + href
				}

				// Must be a deck detail page, not listing page
				if reDeckURL.MatchString(fullURL) &&
					fullURL != "https://riftbound.gg/decks" &&
					fullURL != "https://riftbound.gg/decks/" &&
					!strings.Contains(fullURL, "?page=") &&
					!seenURLs[fullURL] {
					seenURLs[fullURL] = true
					pageURLs = append(pageURLs, fullURL)
				}
			})
		}

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
	// Extract deck ID from URL - handle various URL formats
	reDeckID := regexp.MustCompile(`/decks?/([^/?]+)`)
	matches := reDeckID.FindStringSubmatch(deckURL)
	if len(matches) < 2 {
		return fmt.Errorf("failed to extract deck ID from URL: %s", deckURL)
	}
	deckID := matches[1]

	// Skip if it's just "decks" (listing page)
	if deckID == "" || deckID == "decks" {
		return fmt.Errorf("invalid deck URL (listing page): %s", deckURL)
	}
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

	// Use Playwright to render JavaScript-rendered deck page
	d.log.Debugf(ctx, "Rendering deck page %s with Playwright...", deckURL)
	// Use longer timeout for deck pages and more flexible wait selector
	html, err := d.browserScraper.RenderPage(ctx, deckURL, "body", 45*time.Second)
	if err != nil {
		// Log warning but try to parse anyway - page might have loaded partially
		d.log.Warnf(ctx, "Timeout/error rendering deck page %s, attempting to parse partial content: %v", deckURL, err)
		// Try one more time with shorter timeout
		html, err = d.browserScraper.RenderPage(ctx, deckURL, "", 20*time.Second)
		if err != nil {
			return fmt.Errorf("failed to render deck page with Playwright after retry: %w", err)
		}
	}

	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(html))
	if err != nil {
		return fmt.Errorf("failed to parse deck HTML: %w", err)
	}

	// Extract deck metadata
	deckName := doc.Find("h1, .deck-title, .deck-name, [data-deck-name]").First().Text()
	deckName = strings.TrimSpace(deckName)
	if deckName == "" {
		deckName = "Untitled Deck"
	}

	// Extract tournament info (if available)
	tournamentName := ""
	playerName := ""
	placement := 0
	eventDateStr := ""

	doc.Find(".deck-info, .tournament-info, .meta-info, .deck-meta").Each(func(i int, s *goquery.Selection) {
		text := s.Text()
		if strings.Contains(text, "Tournament:") || strings.Contains(text, "Event:") {
			parts := strings.Split(text, ":")
			if len(parts) > 1 {
				tournamentName = strings.TrimSpace(parts[1])
			}
		}
		if strings.Contains(text, "Player:") || strings.Contains(text, "Author:") {
			parts := strings.Split(text, ":")
			if len(parts) > 1 {
				playerName = strings.TrimSpace(parts[1])
			}
		}
		if strings.Contains(text, "Placement:") || strings.Contains(text, "Place:") || strings.Contains(text, "Rank:") {
			parts := strings.Split(text, ":")
			if len(parts) > 1 {
				placeStr := strings.TrimSpace(parts[1])
				if p, err := strconv.Atoi(strings.Fields(placeStr)[0]); err == nil {
					placement = p
				}
			}
		}
		if strings.Contains(text, "Date:") {
			parts := strings.Split(text, ":")
			if len(parts) > 1 {
				eventDateStr = strings.TrimSpace(parts[1])
			}
		}
	})

	// Extract cards from deck list - try multiple selectors
	cards := []game.CardDesc{}

	cardSelectors := []string{
		".deck-list .card",
		".card-list .card",
		".deck-cards .card",
		"table.deck-list tbody tr",
		".card-row",
		"[data-card-name]",
		".deck-list tr",
		"tbody tr",
	}

	for _, selector := range cardSelectors {
		doc.Find(selector).Each(func(i int, s *goquery.Selection) {
			var cardName string
			var count int = 1

			// Try to get card name from various attributes/selectors
			if name, exists := s.Attr("data-card-name"); exists {
				cardName = name
			} else if name, exists := s.Attr("data-card"); exists {
				cardName = name
			} else {
				cardName = s.Find(".card-name, .name, td:first-child, [class*='name'], [class*='card']").First().Text()
			}
			cardName = strings.TrimSpace(cardName)
			if cardName == "" {
				return
			}

			// Try to get count
			if countStr, exists := s.Attr("data-count"); exists {
				if c, err := strconv.Atoi(countStr); err == nil {
					count = c
				}
			} else {
				countStr := s.Find(".card-count, .count, td:last-child, [class*='count']").Text()
				countStr = strings.TrimSpace(countStr)
				if c, err := strconv.Atoi(countStr); err == nil {
					count = c
				}
			}

			// Only add if we have a valid card name
			if count > 0 && cardName != "" {
				for i := 0; i < count; i++ {
					cards = append(cards, game.CardDesc{
						Name: cardName,
					})
				}
			}
		})

		if len(cards) > 0 {
			break // Found cards with this selector
		}
	}

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
		Source: "riftboundgg",
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

var prefix = filepath.Join("riftbound", "riftboundgg")

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
