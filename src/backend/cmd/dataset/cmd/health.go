package cmd

import (
	"strings"

	"github.com/spf13/cobra"

	"collections/games"
	"collections/games/magic/dataset"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
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
		datasetsToCheck = []string{"mtgtop8", "goldfish", "scryfall", "deckbox"}
	}

	for _, datasetName := range datasetsToCheck {
		config.Log.Infof(config.Ctx, "🔍 Checking health of dataset: %s", datasetName)

		var d dataset.Dataset
		switch datasetName {
		case "deckbox":
			d = deckbox.NewDataset(config.Log, gamesBlob)
		case "scryfall":
			d = scryfall.NewDataset(config.Log, gamesBlob)
		case "goldfish":
			d = goldfish.NewDataset(config.Log, gamesBlob)
		case "mtgtop8":
			d = mtgtop8.NewDataset(config.Log, gamesBlob)
		default:
			config.Log.Warnf(config.Ctx, "⚠️  Unknown dataset: %s, skipping", datasetName)
			continue
		}

		// Run a small test extraction
		opts := []dataset.UpdateOption{
			&dataset.OptExtractItemLimit{Limit: limit},
			&dataset.OptExtractParallel{Parallel: 2}, // Use fewer workers for health check
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

