package pokemontcgpriceapi

import (
	"collections/blob"
	"collections/games"
	"collections/games/pokemon/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go.uber.org/ratelimit"
)

// Dataset enriches Pokemon cards with price data from external APIs.
// Primary provider: PokemonTCG.io (v2) using card IDs (e.g., sv1-1)
// Falls back gracefully when API is unavailable.
type Dataset struct {
	log  *logger.Logger
	blob *blob.Bucket
}

func NewDataset(log *logger.Logger, blob *blob.Bucket) *Dataset {
	return &Dataset{log: log, blob: blob}
}

func (d *Dataset) Description() games.Description {
	return games.Description{Game: "pokemon", Name: "pokemon-tcg-price-api"}
}

// Minimal structure of PokemonTCG.io response for pricing
type tcgIoCard struct {
	Data struct {
		TCGPlayer struct {
			Prices map[string]struct {
				Low    *float64 `json:"low"`
				Mid    *float64 `json:"mid"`
				High   *float64 `json:"high"`
				Market *float64 `json:"market"`
			} `json:"prices"`
		} `json:"tcgplayer"`
		Cardmarket struct {
			Prices struct {
				AverageSellPrice *float64 `json:"averageSellPrice"`
				TrendPrice       *float64 `json:"trendPrice"`
			} `json:"prices"`
		} `json:"cardmarket"`
	} `json:"data"`
}

type priceRecord struct {
	ID      string          `json:"id"`
	Prices  game.CardPrices `json:"prices"`
	Source  string          `json:"source"`
	Version int             `json:"version"`
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

	// Iterate over existing Pokemon card IDs from pokemontcg-data
	cardsPrefix := filepath.Join("pokemon", "pokemontcg-data", "cards") + "/"

	it := d.blob.List(ctx, &blob.OptListPrefix{Prefix: cardsPrefix})

	// Rate limit outbound API calls (be nice to providers)
	limiter := ratelimit.New(120, ratelimit.Per(time.Minute)) // 2 rps
	processed := 0
	for it.Next(ctx) {
		key := it.Key() // e.g., pokemon/pokemontcg-data/cards/sv1-1.json
		if filepath.Ext(key) != ".json" {
			continue
		}

		// Respect item limit
		if limit, ok := opts.ItemLimit.Get(); ok && processed >= limit {
			d.log.Infof(ctx, "Reached item limit of %d", limit)
			break
		}

		id := strings.TrimSuffix(filepath.Base(key), ".json")
		limiter.Take()
		rec, err := d.fetchPricesFromTCGIO(ctx, sc, id)
		if err != nil {
			d.log.Field("id", id).Warnf(ctx, "price fetch failed, skipping: %v", err)
			continue
		}

		out := priceRecord{
			ID:      id,
			Prices:  rec,
			Source:  "pokemontcg.io",
			Version: 1,
		}

		b, err := json.Marshal(out)
		if err != nil {
			d.log.Field("id", id).Warnf(ctx, "marshal price record failed: %v", err)
			continue
		}

		outKey := filepath.Join("pokemon", "pokemon-tcg-price-api", "cards", id+".json")
		if err := d.blob.Write(ctx, outKey, b); err != nil {
			d.log.Field("key", outKey).Warnf(ctx, "failed to write price record: %v", err)
			continue
		}

		processed++
		if (processed % 250) == 0 {
			d.log.Field("processed", fmt.Sprintf("%d", processed)).Infof(ctx, "price enrichment progress")
		}
	}
	if err := it.Err(); err != nil {
		return err
	}

	d.log.Field("count", fmt.Sprintf("%d", processed)).Infof(ctx, "pokemon prices written")
	return nil
}

func (d *Dataset) fetchPricesFromTCGIO(
	ctx context.Context,
	sc *scraper.Scraper,
	id string,
) (game.CardPrices, error) {
	// Prefer RapidAPI if configured, else direct API
	var url string
	useRapid := os.Getenv("RAPIDAPI_KEY") != ""
	if useRapid {
		// RapidAPI proxy host for PokemonTCG (common pattern)
		url = fmt.Sprintf("https://pokemon-tcg-api.p.rapidapi.com/v2/cards/%s", id)
	} else {
		url = fmt.Sprintf("https://api.pokemontcg.io/v2/cards/%s", id)
	}

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return game.CardPrices{}, err
	}
	if useRapid {
		req.Header.Set("X-RapidAPI-Key", os.Getenv("RAPIDAPI_KEY"))
		req.Header.Set("X-RapidAPI-Host", "pokemon-tcg-api.p.rapidapi.com")
	} else if apiKey := os.Getenv("POKEMONTCG_API_KEY"); apiKey != "" {
		req.Header.Set("X-Api-Key", apiKey)
	}

	page, err := games.Do(ctx, sc, &games.ResolvedUpdateOptions{}, req)
	if err != nil {
		return game.CardPrices{}, err
	}

	var resp tcgIoCard
	if err := json.Unmarshal(page.Response.Body, &resp); err != nil {
		return game.CardPrices{}, err
	}

	// Select a representative TCGPlayer price bucket
	var pick struct{ Low, Mid, High, Market *float64 }
	order := []string{"holofoil", "reverseHolofoil", "normal"}
	for _, k := range order {
		if p, ok := resp.Data.TCGPlayer.Prices[k]; ok {
			pick.Low = coalesce(pick.Low, p.Low)
			pick.Mid = coalesce(pick.Mid, p.Mid)
			pick.High = coalesce(pick.High, p.High)
			pick.Market = coalesce(pick.Market, p.Market)
		}
	}

	prices := game.CardPrices{}
	prices.TCGPlayerLow = pick.Low
	prices.TCGPlayerMid = pick.Mid
	prices.TCGPlayerHigh = pick.High
	prices.TCGPlayer = pick.Market

	if v := resp.Data.Cardmarket.Prices.AverageSellPrice; v != nil {
		prices.Cardmarket = v
	} else if v := resp.Data.Cardmarket.Prices.TrendPrice; v != nil {
		prices.Cardmarket = v
	}

	return prices, nil
}

func coalesce(a, b *float64) *float64 {
	if a != nil {
		return a
	}
	return b
}

// IterItems implements the generic Dataset interface by listing written price records.
// Note: IterItems not required for CLI extraction flow here.
