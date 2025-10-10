package pokemontcg

import (
	"collections/blob"
	"collections/games"
	"collections/games/pokemon/dataset"
	"collections/games/pokemon/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
)

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
		Name: "pokemontcg",
	}
}

// Pokemon TCG API response structures
type apiCard struct {
	ID          string   `json:"id"`
	Name        string   `json:"name"`
	Supertype   string   `json:"supertype"`
	Subtypes    []string `json:"subtypes"`
	HP          string   `json:"hp"`
	Types       []string `json:"types"`
	EvolvesFrom string   `json:"evolvesFrom"`
	EvolvesTo   []string `json:"evolvesTo"`
	Attacks     []struct {
		Name                string   `json:"name"`
		Cost                []string `json:"cost"`
		ConvertedEnergyCost int      `json:"convertedEnergyCost"`
		Damage              string   `json:"damage"`
		Text                string   `json:"text"`
	} `json:"attacks"`
	Abilities []struct {
		Name string `json:"name"`
		Text string `json:"text"`
		Type string `json:"type"`
	} `json:"abilities"`
	Weaknesses []struct {
		Type  string `json:"type"`
		Value string `json:"value"`
	} `json:"weaknesses"`
	Resistances []struct {
		Type  string `json:"type"`
		Value string `json:"value"`
	} `json:"resistances"`
	RetreatCost            []string `json:"retreatCost"`
	Rules                  []string `json:"rules"`
	NationalPokedexNumbers []int    `json:"nationalPokedexNumbers"`
	Images                 struct {
		Small string `json:"small"`
		Large string `json:"large"`
	} `json:"images"`
	Set struct {
		ID   string `json:"id"`
		Name string `json:"name"`
	} `json:"set"`
	Rarity string `json:"rarity"`
	Artist string `json:"artist"`
}

type apiResponse struct {
	Data       []apiCard `json:"data"`
	Page       int       `json:"page"`
	PageSize   int       `json:"pageSize"`
	Count      int       `json:"count"`
	TotalCount int       `json:"totalCount"`
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

	d.log.Infof(ctx, "Extracting Pokemon cards from Pokemon TCG API...")

	// Pokemon TCG API endpoint
	// API key is optional for low-rate usage
	url := "https://api.pokemontcg.io/v2/cards?pageSize=250"

	page := 1
	totalCards := 0

	for {
		// Check limit
		if limit, ok := opts.ItemLimit.Get(); ok && totalCards >= limit {
			d.log.Infof(ctx, "Reached item limit of %d", limit)
			break
		}

		pageURL := fmt.Sprintf("%s&page=%d", url, page)
		req, err := http.NewRequest("GET", pageURL, nil)
		if err != nil {
			return err
		}

		pageResp, err := games.Do(ctx, sc, &opts, req)
		if err != nil {
			// Pokemon TCG API returns 404 when pagination exhausted
			// Treat as graceful end rather than error
			if page > 1 {
				d.log.Infof(ctx, "Failed to fetch page %d (likely end of pagination): %v", page, err)
				d.log.Infof(ctx, "Successfully extracted %d cards before pagination ended", totalCards)
				break
			}
			return fmt.Errorf("failed to fetch cards page %d: %w", page, err)
		}

		// Parse API response
		var apiResp apiResponse
		if err := json.Unmarshal(pageResp.Response.Body, &apiResp); err != nil {
			// Try to parse error response
			d.log.Warnf(ctx, "Failed to parse page %d, skipping: %v", page, err)
			break
		}

		if len(apiResp.Data) == 0 {
			d.log.Infof(ctx, "No more cards on page %d, stopping", page)
			break
		}

		d.log.Infof(ctx, "Processing page %d with %d cards", page, len(apiResp.Data))

		// Store each card
		for i, cardData := range apiResp.Data {
			if limit, ok := opts.ItemLimit.Get(); ok && totalCards >= limit {
				break
			}

			card := convertToCard(cardData)

			// Store in blob: games/pokemon/pokemontcg/cards/{id}.json
			key := fmt.Sprintf("games/pokemon/pokemontcg/cards/%s.json", cardData.ID)
			data, err := json.Marshal(card)
			if err != nil {
				return fmt.Errorf("failed to marshal card %s: %w", card.Name, err)
			}

			if err := d.blob.Write(ctx, key, data); err != nil {
				return fmt.Errorf("failed to write card %s: %w", card.Name, err)
			}

			totalCards++
			if (i+1)%100 == 0 {
				d.log.Infof(ctx, "Stored %d cards so far...", totalCards)
			}
		}

		// Check if we've reached the end
		if page*apiResp.PageSize >= apiResp.TotalCount {
			d.log.Infof(ctx, "Reached end of results")
			break
		}

		page++
	}

	d.log.Infof(ctx, "✅ Extracted %d Pokemon cards from Pokemon TCG API", totalCards)
	return nil
}

func convertToCard(apiCard apiCard) game.Card {
	card := game.Card{
		Name:        apiCard.Name,
		SuperType:   apiCard.Supertype,
		SubTypes:    apiCard.Subtypes,
		HP:          apiCard.HP,
		Types:       apiCard.Types,
		EvolvesFrom: apiCard.EvolvesFrom,
		EvolvesTo:   apiCard.EvolvesTo,
		RetreatCost: apiCard.RetreatCost,
		Rules:       apiCard.Rules,
		Rarity:      apiCard.Rarity,
		Artist:      apiCard.Artist,
	}

	// National dex number (take first if multiple)
	if len(apiCard.NationalPokedexNumbers) > 0 {
		card.NationalDex = apiCard.NationalPokedexNumbers[0]
	}

	// Attacks
	for _, atk := range apiCard.Attacks {
		card.Attacks = append(card.Attacks, game.Attack{
			Name:                atk.Name,
			Cost:                atk.Cost,
			ConvertedEnergyCost: atk.ConvertedEnergyCost,
			Damage:              atk.Damage,
			Text:                atk.Text,
		})
	}

	// Abilities
	for _, abl := range apiCard.Abilities {
		card.Abilities = append(card.Abilities, game.Ability{
			Name: abl.Name,
			Text: abl.Text,
			Type: abl.Type,
		})
	}

	// Weaknesses
	for _, w := range apiCard.Weaknesses {
		card.Weaknesses = append(card.Weaknesses, game.Resistance{
			Type:  w.Type,
			Value: w.Value,
		})
	}

	// Resistances
	for _, r := range apiCard.Resistances {
		card.Resistances = append(card.Resistances, game.Resistance{
			Type:  r.Type,
			Value: r.Value,
		})
	}

	// Images
	if apiCard.Images.Small != "" || apiCard.Images.Large != "" {
		card.Images = append(card.Images, game.CardImage{
			URL:   apiCard.Images.Large,
			Small: apiCard.Images.Small,
			Large: apiCard.Images.Large,
		})
	}

	return card
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(item games.Item) error,
	options ...games.IterItemsOption,
) error {
	return games.IterItemsBlobPrefix(
		ctx,
		d.blob,
		"games/pokemon/pokemontcg/cards/",
		func(key string, data []byte) (games.Item, error) {
			pokemonItem, err := dataset.DeserializeAsCard(key, data)
			if err != nil {
				return nil, err
			}
			cardItem := pokemonItem.(*dataset.CardItem)
			return &games.CollectionItem{
				Collection: &games.Collection{
					ID: cardItem.Card.Name,
				},
			}, nil
		},
		fn,
		options...,
	)
}
