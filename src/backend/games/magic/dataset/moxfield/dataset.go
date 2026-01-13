package moxfield

import (
	"context"
	"path/filepath"

	"collections/blob"
	"collections/games/magic/dataset"
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

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(dataset.Item) error,
	options ...dataset.IterItemsOption,
) error {
	prefix := filepath.Join("magic", "moxfield", "collections")
	return dataset.IterItemsBlobPrefix(ctx, d.blob, prefix, dataset.DeserializeAsCollection, fn, options...)
}
