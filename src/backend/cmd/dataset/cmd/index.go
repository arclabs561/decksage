package cmd

import (
	"fmt"
	"net/http"
	"strings"

	"github.com/felixge/fgprof"
	"github.com/spf13/cobra"

	"collections/blob"
	"collections/games/magic/dataset"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/scryfall"
	"collections/logger"
	"collections/search"
)

var indexCmd = &cobra.Command{
	Use:  "index DATASET",
	Args: cobra.ExactArgs(1),
	RunE: runIndex,
}

func init() {
	flags := indexCmd.PersistentFlags()

	flags.String("log-level", "info", "level to log at")
	flags.BoolP("debug", "d", false, "whether to set log level to debug, overrides --log-level")
	flags.String("bucket-url", "s3://games-collections", "bucket url for writing dataset")
	flags.StringP("cache", "c", "", "dir to use for local blob cache")

	flags.IntP("limit", "l", 0, "total number of items to transform")
	flags.IntP("parallel", "p", 1024, "number of parallel workers to transform with")
}

func runIndex(cmd *cobra.Command, args []string) error {
	ctx := cmd.Context()
	log := logger.NewLogger(ctx)

	logLevel, err := cmd.Flags().GetString("log-level")
	if err != nil {
		return fmt.Errorf("failed to get bool flag --log-level: %w", err)
	}
	log.SetLevel(logLevel)
	debug, err := cmd.Flags().GetBool("debug")
	if err != nil {
		return fmt.Errorf("failed to get bool flag --debug: %w", err)
	}
	if debug {
		log.SetLevel("debug")
	}

	http.DefaultServeMux.Handle("/debug/fgprof", fgprof.Handler())
	go func() {
		addr := "localhost:6060"
		log.Infof(ctx, "listening on http://%s", addr)
		if err := http.ListenAndServe(addr, nil); err != nil {
			log.Fatalf(ctx, "%v", err)
		}
	}()

	bucketUrl, err := cmd.Flags().GetString("bucket-url")
	if err != nil {
		panic(err)
	}

	var bucketOpts []blob.BucketOption
	if cmd.Flags().Changed("cache") {
		cacheDir, err := cmd.Flags().GetString("cache")
		if err != nil {
			log.Fatalf(ctx, "failed to get flag --cache")
		}
		bucketOpts = append(bucketOpts, &blob.OptBucketCache{
			Dir: cacheDir,
		})
	}

	bucket, err := blob.NewBucket(ctx, log, bucketUrl, bucketOpts...)
	if err != nil {
		return err
	}
	gamesBlob := bucket.WithPrefix("games/")
	defer gamesBlob.Close(ctx)
	scraperBlob := bucket.WithPrefix("scraper/")
	defer scraperBlob.Close(ctx)

	var d dataset.Dataset
	datasetName := strings.ToLower(args[0])
	switch datasetName {
	case "deckbox":
		d = deckbox.NewDataset(log, gamesBlob)
	case "scryfall":
		d = scryfall.NewDataset(log, gamesBlob)
	case "goldfish":
		d = goldfish.NewDataset(log, gamesBlob)
	default:
		return fmt.Errorf("unsupported dataset: %q", datasetName)
	}

	var options []search.IndexOption
	if cmd.Flags().Changed("limit") {
		limit, err := cmd.Flags().GetInt("limit")
		if err != nil {
			panic(err)
		}
		options = append(options, &search.OptLimit{Limit: limit})
	}
	// parallel, err := cmd.Flags().GetInt("parallel")
	// if err != nil {
	// 	panic(err)
	// }
	// options = append(options, &transform.OptTransformParallel{Parallel: parallel})

	index, err := search.NewIndex(log)
	if err != nil {
		return fmt.Errorf("failed to create new index: %w", err)
	}
	if err := index.PutItems(ctx, d, options...); err != nil {
		return fmt.Errorf("failed to put items: %w", err)
	}

	return nil
}
