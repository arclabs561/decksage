package cmd

import (
	"encoding/json"
	"fmt"
	"strings"
	"sync"

	"github.com/samber/mo"
	"github.com/spf13/cobra"

	"collections/games/magic/dataset"
	"collections/games/magic/dataset/deckbox"
	"collections/games/magic/dataset/goldfish"
	"collections/games/magic/dataset/mtgtop8"
	"collections/games/magic/dataset/scryfall"
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

	var ds []dataset.Dataset
	name := mo.None[string]()
	if len(args) > 0 {
		name = mo.Some(strings.ToLower(args[0]))
	}
	n, ok := name.Get()
	switch {
	case !ok || n == "deckbox":
		ds = append(ds, deckbox.NewDataset(log, gamesBlob))
		fallthrough
	case !ok || n == "scryfall":
		ds = append(ds, scryfall.NewDataset(log, gamesBlob))
		fallthrough
	case !ok || n == "goldfish":
		ds = append(ds, goldfish.NewDataset(log, gamesBlob))
		fallthrough
	case !ok || n == "mtgtop8":
		ds = append(ds, mtgtop8.NewDataset(log, gamesBlob))
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
		fn := func(item dataset.Item) error {
			mu.Lock()
			defer mu.Unlock()
			if n, ok := limit.Get(); ok && total >= n {
				return dataset.ErrIterItemsStop
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
