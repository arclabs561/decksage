package cmd

import (
	"strings"

	"github.com/spf13/cobra"

	"collections/games"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
	digimonlimitless "collections/games/digimon/dataset/limitless"
	digimonlimitlessweb "collections/games/digimon/dataset/limitless-web"
	onepiecelimitless "collections/games/onepiece/dataset/limitless"
	onepiecelimitlessweb "collections/games/onepiece/dataset/limitless-web"
	riftboundriftmana "collections/games/riftbound/dataset/riftmana"
	riftboundriftcodex "collections/games/riftbound/dataset/riftcodex"
	riftboundriftboundgg "collections/games/riftbound/dataset/riftboundgg"
	"collections/scraper"
)

var healthCmd = &cobra.Command{
	Use:   "health [DATASET]",
	Short: "Check dataset health and connectivity",
	Long:  "Test dataset extraction with a small sample to verify it's working correctly",
	Args:  cobra.MaximumNArgs(1),
	RunE:  runHealth,
}

func init() {
	healthCmd.Flags().IntP("limit", "l", 3, "number of items to test with")
}

func runHealth(cmd *cobra.Command, args []string) error {
	config, err := newRootConfig(cmd)
	if err != nil {
		return err
	}

	gamesBlob := config.Bucket.WithPrefix("games/")
	defer gamesBlob.Close(config.Ctx)
	scraperBlob := config.Bucket.WithPrefix("scraper/")
	defer scraperBlob.Close(config.Ctx)

	sc := scraper.NewScraper(config.Log, scraperBlob)

	limit, err := cmd.Flags().GetInt("limit")
	if err != nil {
		return err
	}

	datasetsToCheck := []string{}
	if len(args) > 0 {
		datasetsToCheck = []string{strings.ToLower(args[0])}
	} else {
		datasetsToCheck = []string{"mtgtop8", "goldfish", "scryfall", "deckbox", "digimon-limitless-web", "onepiece-limitless-web", "riftbound-riftboundgg"}
	}

	for _, datasetName := range datasetsToCheck {
		config.Log.Infof(config.Ctx, "🔍 Checking health of dataset: %s", datasetName)

		var d games.Dataset
		switch datasetName {
		case "deckbox":
			d = wrapMTGDataset(deckbox.NewDataset(config.Log, gamesBlob))
		case "scryfall":
			d = wrapMTGDataset(scryfall.NewDataset(config.Log, gamesBlob))
		case "goldfish":
			d = wrapMTGDataset(goldfish.NewDataset(config.Log, gamesBlob))
		case "mtgtop8":
			d = wrapMTGDataset(mtgtop8.NewDataset(config.Log, gamesBlob))
		case "digimon-limitless", "digimonlimitless":
			d = digimonlimitless.NewDataset(config.Log, gamesBlob)
		case "digimon-limitless-web", "digimonlimitlessweb":
			d = digimonlimitlessweb.NewDataset(config.Log, gamesBlob)
		case "onepiece-limitless", "onepiecelimitless":
			d = onepiecelimitless.NewDataset(config.Log, gamesBlob)
		case "onepiece-limitless-web", "onepiecelimitlessweb":
			d = onepiecelimitlessweb.NewDataset(config.Log, gamesBlob)
		case "riftbound-riftmana", "riftboundriftmana":
			dataset, err := riftboundriftmana.NewDataset(config.Log, gamesBlob)
			if err != nil {
				config.Log.Errorf(config.Ctx, "Failed to create riftmana dataset: %v", err)
				continue
			}
			d = dataset
		case "riftbound-riftcodex", "riftboundriftcodex":
			d = riftboundriftcodex.NewDataset(config.Log, gamesBlob)
		case "riftbound-riftboundgg", "riftboundriftboundgg", "riftbound-gg":
			dataset, err := riftboundriftboundgg.NewDataset(config.Log, gamesBlob)
			if err != nil {
				config.Log.Errorf(config.Ctx, "Failed to create riftbound.gg dataset: %v", err)
				continue
			}
			d = dataset
		default:
			config.Log.Warnf(config.Ctx, "⚠️  Unknown dataset: %s, skipping", datasetName)
			continue
		}

		// Run a small test extraction
		opts := []games.UpdateOption{
			&games.OptExtractItemLimit{Limit: limit},
			&games.OptExtractParallel{Parallel: 2}, // Use fewer workers for health check
		}

		stats := games.NewExtractStats(config.Log)
		config.Log.Infof(config.Ctx, "Running test extraction (limit: %d)...", limit)

		err := d.Extract(config.Ctx, sc, opts...)
		if err != nil {
			stats.RecordError(config.Ctx, "", datasetName, err)
			config.Log.Errorf(config.Ctx, "❌ Health check FAILED for %s: %v", datasetName, err)
			continue
		}

		summary := stats.Summary()
		if stats.Total > 0 && stats.Successful > 0 {
			config.Log.Infof(config.Ctx, "✅ Health check PASSED for %s: %s", datasetName, summary)
		} else {
			config.Log.Warnf(config.Ctx, "⚠️  Health check WARNING for %s: No items extracted", datasetName)
		}
	}

	return nil
}

