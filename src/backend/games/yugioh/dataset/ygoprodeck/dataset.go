package ygoprodeck

import (
	"collections/blob"
	"collections/games"
	"collections/games/yugioh/dataset"
	"collections/games/yugioh/game"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
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
		Game: "yugioh",
		Name: "ygoprodeck",
	}
}

// YGOPRODeck API response structure
type apiCard struct {
	Name       string `json:"name"`
	Type       string `json:"type"`
	Desc       string `json:"desc"`
	ATK        *int   `json:"atk"`
	DEF        *int   `json:"def"`
	Level      *int   `json:"level"`
	Rank       *int   `json:"rank"`
	LinkVal    *int   `json:"linkval"`
	Race       string `json:"race"`
	Attribute  string `json:"attribute"`
	Archetype  string `json:"archetype"`
	CardImages []struct {
		ImageURL      string `json:"image_url"`
		ImageURLSmall string `json:"image_url_small"`
	} `json:"card_images"`
	CardSets []struct {
		SetName       string `json:"set_name"`
		SetCode       string `json:"set_code"`
		SetRarity     string `json:"set_rarity"`
		SetRarityCode string `json:"set_rarity_code"`
		SetPrice      string `json:"set_price"` // Price as string
	} `json:"card_sets,omitempty"`
	CardPrices []struct {
		TCGPlayer     string `json:"tcgplayer_price"`
		Cardmarket    string `json:"cardmarket_price"`
		Amazon        string `json:"amazon_price"`
		Ebay          string `json:"ebay_price"`
		CoolStuffInc  string `json:"coolstuffinc_price"`
	} `json:"card_prices,omitempty"`
	BanlistInfo *struct {
		BanTCG string `json:"ban_tcg,omitempty"` // Banned, Limited, Semi-Limited
		BanOCG string `json:"ban_ocg,omitempty"`
	} `json:"banlist_info,omitempty"`
}

type apiResponse struct {
	Data []apiCard `json:"data"`
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

	d.log.Infof(ctx, "Extracting Yu-Gi-Oh! cards from YGOPRODeck API...")

	// YGOPRODeck API endpoint (all cards)
	req, err := http.NewRequest("GET", "https://db.ygoprodeck.com/api/v7/cardinfo.php", nil)
	if err != nil {
		return err
	}

	page, err := games.Do(ctx, sc, &opts, req)
	if err != nil {
		return fmt.Errorf("failed to fetch cards: %w", err)
	}

	// Parse API response
	var apiResp apiResponse
	if err := json.Unmarshal(page.Response.Body, &apiResp); err != nil {
		return fmt.Errorf("failed to parse API response: %w", err)
	}

	d.log.Infof(ctx, "Received %d cards from API", len(apiResp.Data))

	// Store each card
	for i, cardData := range apiResp.Data {
		card := convertToCard(cardData)

		// Store in blob: games/yugioh/ygoprodeck/cards/{name}.json
		key := fmt.Sprintf("games/yugioh/ygoprodeck/cards/%s.json", cardData.Name)
		data, err := json.Marshal(card)
		if err != nil {
			return fmt.Errorf("failed to marshal card %s: %w", card.Name, err)
		}

		if err := d.blob.Write(ctx, key, data); err != nil {
			return fmt.Errorf("failed to write card %s: %w", card.Name, err)
		}

		if (i+1)%1000 == 0 {
			d.log.Infof(ctx, "Stored %d/%d cards...", i+1, len(apiResp.Data))
		}
	}

	d.log.Infof(ctx, "✅ Extracted %d Yu-Gi-Oh! cards from YGOPRODeck", len(apiResp.Data))
	return nil
}

func convertToCard(apiCard apiCard) game.Card {
	card := game.Card{
		Name:        apiCard.Name,
		Description: apiCard.Desc,
		Race:        apiCard.Race,
		Attribute:   apiCard.Attribute,
		Archetype:   apiCard.Archetype,
	}

	// Determine card type
	switch {
	case contains(apiCard.Type, "Monster"):
		card.Type = game.TypeMonster
		card.MonsterType = parseMonsterType(apiCard.Type)
		if apiCard.ATK != nil {
			card.ATK = *apiCard.ATK
		}
		if apiCard.DEF != nil {
			card.DEF = *apiCard.DEF
		}
		if apiCard.Level != nil {
			card.Level = *apiCard.Level
		}
		if apiCard.Rank != nil {
			card.Rank = *apiCard.Rank
		}
		if apiCard.LinkVal != nil {
			card.LinkRating = *apiCard.LinkVal
		}

	case contains(apiCard.Type, "Spell"):
		card.Type = game.TypeSpell

	case contains(apiCard.Type, "Trap"):
		card.Type = game.TypeTrap
	}

	// Images
	for _, img := range apiCard.CardImages {
		card.Images = append(card.Images, game.CardImage{
			URL: img.ImageURL,
		})
	}
	
	// Prices (take first set of prices if available)
	if len(apiCard.CardPrices) > 0 {
		prices := apiCard.CardPrices[0]
		card.Prices = game.CardPrices{}
		
		if tcg, err := parsePrice(prices.TCGPlayer); err == nil && tcg > 0 {
			card.Prices.TCGPlayer = &tcg
		}
		if cm, err := parsePrice(prices.Cardmarket); err == nil && cm > 0 {
			card.Prices.Cardmarket = &cm
		}
		if amz, err := parsePrice(prices.Amazon); err == nil && amz > 0 {
			card.Prices.Amazon = &amz
		}
		if ebay, err := parsePrice(prices.Ebay); err == nil && ebay > 0 {
			card.Prices.Ebay = &ebay
		}
		if cool, err := parsePrice(prices.CoolStuffInc); err == nil && cool > 0 {
			card.Prices.CoolStuff = &cool
		}
	}
	
	// Ban status (TCG)
	if apiCard.BanlistInfo != nil && apiCard.BanlistInfo.BanTCG != "" {
		card.BanStatus = apiCard.BanlistInfo.BanTCG
	}
	
	// Set info (use first set if available)
	if len(apiCard.CardSets) > 0 {
		set := apiCard.CardSets[0]
		card.Set = set.SetCode
		card.SetName = set.SetName
		card.Rarity = set.SetRarity
	}

	return card
}

func parsePrice(s string) (float64, error) {
	if s == "" {
		return 0, fmt.Errorf("empty price")
	}
	var f float64
	_, err := fmt.Sscanf(s, "%f", &f)
	return f, err
}

func parseMonsterType(typeStr string) *game.MonsterType {
	mt := &game.MonsterType{
		MainType: typeStr,
	}

	// Parse type flags
	mt.IsEffect = contains(typeStr, "Effect")
	mt.IsFusion = contains(typeStr, "Fusion")
	mt.IsSynchro = contains(typeStr, "Synchro")
	mt.IsXyz = contains(typeStr, "XYZ")
	mt.IsLink = contains(typeStr, "Link")
	mt.IsRitual = contains(typeStr, "Ritual")
	mt.IsPendulum = contains(typeStr, "Pendulum")

	return mt
}

func contains(s, substr string) bool {
	return strings.Contains(s, substr)
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(item games.Item) error,
	options ...games.IterItemsOption,
) error {
	// Adapt to YGO-specific Item type
	return games.IterItemsBlobPrefix(
		ctx,
		d.blob,
		"games/yugioh/ygoprodeck/cards/",
		func(key string, data []byte) (games.Item, error) {
			ygoItem, err := dataset.DeserializeAsCard(key, data)
			if err != nil {
				return nil, err
			}
			// Wrap in CollectionItem-like structure
			// For now, just pass through as we only have cards
			cardItem := ygoItem.(*dataset.CardItem)
			return &games.CollectionItem{
				Collection: &games.Collection{
					ID: cardItem.Card.Name,
					// Minimal collection wrapping
				},
			}, nil
		},
		fn,
		options...,
	)
}
