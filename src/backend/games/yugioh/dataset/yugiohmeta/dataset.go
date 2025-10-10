package yugiohmeta

import (
	"bytes"
	"collections/blob"
	"collections/games"
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
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
)

var base *url.URL

func init() {
	u, err := url.Parse("https://www.yugiohmeta.com")
	if err != nil {
		panic(err)
	}
	base = u
}

type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(
	log *logger.Logger,
	blob *blob.Bucket,
) *Dataset {
	return &Dataset{
		log:  log,
		blob: blob,
	}
}

func (d *Dataset) Description() games.Description {
	return games.Description{
		Game: "yugioh",
		Name: "yugiohmeta",
	}
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	// Temporary guard: yugiohmeta has changed site structure; scraper blocked pending maintenance
	return fmt.Errorf("yugiohmeta dataset is currently disabled: site structure changed (404s). Use ygoprodeck-tournament instead.")
}

func (d *Dataset) extractTournamentURLs(
	ctx context.Context,
	sc *scraper.Scraper,
	opts games.ResolvedUpdateOptions,
) ([]string, error) {
	req, err := http.NewRequest("GET", "https://www.yugiohmeta.com/tournaments", nil)
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
	doc.Find(".tournament-list a.tournament-link").Each(func(i int, s *goquery.Selection) {
		href, exists := s.Attr("href")
		if !exists {
			return
		}

		if !strings.HasPrefix(href, "http") {
			href = "https://www.yugiohmeta.com" + href
		}
		urls = append(urls, href)
	})

	// Limit number of tournaments to process
	if limit, ok := opts.ItemLimit.Get(); ok && len(urls) > limit/10 {
		// Assume ~10 decks per tournament
		urls = urls[:limit/10]
	}

	return urls, nil
}

func (d *Dataset) extractDecksFromTournament(
	ctx context.Context,
	sc *scraper.Scraper,
	tournamentURL string,
	opts games.ResolvedUpdateOptions,
) ([]string, error) {
	req, err := http.NewRequest("GET", tournamentURL, nil)
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
	doc.Find(".deck-list a.deck-link, table.standings a").Each(func(i int, s *goquery.Selection) {
		href, exists := s.Attr("href")
		if !exists {
			return
		}

		// Only process deck detail pages
		if strings.Contains(href, "/deck/") || strings.Contains(href, "/decklist/") {
			if !strings.HasPrefix(href, "http") {
				href = "https://www.yugiohmeta.com" + href
			}
			urls = append(urls, href)
		}
	})

	return urls, nil
}

var reDeckID = regexp.MustCompile(`/deck[list]*[s]*/([^/]+)`)

func (d *Dataset) parseDeck(
	ctx context.Context,
	sc *scraper.Scraper,
	deckURL string,
	opts games.ResolvedUpdateOptions,
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
	deckName := strings.TrimSpace(doc.Find("h1.deck-title, h2.deck-name").Text())
	if deckName == "" {
		deckName = "Unnamed Deck"
	}

	// Extract format and archetype
	format := "TCG"
	archetype := ""
	doc.Find(".deck-meta span, .deck-info span").Each(func(i int, s *goquery.Selection) {
		text := strings.TrimSpace(s.Text())
		if strings.HasPrefix(text, "Format:") {
			format = strings.TrimSpace(strings.TrimPrefix(text, "Format:"))
		} else if strings.HasPrefix(text, "Archetype:") || strings.HasPrefix(text, "Deck:") {
			archetype = strings.TrimSpace(strings.TrimPrefix(strings.TrimPrefix(text, "Archetype:"), "Deck:"))
		}
	})

	// Extract player and event info
	player := ""
	event := ""
	placement := ""
	eventDate := ""

	doc.Find(".player-info, .tournament-info").Each(func(i int, s *goquery.Selection) {
		text := strings.TrimSpace(s.Text())
		if strings.Contains(text, "Player:") {
			player = strings.TrimSpace(strings.Split(text, "Player:")[1])
		} else if strings.Contains(text, "Event:") {
			event = strings.TrimSpace(strings.Split(text, "Event:")[1])
		} else if strings.Contains(text, "Place:") || strings.Contains(text, "Placement:") {
			placement = strings.TrimSpace(strings.Split(text, ":")[1])
		}
	})

	// Parse main deck, extra deck, and side deck
	mainDeck := d.parseCardList(doc, ".main-deck, .deck-main")
	extraDeck := d.parseCardList(doc, ".extra-deck, .deck-extra")
	sideDeck := d.parseCardList(doc, ".side-deck, .deck-side")

	if len(mainDeck) == 0 {
		return fmt.Errorf("deck has no cards in main deck")
	}

	partitions := []game.Partition{
		{
			Name:  "Main Deck",
			Cards: mainDeck,
		},
	}

	if len(extraDeck) > 0 {
		partitions = append(partitions, game.Partition{
			Name:  "Extra Deck",
			Cards: extraDeck,
		})
	}

	if len(sideDeck) > 0 {
		partitions = append(partitions, game.Partition{
			Name:  "Side Deck",
			Cards: sideDeck,
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
		ReleaseDate: time.Now(),
		Partitions:  partitions,
		Source:      "yugiohmeta",
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

	doc.Find(selector + " .card-item, " + selector + " li").Each(func(i int, s *goquery.Selection) {
		text := strings.TrimSpace(s.Text())
		if text == "" {
			return
		}

		// Format is typically "3x Card Name" or "Card Name x3"
		var count int
		var cardName string

		if strings.Contains(text, "x") {
			parts := strings.Split(text, "x")
			if len(parts) == 2 {
				// Try parsing first part as count
				if c, err := strconv.Atoi(strings.TrimSpace(parts[0])); err == nil {
					count = c
					cardName = strings.TrimSpace(parts[1])
				} else if c, err := strconv.Atoi(strings.TrimSpace(parts[1])); err == nil {
					count = c
					cardName = strings.TrimSpace(parts[0])
				}
			}
		}

		if cardName == "" {
			cardName = text
			count = 1
		}

		// Try to find count and name in separate elements
		countElem := s.Find(".card-count, .count")
		if countElem.Length() > 0 {
			if c, err := strconv.Atoi(strings.TrimSpace(countElem.Text())); err == nil {
				count = c
			}
		}

		nameElem := s.Find(".card-name, .name")
		if nameElem.Length() > 0 {
			cardName = strings.TrimSpace(nameElem.Text())
		}

		if cardName != "" && count > 0 {
			cards = append(cards, game.CardDesc{
				Name:  cardName,
				Count: count,
			})
		}
	})

	return cards
}

var basePrefix = filepath.Join("yugioh", "yugiohmeta")
var collectionsPrefix = filepath.Join(basePrefix, "collections")

func (d *Dataset) collectionKey(collectionID string) string {
	return filepath.Join(collectionsPrefix, collectionID+".json")
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(games.Item) error,
	options ...games.IterItemsOption,
) error {
	prefix := collectionsPrefix
	de := func(key string, data []byte) (games.Item, error) {
		var col game.Collection
		if err := json.Unmarshal(data, &col); err != nil {
			return nil, fmt.Errorf("failed to unmarshal collection: %w", err)
		}
		return &games.CollectionItem{
			Collection: &col,
		}, nil
	}
	return games.IterItemsBlobPrefix(ctx, d.blob, prefix, de, fn, options...)
}
