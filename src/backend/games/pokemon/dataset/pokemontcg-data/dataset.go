package pokemontcgdata

import (
	"collections/blob"
	"collections/games"
	"collections/logger"
	"collections/scraper"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"collections/games/pokemon/game"
)

// apiCard matches the structure of the JSON objects in the pokemon-tcg-data repo
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

// apiSet matches the structure of set objects in the pokemon-tcg-data repo
type apiSet struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	Series       string `json:"series"`
	PrintedTotal int    `json:"printedTotal"`
	Total        int    `json:"total"`
	ReleaseDate  string `json:"releaseDate"`
}

// Dataset fetches Pokemon card data from the pokemon-tcg-data GitHub repo
// Source: https://github.com/PokemonTCG/pokemon-tcg-data
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
		Name: "pokemontcg-data",
	}
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

	repoURL := "https://github.com/PokemonTCG/pokemon-tcg-data.git"

	// Allow overriding clone path via env for CI/local caching
	cloneDir := os.Getenv("POKEMON_TCG_DATA_DIR")
	if cloneDir == "" {
		cloneDir = filepath.Join("..", "..", "..", "integration_test_tmp", "pokemon-tcg-data")
	}

	// 1. Clone or pull the repo.
	if _, err := os.Stat(cloneDir); os.IsNotExist(err) {
		d.log.Infof(ctx, "Cloning %s into %s...", repoURL, cloneDir)
		cmd := exec.CommandContext(ctx, "git", "clone", "--depth=1", repoURL, cloneDir)
		if output, err := cmd.CombinedOutput(); err != nil {
			d.log.Errorf(ctx, "git clone output: %s", string(output))
			return fmt.Errorf("failed to clone repo: %w", err)
		}
	} else {
		d.log.Infof(ctx, "Pulling latest changes in %s...", cloneDir)
		cmd := exec.CommandContext(ctx, "git", "-C", cloneDir, "pull")
		if output, err := cmd.CombinedOutput(); err != nil {
			d.log.Errorf(ctx, "git pull output: %s", string(output))
			return fmt.Errorf("failed to pull repo: %w", err)
		}
	}

	// 2a. Find and parse the card JSON files.
	setsDir := filepath.Join(cloneDir, "cards", "en")
	files, err := os.ReadDir(setsDir)
	if err != nil {
		return fmt.Errorf("failed to read sets directory %s: %w", setsDir, err)
	}

	totalCardsProcessed := 0
	// Optional global item/card limit across all sets
	var globalLimit int
	if limit, ok := opts.ItemLimit.Get(); ok {
		globalLimit = limit
	}
	for _, file := range files {
		if filepath.Ext(file.Name()) != ".json" {
			continue
		}

		filePath := filepath.Join(setsDir, file.Name())
		jsonData, err := os.ReadFile(filePath)
		if err != nil {
			d.log.Warnf(ctx, "Failed to read file %s: %v", filePath, err)
			continue
		}

		var cards []apiCard
		if err := json.Unmarshal(jsonData, &cards); err != nil {
			d.log.Warnf(ctx, "Failed to unmarshal JSON from %s: %v", filePath, err)
			continue
		}

		for _, apiCard := range cards {
			card := convertToCard(apiCard)

			// Store in blob: pokemon/pokemontcg-data/cards/{id}.json (relative to games/ prefix)
			key := fmt.Sprintf("pokemon/pokemontcg-data/cards/%s.json", apiCard.ID)
			data, err := json.Marshal(card)
			if err != nil {
				d.log.Warnf(ctx, "failed to marshal card %s: %w", card.Name, err)
				continue
			}

			// Skip existing unless forced
			if !opts.Reparse && !opts.FetchReplaceAll {
				if exists, _ := d.blob.Exists(ctx, key); exists {
					totalCardsProcessed++
					if globalLimit > 0 && totalCardsProcessed >= globalLimit {
						d.log.Infof(ctx, "Reached global item limit of %d", globalLimit)
						return nil
					}
					continue
				}
			}

			if err := d.blob.Write(ctx, key, data); err != nil {
				d.log.Warnf(ctx, "failed to write card %s: %w", card.Name, err)
				continue
			}
			totalCardsProcessed++
			if globalLimit > 0 && totalCardsProcessed >= globalLimit {
				d.log.Infof(ctx, "Reached global item limit of %d", globalLimit)
				return nil
			}
		}
	}

	d.log.Infof(ctx, "Successfully processed %d cards from %d set files.", totalCardsProcessed, len(files))

	// 2b. Parse sets metadata if present
	// Common layout in repo: sets/en.json (single file). Fallback: sets/en/*.json
	setsJSONPath := filepath.Join(cloneDir, "sets", "en.json")
	if b, err := os.ReadFile(setsJSONPath); err == nil {
		var sets []apiSet
		if err := json.Unmarshal(b, &sets); err == nil {
			for _, s := range sets {
				setObj := game.CollectionTypeSet{
					Name:         s.Name,
					Code:         s.ID,
					Series:       s.Series,
					ReleaseDate:  s.ReleaseDate,
					PrintedTotal: s.PrintedTotal,
					Total:        s.Total,
				}
				key := filepath.Join("pokemon", "pokemontcg-data", "sets", s.ID+".json")
				data, merr := json.Marshal(setObj)
				if merr != nil {
					d.log.Warnf(ctx, "failed to marshal set %s: %v", s.ID, merr)
					continue
				}
				if err := d.blob.Write(ctx, key, data); err != nil {
					d.log.Warnf(ctx, "failed to write set %s: %v", s.ID, err)
					continue
				}
			}
			d.log.Infof(ctx, "Processed %d set metadata entries.", len(sets))
		} else {
			d.log.Warnf(ctx, "failed to unmarshal sets from %s: %v", setsJSONPath, err)
		}
	} else {
		// Fallback to directory of json files
		setsDir := filepath.Join(cloneDir, "sets", "en")
		if entries, derr := os.ReadDir(setsDir); derr == nil {
			written := 0
			for _, e := range entries {
				if filepath.Ext(e.Name()) != ".json" {
					continue
				}
				p := filepath.Join(setsDir, e.Name())
				b, rerr := os.ReadFile(p)
				if rerr != nil {
					continue
				}
				var s apiSet
				if uerr := json.Unmarshal(b, &s); uerr != nil {
					continue
				}
				setObj := game.CollectionTypeSet{
					Name:         s.Name,
					Code:         s.ID,
					Series:       s.Series,
					ReleaseDate:  s.ReleaseDate,
					PrintedTotal: s.PrintedTotal,
					Total:        s.Total,
				}
				key := filepath.Join("pokemon", "pokemontcg-data", "sets", s.ID+".json")
				data, merr := json.Marshal(setObj)
				if merr != nil {
					continue
				}
				if err := d.blob.Write(ctx, key, data); err == nil {
					written++
				}
			}
			d.log.Infof(ctx, "Processed %d set metadata entries (dir mode).", written)
		}
	}

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
		Set:         apiCard.Set.ID,
		SetName:     apiCard.Set.Name,
	}

	if len(apiCard.NationalPokedexNumbers) > 0 {
		card.NationalDex = apiCard.NationalPokedexNumbers[0]
	}

	for _, atk := range apiCard.Attacks {
		card.Attacks = append(card.Attacks, game.Attack{
			Name:                atk.Name,
			Cost:                atk.Cost,
			ConvertedEnergyCost: atk.ConvertedEnergyCost,
			Damage:              atk.Damage,
			Text:                atk.Text,
		})
	}

	for _, abl := range apiCard.Abilities {
		card.Abilities = append(card.Abilities, game.Ability{
			Name: abl.Name,
			Text: abl.Text,
			Type: abl.Type,
		})
	}

	for _, w := range apiCard.Weaknesses {
		card.Weaknesses = append(card.Weaknesses, game.Resistance{
			Type:  w.Type,
			Value: w.Value,
		})
	}

	for _, r := range apiCard.Resistances {
		card.Resistances = append(card.Resistances, game.Resistance{
			Type:  r.Type,
			Value: r.Value,
		})
	}

	if apiCard.Images.Small != "" || apiCard.Images.Large != "" {
		card.Images = append(card.Images, game.CardImage{
			URL:   apiCard.Images.Large,
			Small: apiCard.Images.Small,
			Large: apiCard.Images.Large,
		})
	}

	return card
}
