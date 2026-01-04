package riftcodex

import (
	"collections/blob"
	"collections/games"
	"collections/games/riftbound/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
)

// Dataset scrapes Riftbound card data from Riftcodex API
// Free community API: https://api.riftcodex.com
// Documentation: https://riftcodex.com/docs/category/riftcodex-api
// No API key required
type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) *Dataset {
	return &Dataset{
		log:  log,
		blob: blob,
	}
}

func (d *Dataset) Description() games.Description {
	return games.Description{
		Game: "riftbound",
		Name: "riftcodex",
	}
}

// API Response structures based on https://riftcodex.com/blog
type riftcodexResponse struct {
	Items []riftcodexCard `json:"items"`
	Total int             `json:"total"`
	Page  int             `json:"page"`
	Size  int             `json:"size"`
	Pages int             `json:"pages"`
}

type riftcodexCard struct {
	ID             string              `json:"id"`
	Name           string              `json:"name"`
	RiftboundID    string              `json:"riftbound_id"`
	TCGPlayerID    string              `json:"tcgplayer_id"`
	PublicCode     string              `json:"public_code"`
	CollectorNumber int               `json:"collector_number"`
	Attributes     riftcodexAttributes `json:"attributes"`
	Classification riftcodexClassification `json:"classification"`
	Text           riftcodexText       `json:"text"`
	Set            riftcodexSet        `json:"set"`
	Media          riftcodexMedia      `json:"media"`
	Tags           []string            `json:"tags"`
	Orientation    string              `json:"orientation"`
	Metadata       riftcodexMetadata   `json:"metadata"`
}

type riftcodexAttributes struct {
	Energy *int `json:"energy"`
	Might  *int `json:"might"`
	Power  *int `json:"power"`
}

type riftcodexClassification struct {
	Type     string   `json:"type"`      // Unit, Spell, Gear, Legend, etc.
	Supertype *string `json:"supertype"` // Champion, Signature, etc.
	Rarity   string   `json:"rarity"`     // Common, Uncommon, Rare, Epic, Legendary
	Domain   []string `json:"domain"`     // Body, Calm, Chaos, Fury, Mind, Order
}

type riftcodexText struct {
	Rich  string `json:"rich"`  // HTML formatted
	Plain string `json:"plain"` // Plain text
}

type riftcodexSet struct {
	SetID string `json:"set_id"` // OGN, SFD, etc.
	Label string `json:"label"`  // "Origins", "Spiritforged", etc.
}

type riftcodexMedia struct {
	ImageURL         string `json:"image_url"`
	Artist           string `json:"artist"`
	AccessibilityText string `json:"accessibility_text"`
}

type riftcodexMetadata struct {
	CleanName     string `json:"clean_name"`
	AlternateArt  bool   `json:"alternate_art"`
	Overnumbered  bool   `json:"overnumbered"`
	Signature     bool   `json:"signature"`
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	opts, err := games.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	d.log.Infof(ctx, "Extracting Riftbound cards from Riftcodex API (https://api.riftcodex.com)...")

	// Fetch all cards with pagination
	page := 1
	size := 50 // API default, can be up to 100
	totalProcessed := atomic.Int64{}
	var wg sync.WaitGroup
	cardChan := make(chan riftcodexCard, 100)

	// Worker pool to process cards
	for i := 0; i < opts.Parallel; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for rawCard := range cardChan {
				if limit, ok := opts.ItemLimit.Get(); ok && int(totalProcessed.Load()) >= limit {
					return
				}

				if err := d.parseCard(ctx, rawCard); err != nil {
					d.log.Field("card", rawCard.Name).Errorf(ctx, "Failed to parse card: %v", err)
					if stats := games.ExtractStatsFromContext(ctx); stats != nil {
						stats.RecordCategorizedError(ctx, rawCard.ID, "riftcodex", err)
					}
					continue
				}

				totalProcessed.Add(1)
				if stats := games.ExtractStatsFromContext(ctx); stats != nil {
					stats.RecordSuccess()
				}

				if totalProcessed.Load()%50 == 0 {
					d.log.Infof(ctx, "Processed %d cards...", totalProcessed.Load())
				}
			}
		}()
	}

	// Fetch pages
	for {
		// Check context cancellation
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		if limit, ok := opts.ItemLimit.Get(); ok && int(totalProcessed.Load()) >= limit {
			break
		}

		url := fmt.Sprintf("https://api.riftcodex.com/cards?page=%d&size=%d", page, size)
		req, err := http.NewRequest("GET", url, nil)
		if err != nil {
			return fmt.Errorf("failed to create request: %w", err)
		}

		req.Header.Set("Accept", "application/json")
		req.Header.Set("User-Agent", "DeckSage/1.0")

		resp, err := sc.Do(ctx, req)
		if err != nil {
			return fmt.Errorf("failed to fetch page %d: %w", page, err)
		}

		var apiResp riftcodexResponse
		if err := json.Unmarshal(resp.Response.Body, &apiResp); err != nil {
			return fmt.Errorf("failed to parse API response for page %d: %w", page, err)
		}

		if len(apiResp.Items) == 0 {
			d.log.Infof(ctx, "No more cards on page %d, stopping", page)
			break
		}

		d.log.Infof(ctx, "Fetched page %d/%d: %d cards (total: %d)", page, apiResp.Pages, len(apiResp.Items), apiResp.Total)

		// Send cards to workers
		for _, card := range apiResp.Items {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case cardChan <- card:
			}
		}

		if page >= apiResp.Pages {
			break
		}
		page++
	}

	close(cardChan)
	wg.Wait()

	d.log.Infof(ctx, "✅ Extracted %d Riftbound cards from Riftcodex API", totalProcessed.Load())
	return nil
}

func (d *Dataset) parseCard(
	ctx context.Context,
	rawCard riftcodexCard,
) error {
	// Map Riftcodex fields to Riftbound Card structure
	card := &game.Card{
		Name: rawCard.Name,
		Type: rawCard.Classification.Type,
		Set:  rawCard.Set.SetID,
		SetName: rawCard.Set.Label,
		Rarity: rawCard.Classification.Rarity,
		CardNumber: strconv.Itoa(rawCard.CollectorNumber),
		Domain: rawCard.Classification.Domain,
		Effect: rawCard.Text.Plain, // Use plain text for effect
	}

	// Map attributes
	if rawCard.Attributes.Energy != nil {
		card.Cost = *rawCard.Attributes.Energy
	}
	if rawCard.Attributes.Might != nil {
		card.Power = *rawCard.Attributes.Might
	}
	if rawCard.Attributes.Power != nil {
		card.Health = *rawCard.Attributes.Power
	}

	// Handle Champion type
	if rawCard.Classification.Supertype != nil && *rawCard.Classification.Supertype == "Champion" {
		// Extract champion name from tags or name
		championName := rawCard.Name
		if len(rawCard.Tags) > 0 {
			// Tags often contain champion names
			for _, tag := range rawCard.Tags {
				// Check if tag is a known champion name (simplified - could be enhanced)
				championName = tag
				break
			}
		}
		card.Champion = championName
	}

	// Add image
	if rawCard.Media.ImageURL != "" {
		card.Images = []game.CardImage{
			{URL: rawCard.Media.ImageURL},
		}
	}

	// Add reference
	card.References = []game.CardRef{
		{URL: fmt.Sprintf("https://riftcodex.com/cards/%s", rawCard.RiftboundID)},
	}

	// Extract keywords from text (simplified - could parse more thoroughly)
	// Keywords like [Shield], [Tank], [Quick Attack] are in the text
	// This is a basic implementation - could be enhanced with proper keyword extraction

	bkey := d.cardKey(card.Name)
	b, err := json.Marshal(card)
	if err != nil {
		return fmt.Errorf("failed to marshal card %q: %w", card.Name, err)
	}

	if err := d.blob.Write(ctx, bkey, b); err != nil {
		return fmt.Errorf("failed to write card %q: %w", card.Name, err)
	}

	return nil
}

var prefix = filepath.Join("riftbound", "riftcodex")

func (d *Dataset) cardKey(cardName string) string {
	// Sanitize card name for file path (similar to Scryfall pattern)
	// Replace problematic characters with underscores
	safeName := strings.ReplaceAll(cardName, "/", "_")
	safeName = strings.ReplaceAll(safeName, "\\", "_")
	safeName = strings.ReplaceAll(safeName, ":", "_")
	safeName = strings.ReplaceAll(safeName, "*", "_")
	safeName = strings.ReplaceAll(safeName, "?", "_")
	safeName = strings.ReplaceAll(safeName, "\"", "_")
	safeName = strings.ReplaceAll(safeName, "<", "_")
	safeName = strings.ReplaceAll(safeName, ">", "_")
	safeName = strings.ReplaceAll(safeName, "|", "_")
	safeName = filepath.Clean(safeName)
	return filepath.Join(prefix, safeName+".json")
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(item games.Item) error,
	options ...games.IterItemsOption,
) error {
	// TODO: Implement card iteration
	// For now, this is a placeholder - cards are stored but iteration needs game-specific CardItem
	// Could iterate collections instead or implement game-specific Item wrapper
	d.log.Warnf(ctx, "IterItems not yet implemented for Riftcodex - cards are stored but iteration needs CardItem wrapper")
	return nil
}
