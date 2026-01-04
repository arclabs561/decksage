package lands17

import (
	"context"
	"collections/blob"
	"collections/games"
	"collections/games/magic/dataset"
	"collections/logger"
	"collections/scraper"
)

// Dataset scrapes Limited format data from 17Lands
type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) dataset.Dataset {
	return &Dataset{log: log, blob: blob}
}

func (d *Dataset) Description() dataset.Description {
	return dataset.Description{Name: "17lands"}
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...dataset.UpdateOption,
) error {
	// TODO: Implement 17Lands scraper
	// 17Lands has data exports: https://www.17lands.com/data
	// Format: Limited (Draft/Sealed) format data
	// Unique: Draft pick orders, win rates, synergy data
	d.log.Infof(ctx, "17Lands scraper not yet implemented")
	return nil
}
