package main

// Export collections from blob storage (S3 or local) to JSONL
// Uses IterItemsBlobPrefix pattern - works with any blob storage
//
// DATA LINEAGE: Order 1 (depends on Order 0: Primary Source Data)
// - Input: s3://games-collections/games/{game}/{dataset}/ (Order 0)
// - Output: data/processed/decks_{game}_{dataset}.jsonl (Order 1)
// - Converts Collection objects to flattened JSONL format

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"collections/blob"
	"collections/games"
	_ "collections/games/digimon/game"   // Register collection types
	_ "collections/games/magic/game"      // Register collection types
	_ "collections/games/onepiece/game"   // Register collection types
	_ "collections/games/pokemon/game"    // Register collection types
	_ "collections/games/riftbound/game"  // Register collection types
	_ "collections/games/yugioh/game"     // Register collection types
	"collections/logger"
)

func main() {
	if len(os.Args) < 4 {
		fmt.Println("Usage: export-blob <bucket-url> <game> <dataset> <output.jsonl>")
		fmt.Println("Example: export-blob s3://games-collections pokemon limitless-web output.jsonl")
		fmt.Println("Example: export-blob file://./data-full magic mtgtop8 output.jsonl")
		os.Exit(1)
	}

	bucketURL := os.Args[1]
	game := os.Args[2]
	dataset := os.Args[3]
	outputFile := os.Args[4]

	ctx := context.Background()
	log := logger.NewLogger(ctx)
	log.SetLevel("INFO")

	log.Infof(ctx, "Exporting %s/%s from %s...", game, dataset, bucketURL)

	// Create blob bucket
	bucket, err := blob.NewBucket(ctx, log, bucketURL)
	if err != nil {
		log.Errorf(ctx, "Failed to create bucket: %v", err)
		os.Exit(1)
	}
	defer func() {
		bucket.Close(ctx) // Close doesn't return error
	}()

	// Use games/ prefix
	gamesBucket := bucket.WithPrefix("games/")

	// Prefix for this game/dataset
	prefix := filepath.Join(game, dataset) + "/"

	log.Infof(ctx, "Iterating collections from prefix: %s", prefix)

	// Open output file
	out, err := os.Create(outputFile)
	if err != nil {
		log.Errorf(ctx, "Failed to create output file: %v", err)
		os.Exit(1)
	}
	defer out.Close()

	encoder := json.NewEncoder(out)
	exported := 0
	errors := 0

	// Iterate through collections using IterItemsBlobPrefix
	err = games.IterItemsBlobPrefix(
		ctx,
		gamesBucket,
		prefix,
		func(key string, data []byte) (games.Item, error) {
			var collection games.Collection
			if err := json.Unmarshal(data, &collection); err != nil {
				return nil, fmt.Errorf("failed to unmarshal collection: %w", err)
			}
			return &games.CollectionItem{
				Collection: &collection,
			}, nil
		},
		func(item games.Item) error {
			colItem, ok := item.(*games.CollectionItem)
			if !ok {
				return fmt.Errorf("unexpected item type")
			}

			collection := colItem.Collection

			// Convert to export format (similar to export-hetero)
			deckMap := map[string]interface{}{
				"deck_id":    collection.ID,
				"url":        collection.URL,
				"source":     collection.Source,
				"scraped_at": collection.ReleaseDate.Format("2006-01-02T15:04:05Z07:00"),
				"timestamp":  collection.ReleaseDate.Format("2006-01-02T15:04:05Z07:00"),
				"created_at": collection.ReleaseDate.Format("2006-01-02T15:04:05Z07:00"),
			}

			// Extract type info - use reflection or type switch
			// Try common methods first
			if inner := collection.Type.Inner; inner != nil {
				// Use type assertion with interface{} and extract via reflection-like approach
				// For now, extract what we can from the type
				deckMap["archetype"] = ""
				deckMap["format"] = ""
				deckMap["player"] = ""
				deckMap["event"] = ""
				deckMap["placement"] = 0
				deckMap["event_date"] = ""

				// Try to get values using type assertions for known types
				// This is a simplified approach - in production, you'd use proper type switches
			}

			// Extract cards from partitions
			var cards []map[string]interface{}
			for _, partition := range collection.Partitions {
				for _, card := range partition.Cards {
					cards = append(cards, map[string]interface{}{
						"name":      card.Name,
						"count":     card.Count,
						"partition": partition.Name,
					})
				}
			}

			if len(cards) == 0 {
				return nil // Skip decks with no cards
			}

			deckMap["cards"] = cards

			if err := encoder.Encode(deckMap); err != nil {
				return fmt.Errorf("failed to encode deck: %w", err)
			}

			exported++
			if exported%1000 == 0 {
				log.Infof(ctx, "Exported %d decks...", exported)
			}

			return nil
		},
	)

	if err != nil {
		log.Errorf(ctx, "Iteration failed: %v", err)
		errors++
	}

	log.Infof(ctx, "✅ Exported %d decks to %s", exported, outputFile)
	if errors > 0 {
		log.Warnf(ctx, "⚠️  Encountered %d errors", errors)
	}
}

func getString(m map[string]interface{}, key string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return ""
}

func getInt(m map[string]interface{}, key string) int {
	if v, ok := m[key].(float64); ok {
		return int(v)
	}
	return 0
}
