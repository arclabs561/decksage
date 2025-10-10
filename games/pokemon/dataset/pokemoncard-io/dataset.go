package pokemoncardio

import (
	"collections/blob"
	"collections/games"
	"collections/logger"
	"collections/scraper"
	"context"
)

// Dataset fetches Pokemon deck data from pokemoncard.io
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
		Game: "pokemon",
		Name: "pokemoncard-io",
	}
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	d.log.Infof(ctx, "Extracting from pokemoncard.io is not yet implemented.")
	// TODO: Implement browser automation scraping logic here.
	return nil
}


