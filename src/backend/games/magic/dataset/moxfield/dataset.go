package moxfield

import (
	"context"
	"collections/blob"
	"collections/games"
	"collections/games/magic/dataset"
	"collections/games/magic/game"
	"collections/logger"
	"collections/scraper"
)

// Dataset scrapes Commander decks from Moxfield
type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) dataset.Dataset {
	return &Dataset{log: log, blob: blob}
}

func (d *Dataset) Description() dataset.Description {
	return dataset.Description{Name: "moxfield"}
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...dataset.UpdateOption,
) error {
	// TODO: Implement Moxfield scraper
	// Moxfield has a public API: https://api.moxfield.com/v2/decks/all
	// Rate limit: Unknown, be polite
	// Format: Commander decks primarily
	d.log.Infof(ctx, "Moxfield scraper not yet implemented")
	return nil
}
