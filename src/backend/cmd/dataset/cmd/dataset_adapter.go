package cmd

import (
	"context"
	"encoding/json"

	"collections/games"
	magicdataset "collections/games/magic/dataset"
	"collections/scraper"
)

// Adapter to make MTG datasets compatible with games.Dataset interface
type mtgDatasetAdapter struct {
	inner magicdataset.Dataset
}

func (a *mtgDatasetAdapter) Description() games.Description {
	desc := a.inner.Description()
	return games.Description{
		Game: "magic",
		Name: desc.Name,
	}
}

func (a *mtgDatasetAdapter) Extract(
	ctx context.Context,
	sc *scraper.Scraper,
	options ...games.UpdateOption,
) error {
	// Convert games.UpdateOption to magicdataset.UpdateOption
	magicOpts := make([]magicdataset.UpdateOption, 0, len(options))
	for _, opt := range options {
		switch opt := opt.(type) {
		case *games.OptExtractReparse:
			magicOpts = append(magicOpts, &magicdataset.OptExtractReparse{})
		case *games.OptExtractScraperReplaceAll:
			magicOpts = append(magicOpts, &magicdataset.OptExtractScraperReplaceAll{})
		case *games.OptExtractScraperSkipMissing:
			magicOpts = append(magicOpts, &magicdataset.OptExtractScraperSkipMissing{})
		case *games.OptExtractScraperCache:
			magicOpts = append(magicOpts, &magicdataset.OptExtractScraperCache{})
		case *games.OptExtractParallel:
			magicOpts = append(magicOpts, &magicdataset.OptExtractParallel{Parallel: opt.Parallel})
		case *games.OptExtractSectionOnly:
			magicOpts = append(magicOpts, &magicdataset.OptExtractSectionOnly{Section: opt.Section})
		case *games.OptExtractScrollLimit:
			magicOpts = append(magicOpts, &magicdataset.OptExtractScrollLimit{Limit: opt.Limit})
		case *games.OptExtractScrollStart:
			magicOpts = append(magicOpts, &magicdataset.OptExtractScrollStart{Start: opt.Start})
		case *games.OptExtractItemLimit:
			magicOpts = append(magicOpts, &magicdataset.OptExtractItemLimit{Limit: opt.Limit})
		case *games.OptExtractItemOnlyURL:
			magicOpts = append(magicOpts, &magicdataset.OptExtractItemOnlyURL{URL: opt.URL})
		case *games.OptExtractItemCat:
			magicOpts = append(magicOpts, &magicdataset.OptExtractItemCat{})
		}
	}
	return a.inner.Extract(ctx, sc, magicOpts...)
}

func (a *mtgDatasetAdapter) IterItems(
	ctx context.Context,
	fn func(item games.Item) error,
	options ...games.IterItemsOption,
) error {
	// Convert games.IterItemsOption to magicdataset.IterItemsOption
	magicOpts := make([]magicdataset.IterItemsOption, 0, len(options))
	for _, opt := range options {
		switch opt := opt.(type) {
		case *games.OptIterItemsParallel:
			magicOpts = append(magicOpts, &magicdataset.OptIterItemsParallel{Parallel: opt.Parallel})
		// Skip OptIterItemsFilterType as it's complex to convert
		}
	}

	// Convert the callback function
	magicFn := func(item magicdataset.Item) error {
		// Convert magicdataset.Item to games.Item
		switch item := item.(type) {
		case *magicdataset.CollectionItem:
			// Convert magic/game.Collection to games.Collection
			// They have the same structure, so we can marshal/unmarshal
			data, err := json.Marshal(item.Collection)
			if err != nil {
				return err
			}
			var universalCol games.Collection
			if err := json.Unmarshal(data, &universalCol); err != nil {
				return err
			}
			return fn(&games.CollectionItem{Collection: &universalCol})
		case *magicdataset.CardItem:
			// For card items, we'd need game-specific handling
			// For now, skip card items in iteration (extract doesn't use IterItems anyway)
			return nil
		default:
			return nil
		}
	}

	return a.inner.IterItems(ctx, magicFn, magicOpts...)
}

// wrapMTGDataset wraps a magic dataset to implement games.Dataset
func wrapMTGDataset(d magicdataset.Dataset) games.Dataset {
	return &mtgDatasetAdapter{inner: d}
}

