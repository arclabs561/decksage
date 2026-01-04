package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"

	"github.com/samber/mo"
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
	"collections/logger"
)

var catCmd = &cobra.Command{
	Use:  "cat [DATASET]",
	RunE: runInspect,
}

func init() {
	flags := catCmd.PersistentFlags()

	flags.IntP("limit", "l", 0, "maxmum number of item to iterate, total over all datasets")
}

func runInspect(cmd *cobra.Command, args []string) error {
	ctx := cmd.Context()
	log := logger.NewLogger(ctx)

	config, err := newRootConfig(cmd)
	if err != nil {
		return err
	}

	gamesBlob := config.Bucket.WithPrefix("games/")
	defer gamesBlob.Close(config.Ctx)

	var ds []games.Dataset
	name := mo.None[string]()
	if len(args) > 0 {
		name = mo.Some(strings.ToLower(args[0]))
	}
	n, ok := name.Get()
	switch {
	case !ok || n == "deckbox":
		ds = append(ds, wrapMTGDataset(deckbox.NewDataset(log, gamesBlob)))
		fallthrough
	case !ok || n == "scryfall":
		ds = append(ds, wrapMTGDataset(scryfall.NewDataset(log, gamesBlob)))
		fallthrough
	case !ok || n == "goldfish":
		ds = append(ds, wrapMTGDataset(goldfish.NewDataset(log, gamesBlob)))
		fallthrough
	case !ok || n == "mtgtop8":
		ds = append(ds, wrapMTGDataset(mtgtop8.NewDataset(log, gamesBlob)))
		fallthrough
	case !ok || n == "digimon-limitless" || n == "digimonlimitless":
		ds = append(ds, digimonlimitless.NewDataset(log, gamesBlob))
		fallthrough
	case !ok || n == "digimon-limitless-web" || n == "digimonlimitlessweb":
		ds = append(ds, digimonlimitlessweb.NewDataset(log, gamesBlob))
		fallthrough
	case !ok || n == "onepiece-limitless" || n == "onepiecelimitless":
		ds = append(ds, onepiecelimitless.NewDataset(log, gamesBlob))
		fallthrough
	case !ok || n == "onepiece-limitless-web" || n == "onepiecelimitlessweb":
		ds = append(ds, onepiecelimitlessweb.NewDataset(log, gamesBlob))
		fallthrough
	case !ok || n == "riftbound-riftmana" || n == "riftboundriftmana":
		dataset, err := riftboundriftmana.NewDataset(log, gamesBlob)
		if err != nil {
			log.Errorf(context.Background(), "Failed to create riftmana dataset: %v", err)
		} else {
			ds = append(ds, dataset)
		}
		fallthrough
	case !ok || n == "riftbound-riftcodex" || n == "riftboundriftcodex":
		ds = append(ds, riftboundriftcodex.NewDataset(log, gamesBlob))
		fallthrough
	case !ok || n == "riftbound-riftboundgg" || n == "riftboundriftboundgg" || n == "riftbound-gg":
		dataset, err := riftboundriftboundgg.NewDataset(log, gamesBlob)
		if err != nil {
			log.Errorf(context.Background(), "Failed to create riftbound.gg dataset: %v", err)
		} else {
			ds = append(ds, dataset)
		}
	default:
		return fmt.Errorf("unsupported dataset: %q", n)
	}

	limit := mo.None[int]()
	if cmd.Flags().Changed("limit") {
		n, err := cmd.Flags().GetInt("limit")
		if err != nil {
			panic(err)
		}
		limit = mo.Some(n)
	}

	mu := new(sync.Mutex)
	total := 0
	for _, d := range ds {
		fn := func(item games.Item) error {
			mu.Lock()
			defer mu.Unlock()
			if n, ok := limit.Get(); ok && total >= n {
				return games.ErrIterItemsStop
			}
			b, err := json.Marshal(item)
			if err != nil {
				return err
			}
			fmt.Println(string(b))
			total++
			return nil
		}
		if err := d.IterItems(ctx, fn); err != nil {
			return fmt.Errorf("failed to iterate over dataset items: %w", err)
		}
	}

	return nil
}
