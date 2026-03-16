package onepiecetcg

import (
	"collections/blob"
	"collections/games"
	"collections/games/onepiece/dataset"
	"collections/games/onepiece/game"
	"collections/logger"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"

	limpet "github.com/arclabs561/limpet"
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
		Game: "onepiece",
		Name: "optcgapi",
	}
}

// OPTCG API card structure (from optcgapi.com)
type apiCard struct {
	InventoryPrice float64  `json:"inventory_price"`
	MarketPrice    float64  `json:"market_price"`
	CardName       string   `json:"card_name"`
	SetName        string   `json:"set_name"`
	CardText       string   `json:"card_text"`
	SetID          string   `json:"set_id"`
	Rarity         string   `json:"rarity"`
	CardSetID      string   `json:"card_set_id"`
	CardColor      string   `json:"card_color"`
	CardType       string   `json:"card_type"`
	Life           *string  `json:"life"`
	CardCost       *string  `json:"card_cost"`
	CardPower      *string  `json:"card_power"`
	SubTypes       string   `json:"sub_types"`
	CounterAmount  *int     `json:"counter_amount"`
	Attribute      *string  `json:"attribute"`
	CardImageID    string   `json:"card_image_id"`
	CardImage      string   `json:"card_image"`
}

func (d *Dataset) Extract(
	ctx context.Context,
	sc *limpet.Client,
	options ...games.UpdateOption,
) error {
	opts, err := games.ResolveUpdateOptions(options...)
	if err != nil {
		return err
	}

	d.log.Infof(ctx, "Extracting One Piece cards from OPTCG API...")

	req, err := http.NewRequest(
		"GET",
		"https://www.optcgapi.com/api/allSetCards/",
		nil,
	)
	if err != nil {
		return err
	}

	page, err := games.Do(ctx, sc, &opts, req)
	if err != nil {
		return fmt.Errorf("failed to fetch cards: %w", err)
	}

	var apiCards []apiCard
	if err := json.Unmarshal(page.Response.Body, &apiCards); err != nil {
		return fmt.Errorf("failed to parse API response: %w", err)
	}

	d.log.Infof(ctx, "Received %d card entries from API", len(apiCards))

	// Deduplicate by card_set_id (API returns multiple entries for parallel arts)
	// Keep the first (non-parallel) entry per card ID
	seen := make(map[string]bool)
	stored := 0

	for i, ac := range apiCards {
		if limit, ok := opts.ItemLimit.Get(); ok && stored >= limit {
			break
		}

		// Skip parallel/alternate art variants
		if seen[ac.CardSetID] {
			continue
		}
		// Skip entries with " (Parallel)" or similar suffixes
		if strings.Contains(ac.CardName, "(Parallel)") ||
			strings.Contains(ac.CardName, "(Textured") ||
			strings.Contains(ac.CardName, "(Jolly Roger") ||
			strings.Contains(ac.CardName, "(Manga") {
			continue
		}
		seen[ac.CardSetID] = true

		card := convertToCard(ac)

		key := d.cardKey(ac.CardSetID)
		data, err := json.Marshal(card)
		if err != nil {
			return fmt.Errorf("failed to marshal card %s: %w", card.Name, err)
		}

		if err := d.blob.Write(ctx, key, data); err != nil {
			return fmt.Errorf("failed to write card %s: %w", card.Name, err)
		}

		stored++
		if stored%500 == 0 {
			d.log.Infof(ctx, "Stored %d cards (processed %d/%d entries)...", stored, i+1, len(apiCards))
		}
	}

	d.log.Infof(ctx, "Extracted %d unique One Piece cards from OPTCG API", stored)
	return nil
}

func convertToCard(ac apiCard) game.Card {
	card := game.Card{
		Name:       cleanCardName(ac.CardName),
		Type:       ac.CardType,
		Rarity:     ac.Rarity,
		Set:        ac.SetID,
		SetName:    ac.SetName,
		CardNumber: ac.CardSetID,
	}

	// Colors: card_color can be multi-color separated by "/"
	if ac.CardColor != "" {
		colors := strings.Split(ac.CardColor, "/")
		for i := range colors {
			colors[i] = strings.TrimSpace(colors[i])
		}
		card.Color = colors
	}

	// Cost
	if ac.CardCost != nil {
		if cost, err := strconv.Atoi(*ac.CardCost); err == nil {
			card.Cost = cost
		}
	}

	// Power
	if ac.CardPower != nil {
		if power, err := strconv.Atoi(*ac.CardPower); err == nil {
			card.Power = power
		}
	}

	// Counter
	if ac.CounterAmount != nil {
		card.Counter = *ac.CounterAmount
	}

	// Attribute
	if ac.Attribute != nil {
		card.Attribute = *ac.Attribute
	}

	// Parse effect and trigger from card_text
	// Trigger text is embedded as "[Trigger] ..." within the card text
	if ac.CardText != "" {
		effect, trigger := splitEffectTrigger(ac.CardText)
		card.Effect = effect
		card.Trigger = trigger
	}

	// Image
	if ac.CardImage != "" {
		card.Images = append(card.Images, game.CardImage{
			URL: ac.CardImage,
		})
	}

	return card
}

// splitEffectTrigger separates effect text from trigger text.
// Trigger is marked by "[Trigger]" prefix in the card text.
func splitEffectTrigger(text string) (effect, trigger string) {
	idx := strings.Index(text, "[Trigger]")
	if idx < 0 {
		return strings.TrimSpace(text), ""
	}
	effect = strings.TrimSpace(text[:idx])
	trigger = strings.TrimSpace(text[idx+len("[Trigger]"):])
	return effect, trigger
}

// cleanCardName removes numbering suffixes like " (001)" from card names.
func cleanCardName(name string) string {
	// Remove trailing " (NNN)" pattern used by the API
	if idx := strings.LastIndex(name, " ("); idx > 0 {
		suffix := name[idx+2:]
		if len(suffix) > 0 && suffix[len(suffix)-1] == ')' {
			inner := suffix[:len(suffix)-1]
			// Only strip if it's purely numeric (card number suffix)
			if _, err := strconv.Atoi(inner); err == nil {
				return name[:idx]
			}
		}
	}
	return name
}

var basePrefix = filepath.Join("games", "onepiece", "optcgapi")
var cardsPrefix = filepath.Join(basePrefix, "cards")

func (d *Dataset) cardKey(cardSetID string) string {
	return filepath.Join(cardsPrefix, cardSetID+".json")
}

func (d *Dataset) IterItems(
	ctx context.Context,
	fn func(item games.Item) error,
	options ...games.IterItemsOption,
) error {
	return games.IterItemsBlobPrefix(
		ctx,
		d.blob,
		cardsPrefix+"/",
		func(key string, data []byte) (games.Item, error) {
			item, err := dataset.DeserializeAsCard(key, data)
			if err != nil {
				return nil, err
			}
			cardItem := item.(*dataset.CardItem)
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
