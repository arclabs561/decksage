package mtgdecks

import (
	"bytes"
	"collections/blob"
	"collections/games/magic/dataset"
	"collections/games/magic/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/PuerkitoBio/goquery"
)

type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(
	log *logger.Logger,
	blob *blob.Bucket,
) dataset.Dataset {
	return &Dataset{
		log:  log,
		blob: blob,
	}
}

func (d Dataset) Description() dataset.Description {
	return dataset.Description{
		Name: "mtgdecks",
	}
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...dataset.UpdateOption,
) error {
	opts, err := dataset.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	// MTGDecks.net formats
	formats := []string{"Standard", "Modern", "Legacy", "Vintage", "Pioneer", "Pauper", "Commander"}

	var deckURLs []string

	for _, format := range formats {
		d.log.Infof(ctx, "Extracting %s decks from mtgdecks.net", format)

		// Get deck list page
		formatPath := strings.Replace(format, " ", "-", -1)
		listURL := fmt.Sprintf("https://mtgdecks.net/%s", formatPath)

		urls, err := d.extractDeckURLsFromFormat(ctx, sc, listURL, opts)
		if err != nil {
			d.log.Errorf(ctx, "Failed to extract %s deck URLs: %v", format, err)
			continue
		}

		deckURLs = append(deckURLs, urls...)

		if limit, ok := opts.ItemLimit.Get(); ok && len(deckURLs) >= limit {
			deckURLs = deckURLs[:limit]
			break
		}
	}

	d.log.Infof(ctx, "Found %d deck URLs to process", len(deckURLs))

	// Process decks in parallel
	wg := new(sync.WaitGroup)
	queue := make(chan string, len(deckURLs))

	for i := 0; i < opts.Parallel; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for deckURL := range queue {
				if err := d.parseDeck(ctx, sc, deckURL, opts); err != nil {
					d.log.Field("url", deckURL).Errorf(ctx, "Failed to parse deck: %v", err)
					continue
				}
			}
		}()
	}

	for _, u := range deckURLs {
		queue <- u
	}
	close(queue)

	wg.Wait()
	return nil
}

func (d *Dataset) extractDeckURLsFromFormat(
	ctx context.Context,
	sc *scraper.Scraper,
	listURL string,
	opts dataset.ResolvedUpdateOptions,
) ([]string, error) {
	req, err := http.NewRequest("GET", listURL, nil)
	if err != nil {
		return nil, err
	}

	page, err := sc.Do(ctx, req)
	if err != nil {
		return nil, err
	}

	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return nil, err
	}

	var urls []string
	// Find deck links - MTGDecks uses table structure
	doc.Find("table.table-decks tbody tr td a").Each(func(i int, s *goquery.Selection) {
		href, exists := s.Attr("href")
		if !exists {
			return
		}

		// Only process deck detail pages
		if strings.Contains(href, "/decks/") && !strings.Contains(href, "/archetype/") {
			fullURL := "https://mtgdecks.net" + href
			urls = append(urls, fullURL)
		}
	})

	return urls, nil
}

var reDeckID = regexp.MustCompile(`/decks/(\d+)`)

func (d *Dataset) parseDeck(
	ctx context.Context,
	sc *scraper.Scraper,
	deckURL string,
	opts dataset.ResolvedUpdateOptions,
) error {
	// Extract deck ID from URL
	matches := reDeckID.FindStringSubmatch(deckURL)
	if len(matches) < 2 {
		return fmt.Errorf("could not extract deck ID from URL: %s", deckURL)
	}
	deckID := matches[1]

	bkey := d.collectionKey(deckID)

	// Check if already exists
	if !opts.Reparse && !opts.FetchReplaceAll {
		exists, err := d.blob.Exists(ctx, bkey)
		if err != nil {
			return fmt.Errorf("failed to check if collection exists: %w", err)
		}
		if exists {
			d.log.Field("id", deckID).Debugf(ctx, "Deck already exists")
			return nil
		}
	}

	req, err := http.NewRequest("GET", deckURL, nil)
	if err != nil {
		return err
	}

	page, err := sc.Do(ctx, req)
	if err != nil {
		return err
	}

	r := bytes.NewReader(page.Response.Body)
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return err
	}

	// Extract deck metadata
	deckName := strings.TrimSpace(doc.Find("h1.deck-title").Text())
	if deckName == "" {
		return fmt.Errorf("could not find deck name")
	}

	// Extract format and archetype
	format := ""
	archetype := ""
	doc.Find(".deck-info span").Each(func(i int, s *goquery.Selection) {
		text := strings.TrimSpace(s.Text())
		if strings.HasPrefix(text, "Format:") {
			format = strings.TrimSpace(strings.TrimPrefix(text, "Format:"))
		} else if strings.HasPrefix(text, "Archetype:") {
			archetype = strings.TrimSpace(strings.TrimPrefix(text, "Archetype:"))
		}
	})

	// Extract player and event info if available
	player := ""
	event := ""
	placement := 0
	eventDate := ""

	doc.Find(".deck-info .meta span").Each(func(i int, s *goquery.Selection) {
		text := strings.TrimSpace(s.Text())
		if strings.HasPrefix(text, "Player:") {
			player = strings.TrimSpace(strings.TrimPrefix(text, "Player:"))
		} else if strings.HasPrefix(text, "Event:") {
			event = strings.TrimSpace(strings.TrimPrefix(text, "Event:"))
		} else if strings.HasPrefix(text, "Place:") {
			placeStr := strings.TrimSpace(strings.TrimPrefix(text, "Place:"))
			if p, err := strconv.Atoi(strings.TrimSuffix(placeStr, "st")); err == nil {
				placement = p
			} else if p, err := strconv.Atoi(strings.TrimSuffix(placeStr, "nd")); err == nil {
				placement = p
			} else if p, err := strconv.Atoi(strings.TrimSuffix(placeStr, "rd")); err == nil {
				placement = p
			} else if p, err := strconv.Atoi(strings.TrimSuffix(placeStr, "th")); err == nil {
				placement = p
			}
		}
	})

	// Parse main deck and sideboard
	mainDeck := d.parseCardList(doc, ".deck-list-main")
	sideboard := d.parseCardList(doc, ".deck-list-sideboard")

	if len(mainDeck) == 0 {
		return fmt.Errorf("deck has no cards in main deck")
	}

	partitions := []game.Partition{
		{
			Name:  "Main",
			Cards: mainDeck,
		},
	}

	if len(sideboard) > 0 {
		partitions = append(partitions, game.Partition{
			Name:  "Sideboard",
			Cards: sideboard,
		})
	}

	deckType := &game.CollectionTypeDeck{
		Name:      deckName,
		Format:    format,
		Archetype: archetype,
		Player:    player,
		Event:     event,
		Placement: placement,
		EventDate: eventDate,
	}

	collection := game.Collection{
		Type: game.CollectionTypeWrapper{
			Type:  deckType.Type(),
			Inner: deckType,
		},
		ID:          deckID,
		URL:         deckURL,
		ReleaseDate: time.Now(), // Use current time as we don't always have event date
		Partitions:  partitions,
		Source:      "mtgdecks",
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

func (d *Dataset) parseCardList(doc *goquery.Document, selector string) []game.CardDesc {
	var cards []game.CardDesc

	doc.Find(selector + " .card-item").Each(func(i int, s *goquery.Selection) {
		countStr := strings.TrimSpace(s.Find(".card-count").Text())
		cardName := strings.TrimSpace(s.Find(".card-name").Text())

		if cardName == "" {
			return
		}

		count := 1
		if c, err := strconv.Atoi(countStr); err == nil {
			count = c
		}

		cards = append(cards, game.CardDesc{
			Name:  cardName,
			Count: count,
		})
	})

	return cards
}

var basePrefix = filepath.Join("magic", "mtgdecks")
var collectionsPrefix = filepath.Join(basePrefix, "collections")

func (d *Dataset) collectionKey(collectionID string) string {
	return filepath.Join(collectionsPrefix, collectionID+".json")
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(dataset.Item) error,
	options ...dataset.IterItemsOption,
) error {
	de := dataset.DeserializeAsCollection
	return dataset.IterItemsBlobPrefix(ctx, d.blob, collectionsPrefix, de, fn, options...)
}
