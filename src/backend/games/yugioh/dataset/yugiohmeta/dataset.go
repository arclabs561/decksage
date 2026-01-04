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

	// Extract tournament type and location from event name
	tournamentType := extractYGOTournamentType(event)
	location := extractYGOLocation(event)
	
	deckType := &game.CollectionTypeDeck{
		Name:           deckName,
		Format:         format,
		Archetype:      archetype,
		Player:         player,
		Event:          event,
		Placement:      placement,
		EventDate:      eventDate,
		TournamentType: tournamentType,
		Location:       location,
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

// extractYGOTournamentType extracts tournament type from event name
func extractYGOTournamentType(eventName string) string {
	if eventName == "" {
		return ""
	}
	
	eventLower := strings.ToLower(eventName)
	
	// Check for common tournament types
	if strings.Contains(eventLower, "ycs") || strings.Contains(eventLower, "yugioh championship series") {
		return "YCS"
	}
	if strings.Contains(eventLower, "wcq") || strings.Contains(eventLower, "world championship qualifier") {
		return "WCQ"
	}
	if strings.Contains(eventLower, "regional") {
		return "Regional"
	}
	if strings.Contains(eventLower, "championship") || strings.Contains(eventLower, "worlds") {
		return "Championship"
	}
	if strings.Contains(eventLower, "local") {
		return "Local"
	}
	if strings.Contains(eventLower, "national") {
		return "National"
	}
	if strings.Contains(eventLower, "continental") {
		return "Continental"
	}
	
	return ""
}

// extractYGOLocation extracts location from event name
// Examples: "YCS Las Vegas", "Regional Pittsburgh, PA"
func extractYGOLocation(eventName string) string {
	if eventName == "" {
		return ""
	}
	
	// Try to find comma-separated location
	parts := strings.Split(eventName, ",")
	if len(parts) >= 2 {
		// Check if last part looks like a state/country (2-3 letters or full country name)
		lastPart := strings.TrimSpace(parts[len(parts)-1])
		if len(lastPart) <= 3 || strings.Contains(strings.ToLower(lastPart), "united states") {
			// Likely a location
			city := strings.TrimSpace(parts[len(parts)-2])
			// Remove tournament type prefix if present
			city = strings.TrimPrefix(city, "YCS")
			city = strings.TrimPrefix(city, "WCQ")
			city = strings.TrimPrefix(city, "Regional")
			city = strings.TrimPrefix(city, "Championship")
			city = strings.TrimSpace(city)
			return fmt.Sprintf("%s, %s", city, lastPart)
		}
	}
	
	// Try to extract city from common patterns like "YCS Las Vegas"
	eventLower := strings.ToLower(eventName)
	if strings.Contains(eventLower, "ycs ") {
		parts := strings.Fields(eventName)
		for i, part := range parts {
			if strings.ToLower(part) == "ycs" && i+1 < len(parts) {
				// Next part might be city
				city := strings.Join(parts[i+1:], " ")
				return city
			}
		}
	}
	
	return ""
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
