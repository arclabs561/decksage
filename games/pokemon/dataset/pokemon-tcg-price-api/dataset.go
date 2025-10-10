package pokemontcgpriceapi

import (
	"collections/blob"
	"collections/games"
	"collections/logger"
	"collections/scraper"
	"context"
)

// Dataset fetches Pokemon card pricing data from the pokemonpricetracker.com API
// Source: https://www.pokemonpricetracker.com/pokemon-tcg-price-api
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
		Name: "pokemon-tcg-price-api",
	}
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	d.log.Infof(ctx, "Extracting from pokemon-tcg-price-api is not yet implemented.")
	return nil
}


