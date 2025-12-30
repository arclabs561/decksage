package cmd

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"github.com/spf13/pflag"

	"collections/games"
	"collections/games/magic/dataset"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
	"collections/logger"
	"collections/scraper"
)

var extractCmd = &cobra.Command{
	Use:  "extract DATASET",
	Args: cobra.ExactArgs(1),
	RunE: runExtract,
}

func init() {
	flags := extractCmd.PersistentFlags()
	flags.BoolP("reparse", "r", false, "whether to force reparsing")
	flags.BoolP("rescrape", "R", false, "whether to refetch all web pages")
	flags.BoolP("noscrape", "N", false, "whether to skip any fetching of")
	flags.IntP("parallel", "p", 128, "number of parallel workers")
	flags.IntP("pages", "P", 0, "limit on number of pages of collections to scroll")
	flags.IntP("start", "s", 0, "which page index to start updating from")
	flags.IntP("limit", "l", 0, "limit on number of items to update")
	flags.StringArrayP("only", "o", nil, "update only the given urls, if provided")
	flags.StringP("section", "S", "", "which section to parse")
	flags.Bool("cat", false, "whether to print out json lines of extracted items")
}

func runExtract(cmd *cobra.Command, args []string) error {
	config, err := newRootConfig(cmd)
	if err != nil {
		return err
	}

	gamesBlob := config.Bucket.WithPrefix("games/")
	defer func() {
		gamesBlob.Close(config.Ctx)
	}()
	scraperBlob := config.Bucket.WithPrefix("scraper/")
	defer func() {
		scraperBlob.Close(config.Ctx)
	}()

	scraper := scraper.NewScraper(config.Log, scraperBlob)

	var d dataset.Dataset
	datasetName := strings.ToLower(args[0])
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
		return fmt.Errorf(
			"unsupported dataset %q, allowed (%+v)",
			datasetName,
			[]string{"deckbox", "scryfall", "goldfish", "mtgtop8"},
		)
	}
	opts := parseOptions(config.Ctx, config.Log, cmd.Flags())
	
	// Create stats tracker and progress reporter for extraction metrics
	stats := games.NewExtractStats(config.Log)
	progress := games.NewProgressReporter(config.Log, d.Description().Name, 30*time.Second)
	
	// Pass stats through context so datasets can access it
	ctxWithStats := games.WithExtractStats(config.Ctx, stats)
	
	config.Log.Infof(ctxWithStats, "🚀 Starting extraction for dataset: %s", d.Description().Name)
	
	if err := d.Extract(ctxWithStats, scraper, opts...); err != nil {
		stats.RecordError(config.Ctx, "", d.Description().Name, err)
		progress.IncrementFailed()
		config.Log.Errorf(config.Ctx, "Extraction failed: %v", err)
		progress.FinalReport()
		config.Log.Infof(config.Ctx, "Extraction summary: %s", stats.Summary())
		return fmt.Errorf("failed to update: %w", err)
	}
	
	// Final progress report
	progress.FinalReport()
	
	// Display extraction summary with quality metrics
	config.Log.Infof(config.Ctx, "✅ Extraction complete: %s", stats.Summary())
	
	// Show quality metrics
	if stats.NormalizedCount > 0 {
		config.Log.Infof(config.Ctx, "📝 Normalized %d card names", stats.NormalizedCount)
	}
	cacheHitRate := stats.GetCacheHitRate() * 100
	if stats.CacheHits+stats.CacheMisses > 0 {
		config.Log.Infof(config.Ctx, "💾 Cache: %.1f%% hit rate (%d hits, %d misses)", 
			cacheHitRate, stats.CacheHits, stats.CacheMisses)
	}
	if len(stats.ValidationFailures) > 0 {
		config.Log.Warnf(config.Ctx, "⚠️  Validation failures:")
		for errorType, count := range stats.ValidationFailures {
			config.Log.Warnf(config.Ctx, "   - %s: %d", errorType, count)
		}
	}
	
	// Show recent errors if any
	errors := stats.GetErrors()
	if len(errors) > 0 {
		config.Log.Warnf(config.Ctx, "❌ Encountered %d errors during extraction", len(errors))
		// Show first 5 errors
		maxErrors := 5
		if len(errors) < maxErrors {
			maxErrors = len(errors)
		}
		for i := 0; i < maxErrors; i++ {
			config.Log.Field("url", errors[i].URL).
				Field("error", errors[i].Error).
				Warnf(config.Ctx, "Error %d/%d", i+1, len(errors))
		}
		if len(errors) > maxErrors {
			config.Log.Warnf(config.Ctx, "... and %d more errors (see logs for details)", len(errors)-maxErrors)
		}
	}

	return nil
}

func parseOptions(
	ctx context.Context,
	log *logger.Logger,
	flags *pflag.FlagSet,
) []dataset.UpdateOption {
	var opts []dataset.UpdateOption

	reparse, err := flags.GetBool("reparse")
	if err != nil {
		log.Fatalf(ctx, "failed to get bool flag --reparse")
	}
	if reparse {
		opts = append(opts, &dataset.OptExtractReparse{})
	}

	rescrape, err := flags.GetBool("rescrape")
	if err != nil {
		log.Fatalf(ctx, "failed to get bool flag --rescrape")
	}
	if rescrape {
		opts = append(opts, &dataset.OptExtractScraperReplaceAll{})
	}

	parallel, err := flags.GetInt("parallel")
	if err != nil {
		log.Fatalf(ctx, "failed to get int flag --parallel")
	}
	opts = append(opts, &dataset.OptExtractParallel{Parallel: parallel})

	if flags.Lookup("section") != nil {
		section, err := flags.GetString("section")
		if err != nil {
			log.Fatalf(ctx, "failed to get string flag --section")
		}
		opts = append(opts, &dataset.OptExtractSectionOnly{Section: section})
	}

	if flags.Lookup("pages") != nil {
		pages, err := flags.GetInt("pages")
		if err != nil {
			log.Fatalf(ctx, "failed to get int flag --pages")
		}
		opts = append(opts, &dataset.OptExtractScrollLimit{Limit: pages})
	}

	if flags.Lookup("start") != nil {
		start, err := flags.GetInt("start")
		if err != nil {
			log.Fatalf(ctx, "failed to get int flag --start")
		}
		opts = append(opts, &dataset.OptExtractScrollStart{Start: start})
	}

	if flags.Lookup("limit") != nil {
		limit, err := flags.GetInt("limit")
		if err != nil {
			log.Fatalf(ctx, "failed to get int flag --limit")
		}
		opts = append(opts, &dataset.OptExtractItemLimit{Limit: limit})
	}

	only, err := flags.GetStringArray("only")
	if err != nil {
		log.Fatalf(ctx, "failed to get int flag --only")
	}
	for _, o := range only {
		opts = append(opts, &dataset.OptExtractItemOnlyURL{URL: o})
	}

	cat, err := flags.GetBool("cat")
	if err != nil {
		log.Fatalf(ctx, "failed to get bool flag --cat")
	}
	if cat {
		opts = append(opts, &dataset.OptExtractItemCat{})
	}

	return opts
}
