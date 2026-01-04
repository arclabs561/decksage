package riftdecks

import (
	"collections/blob"
	"collections/games"
	"collections/games/riftbound/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"
	"time"
)

// Dataset scrapes Riftbound tournament deck data from riftdecks.com
// This is a basic implementation that can be enhanced as the game matures
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
		Name: "riftdecks",
	}
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	_, err := games.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	d.log.Infof(ctx, "Extracting Riftbound tournament decks from riftdecks.com...")
	d.log.Warnf(ctx, "Riftbound dataset is a placeholder - implement scraping logic as game matures")

	// TODO: Implement scraping from riftdecks.com or riftbound.gg
	// For now, this is a placeholder that can be extended
	// The site structure is: https://riftdecks.com/riftbound-decks
	
	// Placeholder: return nil for now
	// When implementing, follow the pattern:
	// 1. Scrape deck listing pages
	// 2. Extract deck URLs
	// 3. Parse individual deck pages
	// 4. Store as collections

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
	id := fmt.Sprintf("riftdecks:%s:%d", event, placement)
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
		URL:         fmt.Sprintf("https://riftdecks.com/riftbound-decks"),
		ReleaseDate: eventDate,
		Partitions: []game.Partition{{
			Name:  "Deck",
			Cards: cardDescs,
		}},
		Source: "riftdecks",
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

var prefix = filepath.Join("riftbound", "riftdecks")

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

