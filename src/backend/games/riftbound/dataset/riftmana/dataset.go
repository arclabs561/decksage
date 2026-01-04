package riftmana

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

// Dataset scrapes Riftbound tournament decks from RiftMana
// Website: https://riftmana.com/tournaments/
// No API key required - scrapes tournament deck listings
type Dataset struct {
	log           *logger.Logger
	blob          *blob.Bucket
	browserScraper *scraper.BrowserScraper
}

var base *url.URL

func init() {
	u, err := url.Parse("https://riftmana.com/")
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
		log:            log,
		blob:           blob,
		browserScraper: browserScraper,
	}, nil
}

func (d *Dataset) Description() games.Description {
	return games.Description{
		Game: "riftbound",
		Name: "riftmana",
	}
}

var reDeckURL = regexp.MustCompile(`^https://riftmana\.com/tournaments?/[^/?]+$`)

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	opts, err := games.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	d.log.Infof(ctx, "Extracting Riftbound tournament decks from RiftMana (https://riftmana.com/tournaments/)...")

	// Get all tournament deck URLs
	deckURLs, err := d.scrapeTournamentListingPages(ctx)
	if err != nil {
		return fmt.Errorf("failed to scrape tournament listings: %w", err)
	}

	if len(deckURLs) == 0 {
		d.log.Warnf(ctx, "No tournament decks found on RiftMana")
		return nil
	}

	d.log.Infof(ctx, "Found %d tournament deck URLs to process", len(deckURLs))

	var totalDecks atomic.Int64
	var wg sync.WaitGroup
	sem := make(chan struct{}, 5) // Limit concurrent requests

	for _, deckURL := range deckURLs {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case sem <- struct{}{}:
		}

		wg.Add(1)
		go func(url string) {
			defer wg.Done()
			defer func() { <-sem }()

			if err := d.extractDeck(ctx, sc, url, opts); err != nil {
				d.log.Warnf(ctx, "Failed to extract deck from %s: %v", url, err)
				return
			}
			totalDecks.Add(1)
		}(deckURL)
	}

	wg.Wait()

	d.log.Infof(ctx, "✅ Extracted %d Riftbound tournament decks from RiftMana", totalDecks.Load())
	return nil
}

func (d *Dataset) scrapeTournamentListingPages(ctx context.Context) ([]string, error) {
	allURLs := make([]string, 0)
	seenURLs := make(map[string]bool)
	page := 1
	maxPages := 50 // Limit to prevent infinite loops

	for page <= maxPages {
		listingURL := fmt.Sprintf("https://riftmana.com/tournaments/?page=%d", page)
		if page == 1 {
			listingURL = "https://riftmana.com/tournaments/"
		}

		d.log.Debugf(ctx, "Scraping tournament listing page %d: %s", page, listingURL)

		// Use browser scraper for JavaScript rendering
		html, err := d.browserScraper.RenderPage(ctx, listingURL, ".tournament-list, .deck-list, .meta-deck", 45*time.Second)
		if err != nil {
			d.log.Warnf(ctx, "Failed to render page %d: %v", page, err)
			return nil, fmt.Errorf("failed to render listing page: %w", err)
		}

		doc, err := goquery.NewDocumentFromReader(bytes.NewReader(html))
		if err != nil {
			return nil, fmt.Errorf("failed to parse HTML: %w", err)
		}

		pageURLs := []string{}

		// Try multiple selectors for tournament/deck links
		selectors := []string{
			"a[href*='/tournaments/']",
			"a[href*='/tournament/']",
			".tournament-card a",
			".deck-card a",
			".meta-deck a",
			"table tbody tr td a[href*='tournament']",
			".deck-list a",
		}

		for _, selector := range selectors {
			doc.Find(selector).Each(func(i int, s *goquery.Selection) {
				href, exists := s.Attr("href")
				if !exists || href == "" {
					return
				}

				// Skip listing pages and pagination
				if href == "/tournaments" || href == "/tournaments/" || strings.Contains(href, "?page=") {
					return
				}

				// Resolve relative URLs
				var fullURL string
				if strings.HasPrefix(href, "http") {
					fullURL = href
				} else if strings.HasPrefix(href, "/") {
					fullURL = "https://riftmana.com" + href
				} else {
					fullURL = "https://riftmana.com/tournaments/" + href
				}

				// Must be a tournament/deck detail page
				if (strings.Contains(fullURL, "/tournaments/") || strings.Contains(fullURL, "/tournament/")) &&
					fullURL != "https://riftmana.com/tournaments" &&
					fullURL != "https://riftmana.com/tournaments/" &&
					!strings.Contains(fullURL, "?page=") &&
					!seenURLs[fullURL] {
					seenURLs[fullURL] = true
					pageURLs = append(pageURLs, fullURL)
				}
			})
		}

		if len(pageURLs) == 0 {
			d.log.Infof(ctx, "No more tournaments found on page %d, stopping", page)
			break
		}

		d.log.Infof(ctx, "Found %d tournament URLs on page %d", len(pageURLs), page)
		allURLs = append(allURLs, pageURLs...)
		page++
	}

	return allURLs, nil
}

func (d *Dataset) extractDeck(
	ctx context.Context,
	sc *scraper.Scraper,
	tournamentURL string,
	opts games.ResolvedUpdateOptions,
) error {
	// Use browser scraper for JavaScript rendering
	html, err := d.browserScraper.RenderPage(ctx, tournamentURL, ".deck-list, .card-list, .deck", 45*time.Second)
	if err != nil {
		return fmt.Errorf("failed to render tournament page: %w", err)
	}

	return d.parseTournamentPage(ctx, nil, tournamentURL, html, opts)
}

func (d *Dataset) parseTournamentPage(
	ctx context.Context,
	_ *scraper.Scraper,
	tournamentURL string,
	html []byte,
	opts games.ResolvedUpdateOptions,
) error {
	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(html))
	if err != nil {
		return fmt.Errorf("failed to parse HTML: %w", err)
	}

	// Extract tournament metadata
	tournamentName := doc.Find("h1, .tournament-title, .event-name").First().Text()
	if tournamentName == "" {
		tournamentName = "Unknown Tournament"
	}

	// Extract event date (try multiple formats)
	eventDate := time.Now()
	dateText := doc.Find(".tournament-date, .event-date, time").First().Text()
	if dateText != "" {
		// Try to parse date
		if parsed, err := time.Parse("2006-01-02", dateText); err == nil {
			eventDate = parsed
		} else if parsed, err := time.Parse("January 2, 2006", dateText); err == nil {
			eventDate = parsed
		}
	}

	// Find all deck entries on the page
	deckSelectors := []string{
		".deck-list .deck",
		".meta-deck",
		".tournament-deck",
		"table tbody tr",
		".deck-entry",
	}

	var decksFound int

	for _, selector := range deckSelectors {
		doc.Find(selector).Each(func(i int, s *goquery.Selection) {
			// Extract deck name/champion
			champion := s.Find(".champion, .champion-name, h3, h4").First().Text()
			if champion == "" {
				champion = s.Find("td").First().Text() // First column might be champion
			}
			champion = strings.TrimSpace(champion)

			// Extract placement
			placement := 0
			placementText := s.Find(".placement, .rank, .position").First().Text()
			if placementText == "" {
				// Try to extract from text like "1st", "2nd", etc.
				if match := regexp.MustCompile(`(\d+)(?:st|nd|rd|th)`).FindStringSubmatch(placementText); len(match) > 1 {
					if p, err := strconv.Atoi(match[1]); err == nil {
						placement = p
					}
				}
			} else {
				if p, err := strconv.Atoi(strings.TrimSpace(placementText)); err == nil {
					placement = p
				}
			}

			// Extract cards
			cards := make(map[string]int)
			s.Find(".card, .card-name, .card-entry").Each(func(j int, cardSel *goquery.Selection) {
				cardName := strings.TrimSpace(cardSel.Text())
				if cardName != "" {
					// Try to extract count (e.g., "2x Lightning Bolt")
					if match := regexp.MustCompile(`(\d+)\s*x?\s*(.+)`).FindStringSubmatch(cardName); len(match) > 2 {
						if count, err := strconv.Atoi(match[1]); err == nil {
							cardName = strings.TrimSpace(match[2])
							cards[cardName] = count
						}
					} else {
						cards[cardName] = cards[cardName] + 1
					}
				}
			})

			// If no cards found with card selector, try table cells
			if len(cards) == 0 {
				s.Find("td").Each(func(j int, td *goquery.Selection) {
					text := strings.TrimSpace(td.Text())
					if text != "" && !strings.Contains(text, "x") && len(text) > 3 {
						// Might be a card name
						cards[text] = cards[text] + 1
					}
				})
			}

			if len(cards) == 0 {
				return // Skip decks with no cards
			}

			if champion == "" {
				champion = "Unknown Champion"
			}

			// Store deck
			deckName := fmt.Sprintf("%s - %s", champion, tournamentName)
			if err := d.storeDecklist(ctx, deckName, champion, "Tournament", tournamentName, placement, eventDate, cards, opts); err != nil {
				d.log.Warnf(ctx, "Failed to store deck: %v", err)
				return
			}

			decksFound++
		})

		if decksFound > 0 {
			break // Found decks with this selector
		}
	}

	if decksFound == 0 {
		return fmt.Errorf("no cards found in tournament page")
	}

	return nil
}

func (d *Dataset) storeDecklist(
	ctx context.Context,
	deckName string,
	champion string,
	format string,
	event string,
	placement int,
	eventDate time.Time,
	cards map[string]int,
	opts games.ResolvedUpdateOptions,
) error {
	// Build unique ID
	id := fmt.Sprintf("riftmana:%s:%d", event, placement)
	bkey := d.collectionKey(id)

	// Check if already exists
	if !opts.Reparse && !opts.FetchReplaceAll {
		exists, err := d.blob.Exists(ctx, bkey)
		if err != nil {
			return fmt.Errorf("failed to check if collection exists: %w", err)
		}
		if exists {
			return nil
		}
	}

	// Convert decklist to CardDesc format
	var cardDescs []game.CardDesc
	for cardName, count := range cards {
		cardDescs = append(cardDescs, game.CardDesc{
			Name:  cardName,
			Count: count,
		})
	}

	if len(cardDescs) == 0 {
		return fmt.Errorf("decklist has no cards")
	}

	// Build collection metadata
	deckType := &game.CollectionTypeDeck{
		Name:      deckName,
		Format:    format,
		Champion:  champion,
		Event:     event,
		Placement: placement,
		EventDate: eventDate.Format("2006-01-02"),
	}

	tw := game.CollectionTypeWrapper{
		Type:  deckType.Type(),
		Inner: deckType,
	}

	collection := game.Collection{
		Type:        tw,
		ID:          id,
		URL:         fmt.Sprintf("https://riftmana.com/tournaments/"),
		ReleaseDate: eventDate,
		Partitions: []game.Partition{{
			Name:  "Deck",
			Cards: cardDescs,
		}},
		Source: "riftmana",
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

var prefix = filepath.Join("riftbound", "riftmana")

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

func (d *Dataset) Close() error {
	if d.browserScraper != nil {
		return d.browserScraper.Close()
	}
	return nil
}
