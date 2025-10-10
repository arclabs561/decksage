package main

// Quick tool to split pairs.csv by format
// Usage: go run split_by_format.go data-full/games/magic pairs_500decks.csv

import (
	"collections/blob"
	"collections/games"
	"collections/logger"
	"context"
	"fmt"
	"os"
)

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: split_by_format DATA_DIR PAIRS_CSV")
		os.Exit(1)
	}

	ctx := context.Background()
	log := logger.NewLogger(ctx)

	dataDir := os.Args[1]
	// pairsFile := os.Args[2] // Currently unused - kept for potential future use

	// Read all decks, build format → cards mapping
	bucket, _ := blob.NewBucket(ctx, log, "file://"+dataDir)
	defer bucket.Close(ctx)

	formatDecks := make(map[string][][]string)

	// Iterate through collections
	games.IterItemsBlobPrefix(
		ctx,
		bucket,
		"magic/",
		games.DeserializeAsCollection,
		func(item games.Item) error {
			col, ok := item.(*games.CollectionItem)
			if !ok {
				return nil
			}

			// Get format
			format := "unknown"
			if deckType, ok := col.Collection.Type.Inner.(interface{ Format() string }); ok {
				format = deckType.Format()
			}

			// Get cards
			var cards []string
			for _, p := range col.Collection.Partitions {
				for _, c := range p.Cards {
					cards = append(cards, c.Name)
				}
			}

			formatDecks[format] = append(formatDecks[format], cards)
			return nil
		},
	)

	// Print stats
	for format, decks := range formatDecks {
		fmt.Printf("%s: %d decks\n", format, len(decks))
	}
}
