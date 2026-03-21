package cmd

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"github.com/spf13/pflag"

	"collections/games"
	"collections/games/digimon/dataset/digimoncard"
	digimonlimitless "collections/games/digimon/dataset/limitless"
	digimonlimitlessweb "collections/games/digimon/dataset/limitless-web"
	"collections/games/magic/dataset/archidekt"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
	onepiecelimitless "collections/games/onepiece/dataset/limitless"
	onepiecelimitlessweb "collections/games/onepiece/dataset/limitless-web"
	"collections/games/onepiece/dataset/onepiecetcg"
	pokemonlimitless "collections/games/pokemon/dataset/limitless"
	pokemonlimitlessweb "collections/games/pokemon/dataset/limitless-web"
	"collections/games/pokemon/dataset/pokemon-tcg-price-api"
	"collections/games/pokemon/dataset/pokemoncard-io"
	"collections/games/pokemon/dataset/pokemontcg"
	"collections/games/pokemon/dataset/pokemontcg-data"
	"collections/games/pokemon/dataset/pokestats"
	riftboundriftboundgg "collections/games/riftbound/dataset/riftboundgg"
	riftboundriftcodex "collections/games/riftbound/dataset/riftcodex"
	riftboundriftmana "collections/games/riftbound/dataset/riftmana"
	"collections/games/yugioh/dataset/ygoprodeck"
	"collections/games/yugioh/dataset/yugiohmeta"
	"collections/logger"
	limpet "github.com/arclabs561/limpet"
	limpetblob "github.com/arclabs561/limpet/blob"
)

// datasetCacheTTL overrides cache TTL per dataset. Card databases change
// weekly at most. Datasets not listed use the bucket default (24h).
var datasetCacheTTL = map[string]time.Duration{
	"scryfall":            7 * 24 * time.Hour, // card data
	"ygoprodeck":          7 * 24 * time.Hour,
	"digimoncard":         7 * 24 * time.Hour,
	"pokemontcg-data":     7 * 24 * time.Hour,
	"pokemontcg":          7 * 24 * time.Hour,
	"pokemoncard-io":      7 * 24 * time.Hour,
	"riftbound-riftcodex": 7 * 24 * time.Hour,
}

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
	flags.StringP("cache", "c", "", "dir to use for local blob cache (avoids default Badger lock)")
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

	// For file:// buckets, skip Badger cache (reads are local, no S3 round-trips to cache).
	// For s3:// buckets, use the --cache dir if provided, else default.
	var blobCfg *limpetblob.BucketConfig
	if strings.HasPrefix(config.BucketURL, "file://") {
		blobCfg = &limpetblob.BucketConfig{NoCache: true}
	} else if cmd.Flags().Changed("cache") {
		cacheDir, _ := cmd.Flags().GetString("cache")
		blobCfg = &limpetblob.BucketConfig{CacheDir: cacheDir}
	}
	scraperBucket, err := limpetblob.NewBucket(config.Ctx, config.BucketURL+"/scraper", blobCfg)
	if err != nil {
		return fmt.Errorf("failed to create limpet bucket: %w", err)
	}
	defer scraperBucket.Close()
	sc, err := limpet.NewClient(config.Ctx, scraperBucket,
		limpet.WithUserAgent("decksage/1.0 (+https://github.com/arclabs561/decksage)"),
		limpet.WithIgnoreHeaders("Accept-Encoding", "Accept-Language"),
		limpet.WithIgnoreParams("utm_source", "utm_medium", "utm_campaign", "ref"),
		limpet.WithCacheStatuses(200, 301),
	)
	if err != nil {
		return fmt.Errorf("failed to create limpet client: %w", err)
	}
	defer sc.Close()

	var d games.Dataset
	datasetName := strings.ToLower(args[0])
	switch datasetName {
	case "deckbox":
		d = wrapMTGDataset(deckbox.NewDataset(config.Log, gamesBlob))
	case "scryfall":
		d = wrapMTGDataset(scryfall.NewDataset(config.Log, gamesBlob))
	case "goldfish":
		d = wrapMTGDataset(goldfish.NewDataset(config.Log, gamesBlob))
	case "mtgtop8":
		d = wrapMTGDataset(mtgtop8.NewDataset(config.Log, gamesBlob))
	case "archidekt":
		d = wrapMTGDataset(archidekt.NewDataset(config.Log, gamesBlob))
	case "digimoncard", "digimon-card":
		d = digimoncard.NewDataset(config.Log, gamesBlob)
	case "digimon-limitless", "digimonlimitless":
		d = digimonlimitless.NewDataset(config.Log, gamesBlob)
	case "digimon-limitless-web", "digimonlimitlessweb":
		d = digimonlimitlessweb.NewDataset(config.Log, gamesBlob)
	case "onepiece-limitless", "onepiecelimitless":
		d = onepiecelimitless.NewDataset(config.Log, gamesBlob)
	case "onepiece-limitless-web", "onepiecelimitlessweb":
		d = onepiecelimitlessweb.NewDataset(config.Log, gamesBlob)
	case "onepiecetcg", "onepiece-tcg":
		d = onepiecetcg.NewDataset(config.Log, gamesBlob)
	case "riftbound-riftmana", "riftboundriftmana":
		dataset, err := riftboundriftmana.NewDataset(config.Log, gamesBlob)
		if err != nil {
			return fmt.Errorf("failed to create riftmana dataset: %w", err)
		}
		d = dataset
	case "riftbound-riftcodex", "riftboundriftcodex":
		d = riftboundriftcodex.NewDataset(config.Log, gamesBlob)
	case "riftbound-riftboundgg", "riftboundriftboundgg", "riftbound-gg":
		dataset, err := riftboundriftboundgg.NewDataset(config.Log, gamesBlob)
		if err != nil {
			return fmt.Errorf("failed to create riftbound.gg dataset: %w", err)
		}
		d = dataset
	case "pokemontcg-data", "pokemontcgdata":
		d = wrapExtractOnly(pokemontcgdata.NewDataset(config.Log, gamesBlob))
	case "pokemontcg":
		d = pokemontcg.NewDataset(config.Log, gamesBlob)
	case "pokemon-limitless", "pokemonlimitless":
		d = pokemonlimitless.NewDataset(config.Log, gamesBlob)
	case "pokemon-limitless-web", "pokemonlimitlessweb":
		d = pokemonlimitlessweb.NewDataset(config.Log, gamesBlob)
	case "pokestats":
		d = wrapExtractOnly(pokestats.NewDataset(config.Log, gamesBlob))
	case "pokemoncard-io", "pokemoncardio":
		d = wrapExtractOnly(pokemoncardio.NewDataset(config.Log, gamesBlob))
	case "pokemon-tcg-price-api", "pokemontcgpriceapi":
		d = wrapExtractOnly(pokemontcgpriceapi.NewDataset(config.Log, gamesBlob))
	case "ygoprodeck":
		d = ygoprodeck.NewDataset(config.Log, gamesBlob)
	case "yugiohmeta":
		d = yugiohmeta.NewDataset(config.Log, gamesBlob)
	default:
		return fmt.Errorf(
			"unsupported dataset %q, allowed (%+v)",
			datasetName,
			[]string{"archidekt", "deckbox", "scryfall", "goldfish", "mtgtop8", "digimoncard", "digimon-limitless", "digimon-limitless-web", "onepiecetcg", "onepiece-limitless", "onepiece-limitless-web", "pokemontcg-data", "pokemontcg", "pokemon-limitless", "pokemon-limitless-web", "pokestats", "pokemoncard-io", "pokemon-tcg-price-api", "ygoprodeck", "yugiohmeta", "riftbound-riftmana", "riftbound-riftcodex", "riftbound-riftboundgg"},
		)
	}
	opts := parseOptions(config.Ctx, config.Log, cmd.Flags())

	// Create stats tracker and progress reporter for extraction metrics
	stats := games.NewExtractStats(config.Log)
	progress := games.NewProgressReporter(config.Log, d.Description().Name, 30*time.Second)

	// Pass stats and per-dataset cache TTL through context.
	// Card databases change weekly; tournament/deck sources use the bucket default (24h).
	ctxWithStats := games.WithExtractStats(config.Ctx, stats)
	if ttl, ok := datasetCacheTTL[datasetName]; ok {
		ctxWithStats = limpet.WithCacheTTL(ctxWithStats, ttl)
	}

	config.Log.Infof(ctxWithStats, "🚀 Starting extraction for dataset: %s", d.Description().Name)

	if err := d.Extract(ctxWithStats, sc, opts...); err != nil {
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
) []games.UpdateOption {
	var opts []games.UpdateOption

	reparse, err := flags.GetBool("reparse")
	if err != nil {
		log.Fatalf(ctx, "failed to get bool flag --reparse")
	}
	if reparse {
		opts = append(opts, &games.OptExtractReparse{})
	}

	rescrape, err := flags.GetBool("rescrape")
	if err != nil {
		log.Fatalf(ctx, "failed to get bool flag --rescrape")
	}
	if rescrape {
		opts = append(opts, &games.OptExtractScraperReplaceAll{})
	}

	parallel, err := flags.GetInt("parallel")
	if err != nil {
		log.Fatalf(ctx, "failed to get int flag --parallel")
	}
	opts = append(opts, &games.OptExtractParallel{Parallel: parallel})

	if flags.Lookup("section") != nil {
		section, err := flags.GetString("section")
		if err != nil {
			log.Fatalf(ctx, "failed to get string flag --section")
		}
		opts = append(opts, &games.OptExtractSectionOnly{Section: section})
	}

	if flags.Lookup("pages") != nil {
		pages, err := flags.GetInt("pages")
		if err != nil {
			log.Fatalf(ctx, "failed to get int flag --pages")
		}
		opts = append(opts, &games.OptExtractScrollLimit{Limit: pages})
	}

	if flags.Lookup("start") != nil {
		start, err := flags.GetInt("start")
		if err != nil {
			log.Fatalf(ctx, "failed to get int flag --start")
		}
		opts = append(opts, &games.OptExtractScrollStart{Start: start})
	}

	if flags.Lookup("limit") != nil {
		limit, err := flags.GetInt("limit")
		if err != nil {
			log.Fatalf(ctx, "failed to get int flag --limit")
		}
		opts = append(opts, &games.OptExtractItemLimit{Limit: limit})
	}

	only, err := flags.GetStringArray("only")
	if err != nil {
		log.Fatalf(ctx, "failed to get int flag --only")
	}
	for _, o := range only {
		opts = append(opts, &games.OptExtractItemOnlyURL{URL: o})
	}

	cat, err := flags.GetBool("cat")
	if err != nil {
		log.Fatalf(ctx, "failed to get bool flag --cat")
	}
	if cat {
		opts = append(opts, &games.OptExtractItemCat{})
	}

	return opts
}
