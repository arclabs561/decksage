package cmd

import (
	"context"
	"fmt"
	"strings"

	"github.com/spf13/cobra"
	"github.com/spf13/pflag"

	"collections/games"
	"collections/games/magic/dataset"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/mtgdecks"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
	"collections/games/pokemon/dataset/limitless"
	limitlessweb "collections/games/pokemon/dataset/limitless-web"

	// "collections/games/pokemon/dataset/pokemontcg"
	pokemontcgprice "collections/games/pokemon/dataset/pokemon-tcg-price-api"
	pokemoncardio "collections/games/pokemon/dataset/pokemoncard-io"
	pokemontcgdata "collections/games/pokemon/dataset/pokemontcg-data"
	pokestats "collections/games/pokemon/dataset/pokestats"
	"collections/games/yugioh/dataset/ygoprodeck"
	ygoprodecktournament "collections/games/yugioh/dataset/ygoprodeck-tournament"
	"collections/games/yugioh/dataset/yugiohmeta"
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

	datasetName := strings.ToLower(args[0])

	switch datasetName {
	// MTG datasets (use magic/dataset options)
	case "deckbox":
		d := deckbox.NewDataset(config.Log, gamesBlob)
		opts := parseMTGOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "scryfall":
		d := scryfall.NewDataset(config.Log, gamesBlob)
		opts := parseMTGOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "goldfish":
		d := goldfish.NewDataset(config.Log, gamesBlob)
		opts := parseMTGOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "mtgdecks":
		d := mtgdecks.NewDataset(config.Log, gamesBlob)
		opts := parseMTGOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "mtgtop8":
		d := mtgtop8.NewDataset(config.Log, gamesBlob)
		opts := parseMTGOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	// Yu-Gi-Oh! datasets (use games options)
	case "ygoprodeck":
		d := ygoprodeck.NewDataset(config.Log, gamesBlob)
		opts := parseGamesOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "ygoprodeck-tournament":
		d := ygoprodecktournament.NewDataset(config.Log, gamesBlob)
		opts := parseMTGOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "yugiohmeta":
		d := yugiohmeta.NewDataset(config.Log, gamesBlob)
		opts := parseGamesOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	// Pokemon datasets (use games options)
	case "pokemontcg-data":
		d := pokemontcgdata.NewDataset(config.Log, gamesBlob)
		opts := parseGamesOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "pokemon-tcg-price-api":
		d := pokemontcgprice.NewDataset(config.Log, gamesBlob)
		opts := parseGamesOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "pokemoncard-io":
		d := pokemoncardio.NewDataset(config.Log, gamesBlob)
		opts := parseGamesOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "pokestats":
		d := pokestats.NewDataset(config.Log, gamesBlob)
		opts := parseGamesOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "limitless":
		d := limitless.NewDataset(config.Log, gamesBlob)
		opts := parseGamesOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	case "limitless-web":
		d := limitlessweb.NewDataset(config.Log, gamesBlob)
		opts := parseMTGOptions(config.Ctx, config.Log, cmd.Flags())
		if err := d.Extract(config.Ctx, scraper, opts...); err != nil {
			return fmt.Errorf("failed to update: %w", err)
		}
	default:
		return fmt.Errorf(
			"unsupported dataset %q, allowed (%+v)",
			datasetName,
			[]string{"deckbox", "scryfall", "goldfish", "mtgdecks", "mtgtop8", "ygoprodeck", "ygoprodeck-tournament", "yugiohmeta", "pokemontcg-data", "pokemon-tcg-price-api", "pokemoncard-io", "pokestats", "limitless", "limitless-web"},
		)
	}

	return nil
}

func parseMTGOptions(
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

func parseGamesOptions(
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
