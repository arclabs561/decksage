package ygoprodecktournament

import (
	"bytes"
	"collections/blob"
	"collections/games/magic/dataset"
	"collections/games/yugioh/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"go.uber.org/ratelimit"
)

// Dataset scrapes Yu-Gi-Oh tournament decks from YGOPRODeck tournament section
// Source: https://ygoprodeck.com/category/format/tournament%20meta%20decks
type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

var base *url.URL

func init() {
	u, err := url.Parse("https://ygoprodeck.com/")
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
		Name: "ygoprodeck-tournament",
	}
}

var reDeckURL = regexp.MustCompile(`^https://ygoprodeck\.com/deck/[\w-]+$`)
var reDeckID = regexp.MustCompile(`/deck/([\w-]+)$`)

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...dataset.UpdateOption,
) error {
	opts, err := dataset.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	d.log.Infof(ctx, "Extracting Yu-Gi-Oh tournament decks from YGOPRODeck...")

	// Scrape listing pages to get deck URLs
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

	// Dedupe URLs to avoid redundant work
	uniq := make(map[string]struct{}, len(deckURLs))
	deduped := make([]string, 0, len(deckURLs))
	for _, u := range deckURLs {
		if _, ok := uniq[u]; ok {
			continue
		}
		uniq[u] = struct{}{}
		deduped = append(deduped, u)
	}

	d.log.Infof(ctx, "Found %d deck URLs to process (%d after dedupe)", len(deckURLs), len(deduped))

	// Process each deck (sequential; respects item limit)
	totalDecks := 0
	for i, deckURL := range deduped {
		if limit, ok := opts.ItemLimit.Get(); ok && totalDecks >= limit {
			d.log.Infof(ctx, "Reached item limit of %d", limit)
			break
		}

		if (i+1)%10 == 0 {
			d.log.Infof(ctx, "Processing deck %d/%d...", i+1, len(deduped))
		}

		if err := d.parseDeck(ctx, sc, deckURL, opts); err != nil {
			d.log.Field("url", deckURL).Errorf(ctx, "Failed to parse deck: %v", err)
			continue
		}

		totalDecks++
	}

	d.log.Infof(ctx, "✅ Extracted %d Yu-Gi-Oh tournament decks from YGOPRODeck", totalDecks)
	return nil
}

func (d *Dataset) scrapeDeckListingPages(
	ctx context.Context,
	sc *scraper.Scraper,
	opts dataset.ResolvedUpdateOptions,
) ([]string, error) {
	listingURL := "https://ygoprodeck.com/api/decks/getDecks.php"

	allURLs := []string{}
	limit := 100 // API limit per page
	// Support start/limit via options
	startPage := opts.ScrollStart.OrElse(0)
	maxPages := opts.ScrollLimit.OrElse(0)
	maxOffset := 50 * limit
	if maxPages > 0 {
		maxOffset = (startPage + maxPages) * limit
	}

	for offset := startPage * limit; offset <= maxOffset; offset += limit {
		// Construct URL with category and offset
		u, err := url.Parse(listingURL)
		if err != nil {
			return nil, err
		}
		q := u.Query()
		q.Set("_sft_category", "Tournament Meta Decks")
		q.Set("offset", fmt.Sprintf("%d", offset))
		q.Set("limit", fmt.Sprintf("%d", limit))
		u.RawQuery = q.Encode()
		pageURL := u.String()

		req, err := http.NewRequest("GET", pageURL, nil)
		if err != nil {
			return nil, err
		}

		resp, err := d.fetch(ctx, sc, req, opts)
		if err != nil {
			return nil, fmt.Errorf("failed to fetch listing page with offset %d: %w", offset, err)
		}

		var decks []struct {
			PrettyURL string `json:"pretty_url"`
		}
		if err := json.Unmarshal(resp.Response.Body, &decks); err != nil {
			return nil, fmt.Errorf("failed to unmarshal decks json at offset %d: %w", offset, err)
		}

		if len(decks) == 0 {
			d.log.Infof(ctx, "No more decks found at offset %d, stopping", offset)
			break
		}

		pageURLs := []string{}
		for _, deck := range decks {
			if deck.PrettyURL == "" {
				continue
			}
			fullURL := "https://ygoprodeck.com/deck/" + deck.PrettyURL
			pageURLs = append(pageURLs, fullURL)
		}

		d.log.Infof(ctx, "Found %d deck URLs at offset %d", len(pageURLs), offset)
		allURLs = append(allURLs, pageURLs...)
	}

	return allURLs, nil
}

func (d *Dataset) parseDeck(
	ctx context.Context,
	sc *scraper.Scraper,
	deckURL string,
	opts dataset.ResolvedUpdateOptions,
) error {
	// Extract deck ID
	matches := reDeckID.FindStringSubmatch(deckURL)
	if len(matches) < 2 {
		return fmt.Errorf("failed to extract deck ID from URL")
	}
	deckID := matches[1]
	bkey := d.collectionKey(deckID)

	// Check if exists
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

	// Extract deck name (first heading)
	deckName := strings.TrimSpace(doc.Find("h1, .entry-title").First().Text())

	// Extract metadata from "Deck Primer" section
	primerText := doc.Find(".deck-primer, .entry-content p").First().Text()

	playerName := ""
	tournamentName := ""
	placement := ""
	eventDate := ""

	// Parse format like: "Creator: Pablo Cesar Dominguez Lamazares"
	if strings.Contains(primerText, "Creator:") {
		re := regexp.MustCompile(`Creator:\s*(.+?)(?:\n|Tournament|$)`)
		if matches := re.FindStringSubmatch(primerText); len(matches) > 1 {
			playerName = strings.TrimSpace(matches[1])
		}
	}

	// Parse "Tournament: YCS Lima – September 27th 2025"
	if strings.Contains(primerText, "Tournament:") {
		re := regexp.MustCompile(`Tournament:\s*(.+?)(?:\n|Placement|$)`)
		if matches := re.FindStringSubmatch(primerText); len(matches) > 1 {
			tournamentFull := strings.TrimSpace(matches[1])
			// Split on em-dash or hyphen to get tournament name and date
			parts := strings.Split(tournamentFull, "–")
			if len(parts) < 2 {
				parts = strings.Split(tournamentFull, "-")
			}
			if len(parts) >= 1 {
				tournamentName = strings.TrimSpace(parts[0])
			}
			if len(parts) >= 2 {
				eventDate = strings.TrimSpace(parts[len(parts)-1])
			}
		}
	}

	// Parse "Placement: Top 16"
	if strings.Contains(primerText, "Placement:") {
		re := regexp.MustCompile(`Placement:\s*(.+?)(?:\n|$)`)
		if matches := re.FindStringSubmatch(primerText); len(matches) > 1 {
			placement = strings.TrimSpace(matches[1])
		}
	}

	// YGOPRODeck has card lists in the "Deck Breakdown" section
	// Try multiple approaches to parse cards

	mainCards := []game.CardDesc{}
	extraCards := []game.CardDesc{}
	sideCards := []game.CardDesc{}

	// Approach 1: Look for downloadable deck text in page scripts or data
	doc.Find("script").Each(func(i int, s *goquery.Selection) {
		scriptContent := s.Text()
		// Look for deck data in JavaScript
		if strings.Contains(scriptContent, "Main Deck") || strings.Contains(scriptContent, "Extra Deck") {
			// Parse from script - this is complex, skip for now
		}
	})

	// Approach 2: Parse from visible card images in sections
	// The page has sections with headers like "Main Deck (40 Card Deck)"
	doc.Find("h4").Each(func(i int, header *goquery.Selection) {
		headerText := strings.TrimSpace(header.Text())

		var targetCards *[]game.CardDesc
		if strings.Contains(headerText, "Main Deck") {
			targetCards = &mainCards
		} else if strings.Contains(headerText, "Extra Deck") {
			targetCards = &extraCards
		} else if strings.Contains(headerText, "Side Deck") {
			targetCards = &sideCards
		} else {
			return
		}

		// Find all card image links after this header
		// Images contain card IDs: /images/cards/{ID}.jpg or as search param
		header.NextUntil("h4, h3, h2").Find("a[href*='?search=']").Each(func(j int, link *goquery.Selection) {
			href, exists := link.Attr("href")
			if !exists {
				return
			}

			// Extract card ID from search parameter
			reSearch := regexp.MustCompile(`\?search=(\d+)`)
			matches := reSearch.FindStringSubmatch(href)
			if len(matches) < 2 {
				return
			}

			cardID := matches[1]

			// Get card name from link title or img alt
			cardName := link.AttrOr("title", "")
			if cardName == "" {
				img := link.Find("img").First()
				cardName = img.AttrOr("alt", "")
			}
			if cardName == "" {
				cardName = "Card_" + cardID
			}

			*targetCards = append(*targetCards, game.CardDesc{
				Name:  cardName,
				Count: 1,
			})
		})
	})

	// Aggregate counts
	mainCards = aggregateCards(mainCards)
	extraCards = aggregateCards(extraCards)
	sideCards = aggregateCards(sideCards)

	if len(mainCards) == 0 {
		return fmt.Errorf("no main deck cards found - page structure may have changed")
	}

	// Build partitions
	partitions := []game.Partition{{
		Name:  "Main Deck",
		Cards: mainCards,
	}}
	if len(extraCards) > 0 {
		partitions = append(partitions, game.Partition{
			Name:  "Extra Deck",
			Cards: extraCards,
		})
	}
	if len(sideCards) > 0 {
		partitions = append(partitions, game.Partition{
			Name:  "Side Deck",
			Cards: sideCards,
		})
	}

	// Determine archetype from deck name or tournament
	archetype := deckName

	// Build collection
	deckType := &game.CollectionTypeDeck{
		Name:      deckName,
		Format:    "TCG", // Default
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
		ReleaseDate: time.Now(),
		Partitions:  partitions,
		Source:      "ygoprodeck-tournament",
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

func aggregateCards(cards []game.CardDesc) []game.CardDesc {
	cardMap := make(map[string]int)
	for _, card := range cards {
		cardMap[card.Name] += card.Count
	}

	result := []game.CardDesc{}
	for name, count := range cardMap {
		result = append(result, game.CardDesc{
			Name:  name,
			Count: count,
		})
	}
	return result
}

var (
	reSilentThrottle = regexp.MustCompile(`rate.?limit|too.?many.?requests`)
	limiter          = ratelimit.New(30, ratelimit.Per(time.Minute))
)

func (d *Dataset) fetch(
	ctx context.Context,
	sc *scraper.Scraper,
	req *http.Request,
	opts dataset.ResolvedUpdateOptions,
) (*scraper.Page, error) {
	return dataset.Do(ctx, sc, &opts, req)
}

var prefix = filepath.Join("yugioh", "ygoprodeck-tournament")

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
