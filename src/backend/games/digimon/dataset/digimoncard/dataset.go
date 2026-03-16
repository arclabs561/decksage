package digimoncard

import (
	"collections/blob"
	"collections/games"
	"collections/games/digimon/dataset"
	"collections/games/digimon/game"
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
		Game: "digimon",
		Name: "digimoncard",
	}
}

// digimoncard.io API card structure
type apiCard struct {
	Name           string   `json:"name"`
	Type           string   `json:"type"`
	ID             string   `json:"id"`
	Level          int      `json:"level"`
	PlayCost       int      `json:"play_cost"`
	EvolutionCost  int      `json:"evolution_cost"`
	EvolutionColor string   `json:"evolution_color"`
	EvolutionLevel int      `json:"evolution_level"`
	Color          string   `json:"color"`
	Color2         *string  `json:"color2"`
	DigiType       string   `json:"digi_type"`
	DigiType2      *string  `json:"digi_type2"`
	DigiType3      *string  `json:"digi_type3"`
	DigiType4      *string  `json:"digi_type4"`
	Form           string   `json:"form"`
	DP             int      `json:"dp"`
	Attribute      string   `json:"attribute"`
	Rarity         string   `json:"rarity"`
	Stage          string   `json:"stage"`
	MainEffect     string   `json:"main_effect"`
	SourceEffect   string   `json:"source_effect"`
	AltEffect      string   `json:"alt_effect"`
	SetName        []string `json:"set_name"`
	PrettyURL      string   `json:"pretty_url"`
	TCGPlayerName  string   `json:"tcgplayer_name"`
	TCGPlayerID    int      `json:"tcgplayer_id"`
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

	d.log.Infof(ctx, "Extracting Digimon cards from digimoncard.io API...")

	req, err := http.NewRequest(
		"GET",
		"https://digimoncard.io/api-public/search.php?sort=name&series=Digimon+Card+Game",
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

	d.log.Infof(ctx, "Received %d cards from API", len(apiCards))

	for i, ac := range apiCards {
		if limit, ok := opts.ItemLimit.Get(); ok && i >= limit {
			break
		}

		card := convertToCard(ac)

		key := d.cardKey(ac.ID)
		data, err := json.Marshal(card)
		if err != nil {
			return fmt.Errorf("failed to marshal card %s: %w", card.Name, err)
		}

		if err := d.blob.Write(ctx, key, data); err != nil {
			return fmt.Errorf("failed to write card %s: %w", card.Name, err)
		}

		if (i+1)%500 == 0 {
			d.log.Infof(ctx, "Stored %d/%d cards...", i+1, len(apiCards))
		}
	}

	d.log.Infof(ctx, "Extracted %d Digimon cards from digimoncard.io", len(apiCards))
	return nil
}

func convertToCard(ac apiCard) game.Card {
	card := game.Card{
		Name:        ac.Name,
		Type:        ac.Type,
		Color:       ac.Color,
		Level:       levelStr(ac.Level),
		Attribute:   ac.Attribute,
		DP:          ac.DP,
		PlayCost:    ac.PlayCost,
		EvolutionCost: ac.EvolutionCost,
		CardNumber:  ac.ID,
		Rarity:      ac.Rarity,
	}

	// Build type category from digi_type fields
	var digiTypes []string
	if ac.DigiType != "" {
		digiTypes = append(digiTypes, ac.DigiType)
	}
	if ac.DigiType2 != nil && *ac.DigiType2 != "" {
		digiTypes = append(digiTypes, *ac.DigiType2)
	}
	if ac.DigiType3 != nil && *ac.DigiType3 != "" {
		digiTypes = append(digiTypes, *ac.DigiType3)
	}
	if ac.DigiType4 != nil && *ac.DigiType4 != "" {
		digiTypes = append(digiTypes, *ac.DigiType4)
	}
	if len(digiTypes) > 0 {
		card.TypeCategory = strings.Join(digiTypes, "/")
	}

	// Description combines form/stage info
	if ac.Form != "" {
		card.Description = ac.Form
	}

	// Main effect
	if ac.MainEffect != "" {
		card.Effects = append(card.Effects, game.Effect{
			Type: "Main",
			Text: ac.MainEffect,
		})
	}

	// Alt effect (security effect for some cards)
	if ac.AltEffect != "" {
		card.Effects = append(card.Effects, game.Effect{
			Type: "Security",
			Text: ac.AltEffect,
		})
	}

	// Inherited/source effect
	if ac.SourceEffect != "" {
		card.Inherited = append(card.Inherited, game.Effect{
			Type: "Inherited",
			Text: ac.SourceEffect,
		})
	}

	// Image from digimoncard.io
	imgURL := fmt.Sprintf("https://images.digimoncard.io/images/cards/%s.jpg", ac.ID)
	card.Images = append(card.Images, game.CardImage{
		URL: imgURL,
	})

	// Reference URL
	if ac.PrettyURL != "" {
		card.References = append(card.References, game.CardRef{
			URL: fmt.Sprintf("https://digimoncard.io/card/%s", ac.PrettyURL),
		})
	}

	// Set name (take first if available)
	if len(ac.SetName) > 0 {
		card.SetName = ac.SetName[0]
		// Extract set code from card ID (e.g. "BT1-010" -> "BT1")
		if idx := strings.Index(ac.ID, "-"); idx > 0 {
			card.Set = ac.ID[:idx]
		}
	}

	return card
}

func levelStr(level int) string {
	if level == 0 {
		return ""
	}
	return "Lv." + strconv.Itoa(level)
}

var basePrefix = filepath.Join("games", "digimon", "digimoncard")
var cardsPrefix = filepath.Join(basePrefix, "cards")

func (d *Dataset) cardKey(cardID string) string {
	return filepath.Join(cardsPrefix, cardID+".json")
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
