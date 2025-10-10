package edhrec

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
	"net/url"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"

	"github.com/PuerkitoBio/goquery"
)

var base *url.URL

func init() {
	u, err := url.Parse("https://edhrec.com")
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
) dataset.Dataset {
	return &Dataset{
		log:  log,
		blob: blob,
	}
}

func (d Dataset) Description() dataset.Description {
	return dataset.Description{
		Name: "edhrec",
	}
}

// EDHREC enrichment data structure
type EDHRECCardEnrichment struct {
	CardName      string            `json:"card_name"`
	SaltScore     *float64          `json:"salt_score,omitempty"`     // 0-100, how annoying the card is
	Rank          int               `json:"rank,omitempty"`           // Overall EDH popularity rank
	NumDecks      int               `json:"num_decks,omitempty"`      // Number of decks playing this
	Themes        []string          `json:"themes,omitempty"`         // Associated themes/archetypes
	CommanderInfo *CommanderInfo    `json:"commander_info,omitempty"` // If card is a commander
	Synergies     []CardSynergy     `json:"synergies,omitempty"`      // Cards that synergize well
	RolesByTheme  map[string]string `json:"roles_by_theme,omitempty"` // Role classification per theme
}

type CommanderInfo struct {
	Rank             int      `json:"rank"`
	NumDecks         int      `json:"num_decks"`
	Colors           []string `json:"colors"`
	TopCards         []string `json:"top_cards,omitempty"`          // Top 20 cards in these decks
	Themes           []string `json:"themes,omitempty"`             // Common themes for this commander
	AverageDeckPrice *float64 `json:"average_deck_price,omitempty"` // Average price of decks
}

type CardSynergy struct {
	CardName     string  `json:"card_name"`
	SynergyScore float64 `json:"synergy_score"` // How well they work together
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

	// EDHREC provides several useful data sources:
	// 1. Top commanders list - for commander-specific enrichment
	// 2. Top cards list - for role/theme classification
	// 3. Salt score list - for feel-bad cards
	// 4. Theme pages - for theme/archetype analysis

	d.log.Infof(ctx, "Extracting EDHREC enrichment data...")

	// Extract top commanders
	if err := d.extractTopCommanders(ctx, sc, opts); err != nil {
		d.log.Errorf(ctx, "Failed to extract top commanders: %v", err)
	}

	// Extract salt scores
	if err := d.extractSaltScores(ctx, sc, opts); err != nil {
		d.log.Errorf(ctx, "Failed to extract salt scores: %v", err)
	}

	// Extract top cards with themes
	if err := d.extractTopCards(ctx, sc, opts); err != nil {
		d.log.Errorf(ctx, "Failed to extract top cards: %v", err)
	}

	return nil
}

func (d *Dataset) extractTopCommanders(
	ctx context.Context,
	sc *scraper.Scraper,
	opts dataset.ResolvedUpdateOptions,
) error {
	d.log.Infof(ctx, "Extracting top commanders from EDHREC...")

	req, err := http.NewRequest("GET", "https://edhrec.com/commanders", nil)
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

	// EDHREC lists commanders in cards with rankings
	var commanderURLs []string
	doc.Find(".card-header a, .card-list a").Each(func(i int, s *goquery.Selection) {
		href, exists := s.Attr("href")
		if !exists {
			return
		}

		// Commander detail pages are like /commanders/atraxa-praetors-voice
		if strings.Contains(href, "/commanders/") && !strings.Contains(href, "?") {
			fullURL := "https://edhrec.com" + href
			commanderURLs = append(commanderURLs, fullURL)
		}
	})

	d.log.Infof(ctx, "Found %d commanders to process", len(commanderURLs))

	// Limit if requested
	if limit, ok := opts.ItemLimit.Get(); ok && len(commanderURLs) > limit {
		commanderURLs = commanderURLs[:limit]
	}

	// Process commanders in parallel
	wg := new(sync.WaitGroup)
	queue := make(chan string, len(commanderURLs))

	for i := 0; i < opts.Parallel; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for commanderURL := range queue {
				if err := d.parseCommanderPage(ctx, sc, commanderURL, opts); err != nil {
					d.log.Field("url", commanderURL).Errorf(ctx, "Failed to parse commander: %v", err)
					continue
				}
			}
		}()
	}

	for _, u := range commanderURLs {
		queue <- u
	}
	close(queue)

	wg.Wait()
	return nil
}

func (d *Dataset) parseCommanderPage(
	ctx context.Context,
	sc *scraper.Scraper,
	commanderURL string,
	opts dataset.ResolvedUpdateOptions,
) error {
	// Extract commander name from URL
	parts := strings.Split(commanderURL, "/")
	commanderSlug := parts[len(parts)-1]

	bkey := d.enrichmentKey(commanderSlug)

	// Check if already exists
	if !opts.Reparse {
		exists, err := d.blob.Exists(ctx, bkey)
		if err != nil {
			return fmt.Errorf("failed to check if enrichment exists: %w", err)
		}
		if exists {
			d.log.Field("slug", commanderSlug).Debugf(ctx, "Commander enrichment already exists")
			return nil
		}
	}

	req, err := http.NewRequest("GET", commanderURL, nil)
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

	// Extract commander name
	commanderName := strings.TrimSpace(doc.Find("h1.commander-name, h1").First().Text())
	if commanderName == "" {
		return fmt.Errorf("could not find commander name")
	}

	// Extract deck count and rank
	numDecks := 0
	rank := 0
	doc.Find(".commander-stats span, .stats span").Each(func(i int, s *goquery.Selection) {
		text := strings.TrimSpace(s.Text())
		if strings.Contains(text, "decks") {
			// Parse "1,234 decks"
			numStr := strings.TrimSuffix(strings.TrimSpace(strings.Split(text, "decks")[0]), ",")
			numStr = strings.ReplaceAll(numStr, ",", "")
			if n, err := strconv.Atoi(numStr); err == nil {
				numDecks = n
			}
		}
		if strings.Contains(text, "#") {
			// Parse "#42"
			rankStr := strings.TrimPrefix(text, "#")
			if r, err := strconv.Atoi(rankStr); err == nil {
				rank = r
			}
		}
	})

	// Extract top cards
	topCards := []string{}
	doc.Find(".card-list-item a, .top-cards a").Each(func(i int, s *goquery.Selection) {
		cardName := strings.TrimSpace(s.Text())
		if cardName != "" && len(topCards) < 50 {
			topCards = append(topCards, cardName)
		}
	})

	// Extract themes
	themes := []string{}
	doc.Find(".themes a, .theme-tag").Each(func(i int, s *goquery.Selection) {
		theme := strings.TrimSpace(s.Text())
		if theme != "" {
			themes = append(themes, theme)
		}
	})

	// Build enrichment data
	enrichment := EDHRECCardEnrichment{
		CardName: commanderName,
		Rank:     rank,
		NumDecks: numDecks,
		Themes:   themes,
		CommanderInfo: &CommanderInfo{
			Rank:     rank,
			NumDecks: numDecks,
			TopCards: topCards,
			Themes:   themes,
		},
	}

	b, err := json.Marshal(enrichment)
	if err != nil {
		return err
	}

	return d.blob.Write(ctx, bkey, b)
}

func (d *Dataset) extractSaltScores(
	ctx context.Context,
	sc *scraper.Scraper,
	opts dataset.ResolvedUpdateOptions,
) error {
	d.log.Infof(ctx, "Extracting salt scores from EDHREC...")

	req, err := http.NewRequest("GET", "https://edhrec.com/top/salt", nil)
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

	// Parse salt score table
	doc.Find("table tr, .salt-list-item").Each(func(i int, s *goquery.Selection) {
		cardName := strings.TrimSpace(s.Find(".card-name, td:nth-child(2)").Text())
		saltStr := strings.TrimSpace(s.Find(".salt-score, td:nth-child(3)").Text())

		if cardName == "" || saltStr == "" {
			return
		}

		// Parse salt score (format: "2.45" or "85%")
		saltStr = strings.TrimSuffix(saltStr, "%")
		var saltScore float64
		if _, err := fmt.Sscanf(saltStr, "%f", &saltScore); err != nil {
			return
		}

		// Store enrichment
		enrichment := EDHRECCardEnrichment{
			CardName:  cardName,
			SaltScore: &saltScore,
		}

		slug := strings.ToLower(strings.ReplaceAll(cardName, " ", "-"))
		slug = regexp.MustCompile(`[^a-z0-9-]`).ReplaceAllString(slug, "")
		bkey := d.enrichmentKey("salt-" + slug)

		b, _ := json.Marshal(enrichment)
		d.blob.Write(ctx, bkey, b)
	})

	return nil
}

func (d *Dataset) extractTopCards(
	ctx context.Context,
	sc *scraper.Scraper,
	opts dataset.ResolvedUpdateOptions,
) error {
	d.log.Infof(ctx, "Extracting top cards from EDHREC...")

	req, err := http.NewRequest("GET", "https://edhrec.com/top", nil)
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

	// Parse top cards with their play rates
	doc.Find(".card-list-item, table tr").Each(func(i int, s *goquery.Selection) {
		cardName := strings.TrimSpace(s.Find(".card-name, td:nth-child(2)").Text())
		decksStr := strings.TrimSpace(s.Find(".num-decks, td:nth-child(3)").Text())

		if cardName == "" {
			return
		}

		// Parse deck count
		numDecks := 0
		decksStr = strings.ReplaceAll(decksStr, ",", "")
		if n, err := strconv.Atoi(strings.Fields(decksStr)[0]); err == nil {
			numDecks = n
		}

		enrichment := EDHRECCardEnrichment{
			CardName: cardName,
			NumDecks: numDecks,
			Rank:     i + 1,
		}

		slug := strings.ToLower(strings.ReplaceAll(cardName, " ", "-"))
		slug = regexp.MustCompile(`[^a-z0-9-]`).ReplaceAllString(slug, "")
		bkey := d.enrichmentKey("top-" + slug)

		b, _ := json.Marshal(enrichment)
		d.blob.Write(ctx, bkey, b)
	})

	return nil
}

var basePrefix = filepath.Join("magic", "edhrec")
var enrichmentPrefix = filepath.Join(basePrefix, "enrichment")

func (d *Dataset) enrichmentKey(slug string) string {
	return filepath.Join(enrichmentPrefix, slug+".json")
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(dataset.Item) error,
	options ...dataset.IterItemsOption,
) error {
	de := func(key string, data []byte) (dataset.Item, error) {
		var enrichment EDHRECCardEnrichment
		if err := json.Unmarshal(data, &enrichment); err != nil {
			return nil, fmt.Errorf("failed to unmarshal enrichment: %w", err)
		}
		// Return as a card item
		return &dataset.CardItem{
			Card: &game.Card{
				Name: enrichment.CardName,
			},
		}, nil
	}
	return dataset.IterItemsBlobPrefix(ctx, d.blob, enrichmentPrefix, de, fn, options...)
}
